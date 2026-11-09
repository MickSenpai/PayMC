from app.engine import evaluate_payment
from app.phishing import analyze_message

EXP = {"amount": "25.00", "currency": "EUR", "payee_email": "shop@example.com"}


def order(status="COMPLETED", value="25.00", cur="EUR", payee="shop@example.com", cap="COMPLETED"):
    return {"id": "X", "status": status, "purchase_units": [{
        "payee": {"email_address": payee}, "amount": {"currency_code": cur, "value": value},
        "payments": {"captures": [{"id": "C1", "status": cap, "amount": {"currency_code": cur, "value": value}}]}}]}


def codes(v): return {s.code for s in v.signals}


def test_valid_payment_verified():
    assert evaluate_payment(EXP, order()).status == "verified"

def test_nonexistent_order_not_verified():
    v = evaluate_payment(EXP, None)
    assert v.status != "verified" and "order_not_found" in codes(v)

def test_amount_and_currency_mismatch_high_risk():
    v = evaluate_payment(EXP, order(value="2.50", cur="USD"))
    assert v.status == "high_risk" and {"amount_mismatch", "currency_mismatch"} <= codes(v)

def test_not_completed_needs_review():
    v = evaluate_payment(EXP, order(status="APPROVED", cap="PENDING"))
    assert v.status == "review_required" and "payment_not_completed" in codes(v)

def test_provider_down_is_review_not_fraud():
    v = evaluate_payment(EXP, None, provider_error="timeout")
    assert v.status == "review_required" and v.score == 0

def test_burst_flags_review():
    v = evaluate_payment(EXP, order(), recent_attempts=6)
    assert v.status == "review_required" and "attempt_burst" in codes(v)

def test_legit_with_atypical_signal_not_high_risk():
    v = evaluate_payment(EXP, order(), recent_attempts=5)
    assert v.status != "high_risk"

def test_phishing_detected():
    v = analyze_message("URGENTE: tu cuenta será suspendida. Inicia sesión en http://paypal-secure.xyz/login")
    assert v.status == "high_risk" and {"paypal_lookalike", "urgency"} <= codes(v)

def test_benign_message_clean():
    assert analyze_message("Hola, te paso el pedido mañana. Gracias!").status == "verified"

def test_official_domain_not_flagged():
    assert "paypal_lookalike" not in codes(analyze_message("Mira https://www.paypal.com/invoice/123"))
