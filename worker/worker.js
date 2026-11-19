// Free iPhone 18 Pro Max 256GB Glacier Calgary pickup stock checker.
// Runs every 2 minutes on a Cloudflare Cron Trigger, keeps state in Workers KV,
// pushes ntfy alerts, and (when the email secret is set) emails a backup copy.
// GET /data returns the live snapshot JSON for the GitHub Pages site.
const PART = {
  part: "MJX84VC/A", model: "iPhone 18 Pro Max", size: "256GB", color: "Glacier",
  label: "iPhone 18 Pro Max 256GB Glacier",
};
const STORES = {
  R209: { name: "Apple Chinook Centre", city: "Calgary", slug: "chinookcentre" },
  R301: { name: "Apple Market Mall", city: "Calgary", slug: "marketmall" },
};
const BUY = "https://www.apple.com/ca/shop/buy-iphone/iphone-18-pro/6.9-inch-display-256gb-glacier?partNumber=MJX84VC%2FA";
const UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126 Safari/537.36";

function cat(disp, quote) {
  const q = (quote || "").toLowerCase();
  if (disp === "available") return q.includes("tomorrow") ? "tomorrow" : "stock";
  if (disp === "unavailable" || disp === "ineligible") return "out";
  return "unknown";
}

async function fetchStore(store) {
  const url = "https://www.apple.com/ca/shop/retail/pickup-message?pl=true&mts.0=regular&location=Calgary&parts.0=" + encodeURIComponent(PART.part);
  const r = await fetch(url, { headers: { "User-Agent": UA } });
  if (!r.ok) throw new Error("apple api " + r.status);
  const d = await r.json();
  const s = (d.body && d.body.stores || []).find(x => x.storeNumber === store);
  if (!s) throw new Error("store missing");
  const info = (s.partsAvailability || {})[PART.part] || {};
  return { display: info.pickupDisplay || "unknown", quote: info.pickupSearchQuote || "" };
}

const SITE = "https://iphone-stock-checker.hussnain-checker.workers.dev";
const esc = (t) => String(t).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

function emailHtml(title, opts) {
  const pill = opts.kind === "stock"
    ? '<span style="display:inline-block;padding:6px 14px;border-radius:999px;background:#ecfdf5;color:#059669;font-weight:600;font-size:13px;">&#9679;&nbsp; In stock now</span>'
    : '<span style="display:inline-block;padding:6px 14px;border-radius:999px;background:#fffbeb;color:#b45309;font-weight:600;font-size:13px;">&#9679;&nbsp; Heads-up</span>';
  const st = STORES[opts.store] || {};
  const quotes = (opts.items || []).map((a) =>
    '<div style="color:#6b7280;font-size:14px;margin-top:8px;">' + esc(a.quote) + "</div>").join("");
  const localTime = (() => { try {
    return new Intl.DateTimeFormat("en-CA", { timeZone: "America/Edmonton", weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", hour12: true }).format(new Date());
  } catch (e) { return new Date().toISOString(); } })();
  const primary = opts.kind === "stock" ? BUY : SITE;
  const primaryLabel = opts.kind === "stock" ? "Buy at Apple" : "Open the checker";
  return '<!DOCTYPE html><html><body style="margin:0;padding:0;background:#ffffff;">'
    + '<div style="display:none;max-height:0;overflow:hidden;">' + esc(title) + "</div>"
    + '<div style="margin:0 auto;max-width:560px;padding:28px 22px 34px;font-family:Poppins,Inter,\'Segoe UI\',Helvetica,Arial,sans-serif;">'
    + '<div style="margin-bottom:14px;"><span style="display:inline-block;width:12px;height:12px;background:#0a0a0a;"></span>'
    + '<span style="display:inline-block;width:12px;height:12px;background:#6ee7b7;margin-left:4px;"></span>'
    + '<span style="color:#6b7280;font-size:12px;letter-spacing:.12em;text-transform:uppercase;margin-left:10px;">YYC iPhone stock checker</span></div>'
    + '<div style="font-family:Poppins,\'Segoe UI\',Helvetica,Arial,sans-serif;font-weight:800;font-size:26px;line-height:1.15;letter-spacing:-0.02em;color:#0a0a0a;">' + esc(title) + "</div>"
    + '<div style="margin-top:10px;"><span style="display:inline-block;width:14px;height:14px;border-radius:4px;vertical-align:-2px;margin-right:8px;border:1px solid rgba(0,0,0,.12);background:#cfe6ee;"></span>'
    + '<span style="color:#0a0a0a;font-size:14px;font-weight:600;">' + esc(PART.label) + "</span></div>"
    + '<table width="100%" style="border-collapse:separate;border-spacing:0;margin-top:20px;"><tr><td style="border:1px solid #e5e7eb;border-radius:16px;padding:18px 20px;">'
    + '<div style="font-size:17px;font-weight:600;color:#0a0a0a;">' + esc(st.name || opts.store) + "</div>"
    + '<div style="color:#6b7280;font-size:13px;margin-top:2px;">' + esc(st.city || "Calgary") + ", Alberta</div>"
    + '<div style="margin-top:12px;">' + pill + "</div>" + quotes
    + '<div style="margin-top:16px;"><a href="https://www.apple.com/ca/retail/' + (st.slug || "") + '" style="color:#0a0a0a;font-size:13px;font-weight:600;text-decoration:underline;">Store page &rarr;</a></div>'
    + "</td></tr></table>"
    + '<div style="margin-top:22px;">'
    + '<a href="' + primary + '" style="display:inline-block;background:#0a0a0a;color:#ffffff;padding:11px 20px;border-radius:999px;font-size:13px;font-weight:600;text-decoration:none;">' + primaryLabel + "</a>"
    + '<a href="' + SITE + '" style="display:inline-block;background:#ffffff;border:1px solid #e5e7eb;color:#0a0a0a;padding:10px 20px;border-radius:999px;font-size:13px;font-weight:600;text-decoration:none;margin-left:8px;">Open the checker</a>'
    + "</div>"
    + '<div style="margin-top:30px;padding-top:16px;border-top:1px solid #e5e7eb;color:#6b7280;font-size:12px;line-height:1.7;">'
    + "Email backup of your stock push &middot; sent " + esc(localTime) + " Calgary time<br>"
    + "Alerts fire the moment " + esc(PART.label) + " flips to in stock at Chinook Centre or Market Mall."
    + "</div></div></body></html>";
}

async function notify(env, title, lines, priority, tags, opts) {
  const body = lines.join("\n");
  try {
    // new topic plus the old one so nothing is missed while switching apps
    await fetch("https://ntfy.sh/" + env.NTFY_TOPIC, {
      method: "POST", body,
      headers: { "Title": title, "Priority": priority, "Tags": tags },
    });
    console.log("ntfy sent:", title);
    try {
      await fetch("https://ntfy.sh/yycCalgaryiphone18pmstockcheckerglacier", {
        method: "POST", body,
        headers: { "Title": title + " (old topic)", "Priority": priority, "Tags": tags },
      });
      console.log("ntfy sent (legacy topic):", title);
    } catch (e) { console.log("WARN legacy ntfy failed:", e.message); }
  } catch (e) { console.log("WARN ntfy failed:", e.message); }
  if (env.RESEND_API_KEY && env.EMAIL_TO) {
    try {
      const payload = {
        from: "YYC iPhone Stock <onboarding@resend.dev>",
        to: [env.EMAIL_TO],
        subject: title,
        text: body,
      };
      if (opts) payload.html = emailHtml(title, opts);
      const r = await fetch("https://api.resend.com/emails", {
        method: "POST",
        headers: { "Authorization": "Bearer " + env.RESEND_API_KEY, "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      console.log("email backup:", r.ok ? "sent" : "rejected " + r.status);
    } catch (e) { console.log("WARN email backup failed:", e.message); }
  }
}
async function check(env) {
  const now = new Date().toISOString().slice(0, 19) + "+00:00";
  const results = {};
  const ok = [];
  for (const store of Object.keys(STORES)) {
    try { results[store] = await fetchStore(store); ok.push(store); }
    catch (e) { console.log("WARN store", store, "failed:", e.message); }
  }
  if (!ok.length) { console.log("all fetches failed; keeping state"); return; }

  const state = (await env.STOCK.get("state", "json")) || { seen: {}, open: {} };
  const history = (await env.STOCK.get("history", "json")) || { events: [], windows: [] };
  const events = [], alerts = [], leads = [];

  for (const store of ok) {
    const { display, quote } = results[store];
    const cur = cat(display, quote);
    if (cur === "unknown") continue; // never record a failed check as no stock
    const prev = state.seen[store];
    const prevCat = prev ? cat(prev.d, prev.q) : cur;
    if (cur !== prevCat) {
      events.push({ ts: now, store, storeName: STORES[store].name, label: PART.label, from: prevCat, to: cur, quote });
      if (cur === "stock") {
        state.open[store] = now;
        alerts.push({ store, quote });
      }
      if (cur === "tomorrow" && (prevCat === "out" || prevCat === "unknown")) leads.push({ store, quote });
      if (prevCat === "stock" && cur !== "stock" && state.open[store]) {
        const start = state.open[store];
        const mins = Math.max(Math.round((Date.parse(now) - Date.parse(start)) / 60000), 0);
        history.windows.push({ store, storeName: STORES[store].name, label: PART.label, start, end: now, minutes: mins });
        delete state.open[store];
      }
    }
    state.seen[store] = { d: display, q: quote };
  }

  for (const store of [...new Set(alerts.map(a => a.store))]) {
    const items = alerts.filter(a => a.store === store);
    const lines = items.map(a => PART.label + " — " + a.quote + "\nBuy: " + BUY);
    lines.push("", STORES[store].name + ", " + STORES[store].city, "https://www.apple.com/ca/retail/" + STORES[store].slug + "/");
    await notify(env, "In stock now at " + STORES[store].name + (items.length > 1 ? " (" + items.length + " configs)" : ""), lines, "high", "iphone,rotating_light", { kind: "stock", store, items });
  }
  for (const store of [...new Set(leads.map(a => a.store))]) {
    const items = leads.filter(a => a.store === store);
    const lines = items.map(a => PART.label + "\nApple now shows '" + a.quote + "' at " + STORES[store].name + "\nBuy: " + BUY);
    lines.push("", "Not ready for today pickup yet — the in-stock push fires the moment it is.");
    await notify(env, "Heads-up: '" + items[0].quote + "' at " + STORES[store].name, lines, "default", "iphone,clock4", { kind: "lead", store, items });
  }

  history.events = history.events.concat(events).slice(-400);
  history.windows = history.windows.slice(-60);

  const lastStock = {};
  for (const store of Object.keys(STORES)) {
    let last = null;
    for (const w of history.windows) if (w.store === store && (!last || w.end > last)) last = w.end;
    for (const s of Object.keys(state.open)) if (s === store && (!last || state.open[s] > last)) last = state.open[s];
    lastStock[store] = last;
  }
  const snapshot = {
    updated: now, ok, alertModels: ["iPhone 18 Pro Max"], stores: STORES,
    items: [{ part: PART.part, model: PART.model, size: PART.size, color: PART.color, stores: results }],
    lastStock,
    history: { events: history.events.slice(-60), windows: history.windows.slice(-20) },
  };
  // Write only when something changed, or every 5 minutes to refresh the
  // "last checked" stamp. Keeps KV writes far under the free-plan daily cap.
  const prev = await env.STOCK.get("snapshot", "json");
  const core = (o) => { if (!o) return ""; const { updated, ...r } = o; return JSON.stringify(r); };
  const changed = core(prev) !== core(snapshot);
  const age = prev ? Date.now() - Date.parse(prev.updated) : Infinity;
  if (changed || age > 5 * 60 * 1000) {
    await env.STOCK.put("state", JSON.stringify(state));
    await env.STOCK.put("history", JSON.stringify(history));
    await env.STOCK.put("snapshot", JSON.stringify(snapshot));
  }
  console.log("done", now, "alerts:", alerts.length, "leads:", leads.length);
}

export default {
  async scheduled(controller, env, ctx) { ctx.waitUntil(check(env)); },
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/data") {
      const snap = (await env.STOCK.get("snapshot")) || JSON.stringify({ updated: null, ok: [], stores: STORES, items: [], lastStock: {}, history: { events: [], windows: [] } });
      return new Response(snap, { headers: { "content-type": "application/json; charset=utf-8", "access-control-allow-origin": "*", "cache-control": "no-store" } });
    }
    return new Response("GET /data for the live JSON\n", { headers: { "content-type": "text/plain; charset=utf-8" } });
  },
};
