import { useCallback, useEffect, useMemo, useState } from "react";
import { AgGridReact } from "ag-grid-react";
import { api } from "./api";

const LABEL = { verified: "Verificado", review_required: "Revisión necesaria", high_risk: "Riesgo elevado" };
const KIND = { payment: "Pago", message: "Mensaje", screenshot: "Captura" };
const toB64 = (f) => new Promise((ok, no) => { const r = new FileReader(); r.onload = () => ok(String(r.result).split(",")[1]); r.onerror = no; r.readAsDataURL(f); });

function Badge({ status }) {
  return <span className={`badge ${status}`}>{LABEL[status] || status}</span>;
}

export default function App() {
  const [alerts, setAlerts] = useState([]);
  const [orders, setOrders] = useState([]);
  const [sel, setSel] = useState(null);
  const [err, setErr] = useState("");
  const [text, setText] = useState("");
  const [form, setForm] = useState({ reference: "", amount: "", currency: "EUR", payee_email: "" });
  const [ver, setVer] = useState({ order_id: "", paypal_order_id: "" });

  const load = useCallback(async () => {
    try { setAlerts(await api.alerts()); setOrders(await api.orders()); setErr(""); }
    catch (e) { setErr(e.message); }
  }, []);
  useEffect(() => { load(); }, [load]);
  const run = (fn) => async (e) => { e?.preventDefault(); try { setSel(await fn()); await load(); } catch (x) { setErr(x.message); } };

  const cols = useMemo(() => [
    { field: "id", width: 80 },
    { field: "kind", headerName: "Tipo", width: 110, valueFormatter: (p) => KIND[p.value] },
    { field: "status", headerName: "Estado", width: 190, cellRenderer: (p) => <Badge status={p.value} /> },
    { field: "score", headerName: "Prioridad", width: 120 },
    { field: "review_state", headerName: "Revisión", width: 120 },
    { field: "created_at", headerName: "Fecha", flex: 1, valueFormatter: (p) => new Date(p.value).toLocaleString() },
  ], []);

  return (
    <main>
      <h1>🛡️ TrustShield <small>PayPal Sandbox · MVP</small></h1>
      {err && <p className="err">{err}</p>}
      <section className="forms">
        <form onSubmit={run(() => api.createOrder({ ...form, amount: form.amount }).then(() => { setForm({ ...form, reference: "", amount: "" }); return null; }))}>
          <h3>1. Pedido esperado</h3>
          <input placeholder="Referencia" required value={form.reference} onChange={(e) => setForm({ ...form, reference: e.target.value })} />
          <input placeholder="Importe" required type="number" step="0.01" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} />
          <input placeholder="Moneda" maxLength={3} required value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value })} />
          <input placeholder="Email del vendedor (opcional)" value={form.payee_email} onChange={(e) => setForm({ ...form, payee_email: e.target.value })} />
          <button>Crear pedido</button>
        </form>
        <form onSubmit={run(() => api.verify(ver.order_id, ver.paypal_order_id))}>
          <h3>2. Verificar pago en PayPal</h3>
          <select required value={ver.order_id} onChange={(e) => setVer({ ...ver, order_id: e.target.value })}>
            <option value="">Pedido…</option>
            {orders.map((o) => <option key={o.id} value={o.id}>{o.reference} — {o.amount} {o.currency}</option>)}
          </select>
          <input placeholder="ID de orden PayPal" required value={ver.paypal_order_id} onChange={(e) => setVer({ ...ver, paypal_order_id: e.target.value })} />
          <button>Verificar con la API</button>
        </form>
        <form onSubmit={run(() => api.analyze(text))}>
          <h3>3. Analizar mensaje sospechoso</h3>
          <textarea rows={4} required placeholder="Pega el correo o mensaje…" value={text} onChange={(e) => setText(e.target.value)} />
          <button>Analizar texto</button>
          <span className="muted">…o sube una captura de un supuesto comprobante (análisis con IA; nunca es prueba de pago). Si eliges un pedido en el paso 2, se compara su importe.</span>
          <input type="file" accept="image/png,image/jpeg,image/gif,image/webp"
            onChange={async (e) => { const f = e.target.files[0]; if (!f) return;
              try { setSel(await api.screenshot(await toB64(f), f.type, ver.order_id)); await load(); } catch (x) { setErr(x.message); } e.target.value = ""; }} />
        </form>
      </section>
      <div className="split">
        <div className="ag-theme-quartz grid">
          <AgGridReact rowData={alerts} columnDefs={cols} rowSelection="single" animateRows
            onRowClicked={(e) => setSel(e.data)} defaultColDef={{ sortable: true, filter: true }} />
        </div>
        <aside>
          {!sel ? <p className="muted">Selecciona una alerta para ver la evidencia.</p> : (
            <>
              <h3>Alerta #{sel.id} <Badge status={sel.status} /></h3>
              {sel.explanation && <p className="ai">🤖 {sel.explanation}</p>}
              <p><b>Acción recomendada:</b> {sel.action}</p>
              <ul>
                {sel.signals.length === 0 && <li>Sin señales de riesgo. Una verificación positiva no garantiza ausencia de disputas.</li>}
                {sel.signals.map((s, i) => (
                  <li key={i}><span className={`sev ${s.severity}`}>{s.severity}</span> {s.message}
                    <div className="muted">fuente: {s.source}{Object.keys(s.evidence).length ? ` · ${JSON.stringify(s.evidence)}` : ""}</div></li>
                ))}
              </ul>
              <div className="actions">
                {["cleared", "confirmed", "open"].map((st) => (
                  <button key={st} className={sel.review_state === st ? "on" : ""} onClick={async () => { setSel(await api.review(sel.id, st)); load(); }}>
                    {{ cleared: "Descartar", confirmed: "Confirmar riesgo", open: "Reabrir" }[st]}
                  </button>))}
              </div>
              <p className="muted">Las alertas son indicadores de riesgo, no determinaciones de fraude.</p>
            </>)}
        </aside>
      </div>
      <footer>TrustShield es un proyecto independiente; no está avalado por PayPal.</footer>
    </main>
  );
}
