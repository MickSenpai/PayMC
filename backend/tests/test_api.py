from fastapi.testclient import TestClient
from app.main import app, get_paypal
from app.paypal import ProviderError

H = {"X-API-Key": "dev-key"}


class FakePP:
    def __init__(self): self.order, self.sig_ok, self.err = None, True, False
    def get_order(self, _):
        if self.err: raise ProviderError("down")
        return self.order
    def verify_webhook(self, headers, event): return self.sig_ok


pp = FakePP()
app.dependency_overrides[get_paypal] = lambda: pp
good = {"id": "5O190127TN364715T", "status": "COMPLETED", "purchase_units": [{"amount": {"currency_code": "EUR", "value": "10.00"},
        "payments": {"captures": [{"id": "C", "status": "COMPLETED", "amount": {"currency_code": "EUR", "value": "10.00"}}]}}]}


def test_flow_and_webhook_idempotency_and_signature():
    with TestClient(app) as c:
        assert c.post("/api/orders", json={"reference": "R1", "amount": "10", "currency": "eur"}).status_code == 401
        o = c.post("/api/orders", headers=H, json={"reference": "R1", "amount": "10", "currency": "eur"}).json()
        pp.order = good
        r = c.post(f"/api/orders/{o['id']}/verify", headers=H, json={"paypal_order_id": "5O190127TN364715T"}); assert r.json()["status"] == "verified"
        pp.err = True
        assert c.post(f"/api/orders/{o['id']}/verify", headers=H, json={"paypal_order_id": "5O190127TN364715T"}).json()["status"] == "review_required"
        pp.err = False
        n = len(c.get("/api/alerts", headers=H).json())
        ev = {"id": "WH-1", "event_type": "PAYMENT.CAPTURE.COMPLETED",
              "resource": {"supplementary_data": {"related_ids": {"order_id": "5O190127TN364715T"}}}}
        pp.sig_ok = False
        assert c.post("/api/webhooks/paypal", json=ev).status_code == 400
        assert len(c.get("/api/alerts", headers=H).json()) == n
        pp.sig_ok = True
        assert c.post("/api/webhooks/paypal", json=ev).json()["status"] == "processed"
        assert c.post("/api/webhooks/paypal", json=ev).json()["status"] == "duplicate"
        assert len(c.get("/api/alerts", headers=H).json()) == n + 1


def test_message_analysis_and_review():
    with TestClient(app) as c:
        a = c.post("/api/analyze/message", headers=H, json={"text": "You have received payment, ship first http://bit.ly/x"}).json()
        assert a["status"] == "review_required" or a["status"] == "high_risk"
        r = c.patch(f"/api/alerts/{a['id']}", headers=H, json={"review_state": "cleared", "note": "ok"}).json()
        assert r["review_state"] == "cleared"


def test_ai_degrades_without_key_and_screenshot_requires_it():
    from app import ai
    from app.config import settings
    settings.anthropic_api_key = ""
    assert ai.analyze_text("hola") == ([], {})
    with TestClient(app) as c:
        r = c.post("/api/analyze/screenshot", headers=H, json={"image_base64": "aGk=", "media_type": "image/png"})
        assert r.status_code == 503


def test_ai_signals_are_capped_and_screenshot_never_verified(monkeypatch):
    from app import ai
    from app.signals import Signal
    monkeypatch.setattr(ai, "enabled", lambda: True)
    monkeypatch.setattr(ai, "explain", lambda v: "explicación")
    monkeypatch.setattr(ai, "analyze_image", lambda b, m: ("Has recibido 50 EUR", ai._signals(
        {"signals": [{"code": "x", "severity": "high", "message": "m"}]}), {"amount": "50"}))
    assert ai._signals({"signals": [{"code": "x", "severity": "high", "message": "m"}]})[0].severity == "low"
    with TestClient(app) as c:
        o = c.post("/api/orders", headers=H, json={"reference": "RS1", "amount": "10", "currency": "eur"}).json()
        a = c.post("/api/analyze/screenshot", headers=H,
                   json={"image_base64": "aGk=", "media_type": "image/png", "order_id": o["id"]}).json()
        codes = {s["code"] for s in a["signals"]}
        assert a["status"] != "verified" and {"screenshot_not_proof", "screenshot_amount_mismatch"} <= codes
        assert a["explanation"] == "explicación"
