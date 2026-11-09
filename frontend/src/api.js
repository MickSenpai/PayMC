const key = () => localStorage.getItem("ts_key") || "dev-key";
async function call(path, opts = {}) {
  const r = await fetch(path, {
    ...opts,
    headers: { "Content-Type": "application/json", "X-API-Key": key(), ...(opts.headers || {}) },
  });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `Error ${r.status}`);
  return r.json();
}
const post = (p, b) => call(p, { method: "POST", body: JSON.stringify(b) });
export const api = {
  alerts: () => call("/api/alerts"),
  orders: () => call("/api/orders"),
  createOrder: (b) => post("/api/orders", b),
  verify: (id, paypal_order_id) => post(`/api/orders/${id}/verify`, { paypal_order_id }),
  analyze: (text) => post("/api/analyze/message", { text }),
  screenshot: (image_base64, media_type, order_id) =>
    post("/api/analyze/screenshot", { image_base64, media_type, order_id: order_id ? Number(order_id) : null }),
  review: (id, review_state, note) =>
    call(`/api/alerts/${id}`, { method: "PATCH", body: JSON.stringify({ review_state, note }) }),
};
