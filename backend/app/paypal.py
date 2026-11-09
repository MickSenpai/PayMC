import time

import httpx

from .config import settings


class ProviderError(Exception):
    pass


class PayPalClient:
    """Cliente servidor-a-servidor. Las credenciales nunca salen del backend."""

    def __init__(self) -> None:
        self._token: str | None = None
        self._exp = 0.0

    def _http(self) -> httpx.Client:
        return httpx.Client(base_url=settings.paypal_base_url, timeout=10)

    def _auth(self, c: httpx.Client) -> dict:
        if not self._token or time.time() > self._exp - 30:
            if not settings.paypal_client_id:
                raise ProviderError("Credenciales de PayPal no configuradas")
            r = c.post("/v1/oauth2/token", data={"grant_type": "client_credentials"},
                       auth=(settings.paypal_client_id, settings.paypal_client_secret))
            if r.status_code != 200:
                raise ProviderError(f"OAuth falló ({r.status_code})")
            j = r.json()
            self._token, self._exp = j["access_token"], time.time() + j["expires_in"]
        return {"Authorization": f"Bearer {self._token}"}

    def get_order(self, order_id: str) -> dict | None:
        """Devuelve None si la orden no existe; lanza ProviderError si la API falla."""
        try:
            with self._http() as c:
                r = c.get(f"/v2/checkout/orders/{order_id}", headers=self._auth(c))
        except httpx.HTTPError as e:
            raise ProviderError(str(e)) from e
        if r.status_code in (404, 400, 422):
            return None
        if r.status_code != 200:
            raise ProviderError(f"HTTP {r.status_code}")
        return r.json()

    def verify_webhook(self, headers: dict, event: dict) -> bool:
        body = {
            "auth_algo": headers.get("paypal-auth-algo"),
            "cert_url": headers.get("paypal-cert-url"),
            "transmission_id": headers.get("paypal-transmission-id"),
            "transmission_sig": headers.get("paypal-transmission-sig"),
            "transmission_time": headers.get("paypal-transmission-time"),
            "webhook_id": settings.paypal_webhook_id,
            "webhook_event": event,
        }
        if not all(body[k] for k in ("auth_algo", "cert_url", "transmission_id", "transmission_sig", "transmission_time")) \
                or not settings.paypal_webhook_id:
            return False
        try:
            with self._http() as c:
                r = c.post("/v1/notifications/verify-webhook-signature", json=body, headers=self._auth(c))
            return r.status_code == 200 and r.json().get("verification_status") == "SUCCESS"
        except (httpx.HTTPError, ProviderError):
            return False


paypal_client = PayPalClient()
