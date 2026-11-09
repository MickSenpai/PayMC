"""Motor de reglas deterministas: compara un pedido esperado con la orden de PayPal."""
from decimal import Decimal, InvalidOperation

from .signals import Signal, Verdict, build_verdict


def evaluate_payment(expected: dict, paypal_order: dict | None, *, provider_error: str | None = None,
                     recent_attempts: int = 0, velocity_threshold: int = 5) -> Verdict:
    """expected: {amount, currency, payee_email?}. paypal_order: JSON de GET /v2/checkout/orders/{id}."""
    sigs: list[Signal] = []

    if recent_attempts >= velocity_threshold:
        sigs.append(Signal("attempt_burst", "medium",
                           f"{recent_attempts} intentos en la ventana reciente (posible prueba automatizada).",
                           "internal_velocity", {"attempts": recent_attempts}))

    if provider_error:
        sigs.append(Signal("provider_unavailable", "info",
                           "No se pudo consultar a PayPal; el pago no está verificado (no implica fraude).",
                           "provider", {"error": provider_error}))
        return build_verdict(sigs, verifiable=False)

    if paypal_order is None:
        sigs.append(Signal("order_not_found", "high",
                           "PayPal no reconoce esa orden. Una captura o correo no es prueba de pago.",
                           "paypal_api"))
        return build_verdict(sigs)

    status = paypal_order.get("status")
    if status != "COMPLETED":
        sev = "medium" if status in {"APPROVED", "CREATED", "SAVED", "PAYER_ACTION_REQUIRED"} else "high"
        sigs.append(Signal("payment_not_completed", sev,
                           f"El estado de la orden es {status}, no COMPLETED.", "paypal_api", {"status": status}))

    units = paypal_order.get("purchase_units") or []
    if not units:
        sigs.append(Signal("no_purchase_units", "high", "La orden no contiene unidades de compra.", "paypal_api"))
        return build_verdict(sigs)
    unit = units[0]

    captures = (unit.get("payments") or {}).get("captures") or []
    if status == "COMPLETED" and not captures:
        sigs.append(Signal("no_capture", "high", "Orden COMPLETED sin capturas registradas.", "paypal_api"))
    for c in captures:
        if c.get("status") not in {"COMPLETED"}:
            sigs.append(Signal("capture_not_completed", "high" if c.get("status") in {"DECLINED", "FAILED"} else "medium",
                               f"Captura {c.get('id')} en estado {c.get('status')}.", "paypal_api",
                               {"capture_id": c.get("id"), "status": c.get("status")}))

    amount = (captures[0].get("amount") if captures else None) or unit.get("amount") or {}
    try:
        paid = Decimal(str(amount.get("value")))
        want = Decimal(str(expected["amount"]))
        if paid != want:
            sigs.append(Signal("amount_mismatch", "high", f"Importe pagado {paid} ≠ esperado {want}.",
                               "paypal_api", {"paid": str(paid), "expected": str(want)}))
    except (InvalidOperation, TypeError):
        sigs.append(Signal("amount_unreadable", "high", "No se pudo leer el importe de PayPal.", "paypal_api"))

    if (amount.get("currency_code") or "").upper() != expected["currency"].upper():
        sigs.append(Signal("currency_mismatch", "high",
                           f"Moneda {amount.get('currency_code')} ≠ esperada {expected['currency']}.",
                           "paypal_api", {"paid": amount.get("currency_code"), "expected": expected["currency"]}))

    want_payee = (expected.get("payee_email") or "").lower()
    got_payee = ((unit.get("payee") or {}).get("email_address") or "").lower()
    if want_payee and got_payee != want_payee:
        sigs.append(Signal("payee_mismatch", "high", "El destinatario del pago no coincide con el esperado.",
                           "paypal_api", {"paid_to": got_payee, "expected": want_payee}))

    return build_verdict(sigs)
