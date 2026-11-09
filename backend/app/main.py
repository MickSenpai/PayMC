from contextlib import asynccontextmanager
from datetime import timedelta
from decimal import Decimal

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import base64
import binascii

from . import ai
from .config import settings
from .db import Alert, Attempt, Order, WebhookEvent, get_session, init_db, now
from .engine import evaluate_payment
from .paypal import PayPalClient, ProviderError, paypal_client
from .phishing import analyze_message
from .signals import Signal, build_verdict


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="TrustShield", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"],
                   allow_methods=["*"], allow_headers=["*"])


def get_paypal() -> PayPalClient:
    return paypal_client


def require_key(x_api_key: str = Header(default="")):
    if x_api_key != settings.api_key:
        raise HTTPException(401, "API key inválida")


class OrderIn(BaseModel):
    reference: str = Field(min_length=1, max_length=100)
    amount: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    payee_email: str | None = None


class VerifyIn(BaseModel):
    paypal_order_id: str = Field(min_length=3, max_length=64)


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=20000)


class ScreenshotIn(BaseModel):
    image_base64: str = Field(min_length=1, max_length=7_000_000)
    media_type: str = Field(pattern="^image/(png|jpeg|gif|webp)$")
    order_id: int | None = None


class ReviewIn(BaseModel):
    review_state: str = Field(pattern="^(open|cleared|confirmed)$")
    note: str | None = Field(default=None, max_length=500)


def alert_dict(a: Alert) -> dict:
    return {"id": a.id, "kind": a.kind, "order_id": a.order_id, "status": a.status, "score": a.score,
            "action": a.action, "explanation": a.explanation, "signals": a.signals, "review_state": a.review_state,
            "review_note": a.review_note, "created_at": a.created_at.isoformat()}


def order_dict(o: Order) -> dict:
    return {"id": o.id, "reference": o.reference, "amount": str(o.amount), "currency": o.currency,
            "payee_email": o.payee_email, "paypal_order_id": o.paypal_order_id,
            "created_at": o.created_at.isoformat()}


def save_alert(db: Session, kind: str, order_id: int | None, verdict) -> Alert:
    alert = Alert(kind=kind, order_id=order_id, status=verdict.status, score=verdict.score, action=verdict.action,
                  signals=verdict.to_dict()["signals"], explanation=ai.explain(verdict))
    db.add(alert)
    db.commit()
    return alert


def run_verification(db: Session, order: Order, paypal_order_id: str, pp: PayPalClient) -> Alert:
    """Consulta la fuente oficial, aplica reglas y persiste la alerta."""
    window = now() - timedelta(seconds=settings.velocity_window_seconds)
    recent = db.scalar(select(func.count()).select_from(Attempt)
                       .where(Attempt.key == order.reference, Attempt.at >= window)) or 0
    err, pp_order = None, None
    try:
        pp_order = pp.get_order(paypal_order_id)
    except ProviderError as e:
        err = str(e)
    verdict = evaluate_payment({"amount": order.amount, "currency": order.currency, "payee_email": order.payee_email},
                               pp_order, provider_error=err, recent_attempts=recent,
                               velocity_threshold=settings.velocity_threshold)
    order.paypal_order_id = paypal_order_id
    db.add(Attempt(key=order.reference, outcome=verdict.status))
    return save_alert(db, "payment", order.id, verdict)


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/api/orders", dependencies=[Depends(require_key)], status_code=201)
def create_order(body: OrderIn, db: Session = Depends(get_session)):
    o = Order(reference=body.reference, amount=body.amount, currency=body.currency.upper(), payee_email=body.payee_email)
    db.add(o)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "La referencia ya existe")
    return order_dict(o)


@app.get("/api/orders", dependencies=[Depends(require_key)])
def list_orders(db: Session = Depends(get_session)):
    return [order_dict(o) for o in db.scalars(select(Order).order_by(Order.id.desc()))]


@app.post("/api/orders/{order_id}/verify", dependencies=[Depends(require_key)])
def verify_order(order_id: int, body: VerifyIn, db: Session = Depends(get_session),
                 pp: PayPalClient = Depends(get_paypal)):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(404, "Pedido no encontrado")
    return alert_dict(run_verification(db, order, body.paypal_order_id, pp))


@app.post("/api/analyze/message", dependencies=[Depends(require_key)])
def analyze(body: MessageIn, db: Session = Depends(get_session)):
    ai_sigs, _ = ai.analyze_text(body.text)
    v = build_verdict(analyze_message(body.text).signals + ai_sigs)
    return alert_dict(save_alert(db, "message", None, v))


@app.post("/api/analyze/screenshot", dependencies=[Depends(require_key)])
def analyze_screenshot(body: ScreenshotIn, db: Session = Depends(get_session)):
    if not ai.enabled():
        raise HTTPException(503, "El análisis de capturas requiere ANTHROPIC_API_KEY")
    try:
        base64.b64decode(body.image_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "Imagen base64 inválida")
    order = db.get(Order, body.order_id) if body.order_id else None
    text, ai_sigs, claims = ai.analyze_image(body.image_base64, body.media_type)
    sigs = analyze_message(text).signals if text else []
    sigs += ai_sigs
    # Una captura nunca prueba un pago: siempre exige verificar contra la API oficial.
    sigs.append(Signal("screenshot_not_proof", "low",
                       "Una captura no demuestra que exista un pago; verifícalo con la API de PayPal.", "internal_policy"))
    if not text and not ai_sigs:
        sigs.append(Signal("ai_unavailable", "info", "No se pudo analizar la imagen automáticamente.", "provider"))
    if order and claims.get("amount"):
        try:
            if Decimal(str(claims["amount"]).replace(",", ".")) != Decimal(str(order.amount)):
                sigs.append(Signal("screenshot_amount_mismatch", "medium",
                                   f"La captura indica {claims['amount']} pero el pedido espera {order.amount}.",
                                   "ai_analysis", {"claimed": str(claims["amount"]), "expected": str(order.amount)}))
        except Exception:
            pass
    return alert_dict(save_alert(db, "screenshot", order.id if order else None, build_verdict(sigs)))


@app.get("/api/alerts", dependencies=[Depends(require_key)])
def list_alerts(db: Session = Depends(get_session)):
    return [alert_dict(a) for a in db.scalars(select(Alert).order_by(Alert.id.desc()).limit(500))]


@app.patch("/api/alerts/{alert_id}", dependencies=[Depends(require_key)])
def review_alert(alert_id: int, body: ReviewIn, db: Session = Depends(get_session)):
    a = db.get(Alert, alert_id)
    if not a:
        raise HTTPException(404, "Alerta no encontrada")
    a.review_state, a.review_note = body.review_state, body.note
    db.commit()
    return alert_dict(a)


@app.post("/api/webhooks/paypal")
async def paypal_webhook(request: Request, db: Session = Depends(get_session),
                         pp: PayPalClient = Depends(get_paypal)):
    event = await request.json()
    headers = {k.lower(): v for k, v in request.headers.items()}
    # 1) Firma antes de cualquier acción de negocio
    if not pp.verify_webhook(headers, event):
        raise HTTPException(400, "Firma de webhook inválida")
    event_id = event.get("id")
    if not event_id:
        raise HTTPException(400, "Evento sin id")
    # 2) Idempotencia: la PK rechaza el segundo procesamiento
    db.add(WebhookEvent(event_id=event_id, event_type=event.get("event_type", "")))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return {"status": "duplicate"}
    # 3) Lógica de negocio
    resource = event.get("resource") or {}
    pp_order_id = ((resource.get("supplementary_data") or {}).get("related_ids") or {}).get("order_id") \
        or (resource.get("id") if str(event.get("event_type", "")).startswith("CHECKOUT.ORDER") else None)
    order = db.scalar(select(Order).where(Order.paypal_order_id == pp_order_id)) if pp_order_id else None
    if order:
        run_verification(db, order, pp_order_id, pp)
        return {"status": "processed"}
    return {"status": "ignored"}
