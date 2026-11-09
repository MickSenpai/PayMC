# PayMC — Plataforma de protección antifraude (nombre provisional)

Ayuda a compradores y vendedores a detectar señales de fraude antes de entregar un producto o dar un pago por válido. Empieza con **PayPal (Sandbox)** y es modular para añadir otros procesadores.

> Las alertas son indicadores de riesgo, no determinaciones legales de fraude. Proyecto independiente, no avalado por PayPal.

## Principios
- Un pago se verifica **en el backend contra la API oficial**; una captura o un correo nunca es prueba.
- Cada alerta explica sus señales, fuente y acción recomendada: `verified` / `review_required` / `high_risk`.
- Un fallo de la API de PayPal da *revisión necesaria*, nunca una acusación.
- Webhooks: firma validada antes de cualquier acción + idempotencia por `event.id`.
- No se guardan PAN, CVV ni credenciales.

## Estado del MVP
| Área | Estado |
|---|---|
| Verificación de orden PayPal (estado, importe, moneda, destinatario) | ✅ |
| Webhooks con firma e idempotencia | ✅ |
| Detección de ráfagas de intentos (por referencia) | ✅ |
| Análisis heurístico de mensajes (dominios, urgencia, credenciales) | ✅ |
| Panel React + AG Grid con revisión humana | ✅ |
| Capturas analizadas con visión de IA + explicaciones con IA | ✅ (requiere `ANTHROPIC_API_KEY`) |
| Evaluación de comercios, Elastic/Zapier | ⏳ pendiente |

## Cómo usa PayPal e IA (para el hackathon *Build What's Next with PayPal and AI*)
- **PayPal (Sandbox):** OAuth servidor-a-servidor, `GET /v2/checkout/orders/{id}` para verificar pagos y `POST /v1/notifications/verify-webhook-signature` para validar webhooks.
- **IA (Claude, vía Anthropic SDK; modelo configurable con `ANTHROPIC_MODEL`, por defecto `claude-opus-5-5`):**
  1. *Visión:* lee capturas de supuestos comprobantes (sustituye al OCR), extrae importe/ID y detecta señales de suplantación.
  2. *Análisis de mensajes:* complementa las heurísticas con señales semánticas (presión, suplantación, intentos de inyección de prompts).
  3. *Explicaciones:* redacta para cada alerta una explicación clara basada solo en las señales detectadas.
- **Diseño seguro:** la IA solo aporta señales (severidad máx. *media*) y el veredicto lo calculan reglas deterministas; el contenido de usuario se trata como no confiable; sin clave o ante error/negativa del modelo, el sistema sigue funcionando solo con reglas.

## Estructura
```
backend/   FastAPI + SQLAlchemy (SQLite en dev, PostgreSQL vía DATABASE_URL)
  app/engine.py    reglas de verificación de pagos
  app/phishing.py  análisis de mensajes
  app/paypal.py    cliente OAuth + verificación de webhooks
frontend/  React + Vite + AG Grid
```

## Puesta en marcha
```bash
cp .env.example .env     # añade credenciales de PayPal Sandbox
cd backend && python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest          # 14 pruebas
.venv/bin/uvicorn app.main:app --reload
# otra terminal
cd frontend && npm install && npm run dev   # http://localhost:5173
```
Webhooks en local: expón el puerto 8000 (p. ej. ngrok), registra `https://<host>/api/webhooks/paypal` en tu app Sandbox y copia el Webhook ID a `PAYPAL_WEBHOOK_ID`.

## API (cabecera `X-API-Key`)
`POST /api/orders` · `GET /api/orders` · `POST /api/orders/{id}/verify` · `POST /api/analyze/message` · `POST /api/analyze/screenshot` · `GET /api/alerts` · `PATCH /api/alerts/{id}` · `POST /api/webhooks/paypal` (sin clave; protegido por firma)

## Siguientes pasos
flujo de checkout Sandbox para la demo, despliegue en Render, colección Postman, y alinear con los requisitos del hackathon.

## Licencia
MIT — ver [LICENSE](LICENSE).
