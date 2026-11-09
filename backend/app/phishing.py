"""Análisis heurístico de mensajes. Prioriza revisiones; no prueba falsificación."""
import re
from urllib.parse import urlparse

from .signals import Signal, Verdict, build_verdict

URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>\"')]+", re.I)
SHORTENERS = {"bit.ly", "tinyurl.com", "t.co", "goo.gl", "is.gd", "cutt.ly", "rb.gy", "ow.ly"}
RISKY_TLDS = {"zip", "xyz", "top", "click", "icu", "rest", "country", "gq", "tk", "work"}
OFFICIAL = {"paypal.com", "paypal.me", "paypalobjects.com"}
URGENCY = re.compile(r"urgente|inmediat|\b24 horas|suspendid|bloquead|verifica(r)? tu cuenta|"
                     r"act(ú|u)a ya|urgent|immediately|suspended|limited|within 24 hours", re.I)
CREDENTIALS = re.compile(r"contrase(ñ|n)a|password|c(ó|o)digo (de )?(verificaci|seguridad)|cvv|pin\b|"
                         r"n(ú|u)mero de tarjeta|card number|inicia(r)? sesi(ó|o)n|log ?in", re.I)
PAYMENT_CLAIM = re.compile(r"(has recibido|recibiste|you('ve| have) received|payment (received|sent)|"
                           r"pago (recibido|enviado|completado))", re.I)
SHIP_FIRST = re.compile(r"env(í|i)a (primero|antes)|ship (first|before)|libera(r)? (el )?(pedido|env(í|i)o)|release (the )?(item|order)", re.I)


def _registrable(host: str) -> str:
    parts = host.lower().strip(".").split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host.lower()


def analyze_message(text: str) -> Verdict:
    sigs: list[Signal] = []
    for raw in dict.fromkeys(URL_RE.findall(text)):
        url = raw if raw.lower().startswith("http") else "http://" + raw
        host = (urlparse(url).hostname or "").lower()
        reg = _registrable(host)
        ev = {"url": raw, "host": host}
        if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", host):
            sigs.append(Signal("ip_host", "high", "El enlace usa una dirección IP en lugar de un dominio.", "message_analysis", ev))
        elif "paypal" in host and reg not in OFFICIAL:
            sigs.append(Signal("paypal_lookalike", "high", f"Dominio {host} imita a PayPal sin ser oficial.", "message_analysis", ev))
        elif host.startswith("xn--") or ".xn--" in host:
            sigs.append(Signal("punycode", "high", "Dominio con punycode (posible homógrafo).", "message_analysis", ev))
        elif reg in SHORTENERS:
            sigs.append(Signal("url_shortener", "medium", "Enlace acortado que oculta el destino.", "message_analysis", ev))
        elif host.rsplit(".", 1)[-1] in RISKY_TLDS:
            sigs.append(Signal("risky_tld", "low", f"TLD poco habitual en comunicaciones de pago (.{host.rsplit('.',1)[-1]}).", "message_analysis", ev))
        if url.startswith("http://") and reg not in OFFICIAL:
            sigs.append(Signal("no_https", "low", "El enlace no usa HTTPS.", "message_analysis", ev))
    if URGENCY.search(text):
        sigs.append(Signal("urgency", "medium", "Lenguaje de urgencia o amenaza de suspensión.", "message_analysis"))
    if CREDENTIALS.search(text):
        sigs.append(Signal("credential_request", "high", "Solicita credenciales, códigos o datos de tarjeta.", "message_analysis"))
    if PAYMENT_CLAIM.search(text):
        sigs.append(Signal("unverified_payment_claim", "medium",
                           "Afirma que hay un pago; verifícalo en tu cuenta/API de PayPal, no por este mensaje.", "message_analysis"))
    if SHIP_FIRST.search(text):
        sigs.append(Signal("ship_first_pressure", "medium", "Presiona para entregar o enviar antes de verificar el pago.", "message_analysis"))
    return build_verdict(sigs)
