#!/usr/bin/env python3
"""Free iPhone 18 Pro / Pro Max Calgary pickup stock checker.

Polls Apple Canada's retail pickup API for Apple Chinook Centre (R209) and
Apple Market Mall (R301), posts ntfy alerts when a tracked config goes from
sold out to available (high priority) or from sold out to "Available
Tomorrow" (a softer heads-up), logs every status change and in-stock window
to history.json, and writes data.json for the GitHub Pages site. Everything
is free: GitHub Actions cron + Pages + ntfy.sh.
"""
import json, os, sys, time, urllib.request, urllib.error
from datetime import datetime, timezone

BASE = "https://www.apple.com/ca/shop/retail/pickup-message"
STORES = {
    "R209": {"name": "Apple Chinook Centre", "city": "Calgary", "slug": "chinookcentre"},
    "R301": {"name": "Apple Market Mall", "city": "Calgary", "slug": "marketmall"},
}
COLORS = ["Black", "Silver", "Glacier", "Burgundy"]
STORAGE = ["256GB", "512GB", "1TB", "2TB"]

# Unlocked Canada parts (apple.com/ca, suffix VC/A)
# Track list: currently only the iPhone 18 Pro Max 256GB Glacier (MJX84VC/A).
# To widen coverage, paste more SKU lines back in from apple.com/ca.
PARTS = {
    "iPhone 18 Pro Max": {
        "256GB": {"Glacier": "MJX84VC/A"},
    },
}
PART_META = {p: (m, s, c) for m, ss in PARTS.items() for s, cc in ss.items() for c, p in cc.items()}
ALERT_MODELS = {"iPhone 18 Pro Max"}
BUY_URL = "https://www.apple.com/ca/shop/buy-iphone/iphone-18-pro/6.9-inch-display-256gb-glacier?partNumber={}"

def buy_link(part):
    return BUY_URL.format(urllib.request.quote(part, safe=""))
NTFY = os.environ.get("NTFY_TOPIC", "").strip()
NTFY_EMAIL = os.environ.get("NTFY_EMAIL", "").strip()
NTFY_TOKEN = os.environ.get("NTFY_TOKEN", "").strip()
HERE = os.path.dirname(os.path.abspath(__file__))

def http(url, retries=3, data=None, headers=None):
    req = urllib.request.Request(url, headers=headers or {}, data=data)
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode()
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and i < retries - 1:
                time.sleep(5 * (i + 1)); continue
            raise
    raise RuntimeError("unreachable")

def fetch(store, parts):
    qs = "pl=true&mts.0=regular&location=Calgary&" + "&".join(
        f"parts.{i}={urllib.request.quote(p, safe='')}" for i, p in enumerate(parts))
    d = json.loads(http(f"{BASE}?{qs}", headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126 Safari/537.36"}))
    for s in d.get("body", {}).get("stores", []):
        if s.get("storeNumber") == store:
            out = {}
            for p, info in (s.get("partsAvailability") or {}).items():
                out[p] = {
                    "display": info.get("pickupDisplay", "unknown"),
                    "quote": info.get("pickupSearchQuote", ""),
                }
            return out
    raise RuntimeError(f"store {store} missing from response")

def notify(title, lines, priority="high", tags="iphone,rotating_light"):
    if not NTFY:
        print("NTFY_TOPIC not set; skipping:", title); return
    body = "\n".join(lines)
    req = urllib.request.Request(
        f"https://ntfy.sh/{NTFY}", data=body.encode("utf-8"),
        headers={"Title": title, "Priority": priority, "Tags": tags, "Markdown": "no"})
    with urllib.request.urlopen(req, timeout=30) as r:
        r.read()
    print("ntfy sent:", title)
    # Email backup: ntfy.sh only forwards mail for logged-in accounts with a
    # verified address, so this is best-effort and never blocks the push.
    if NTFY_EMAIL:
        try:
            eh = {"Title": title, "Email": NTFY_EMAIL}
            if NTFY_TOKEN:
                eh["Authorization"] = "Bearer " + NTFY_TOKEN
            req2 = urllib.request.Request(
                f"https://ntfy.sh/{NTFY}-email", data=body.encode("utf-8"), headers=eh)
            with urllib.request.urlopen(req2, timeout=30) as r:
                r.read()
            print("email backup sent:", title)
        except Exception as e:
            print("WARN email backup failed:", e, file=sys.stderr)

def cat(disp, quote):
    q = (quote or "").lower()
    if disp == "available":
        return "tomorrow" if "tomorrow" in q else "stock"
    if disp in ("unavailable", "ineligible"):
        return "out"
    return "unknown"

def load_json(path, default):
    try:
        with open(path) as f: return json.load(f)
    except Exception:
        return default

def main():
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    state_path = os.path.join(HERE, "state.json")
    hist_path = os.path.join(HERE, "history.json")
    state = load_json(state_path, {"seen": {}, "open": {}, "lastRun": None})
    seen = state.get("seen", {})
    open_w = state.get("open", {})
    # migrate legacy state entries ("available" strings) to the dict schema
    for part in seen:
        for store, v in list(seen[part].items()):
            if isinstance(v, str):
                seen[part][store] = {"d": v, "q": "", "legacy": True}
    history = load_json(hist_path, {"events": [], "windows": []})
    if "events" not in history: history["events"] = []
    if "windows" not in history: history["windows"] = []

    all_parts = list(PART_META)
    # Apple's pickup API caps ~16 part numbers per request, so chunk by model
    chunks = [[v for ss in PARTS[m].values() for v in ss.values()] for m in PARTS]
    results = {}           # part -> store -> {display, quote}
    ok_stores = set()
    for store in STORES:
        try:
            merged = {}
            for chunk in chunks:
                merged.update(fetch(store, chunk))
            results[store] = merged
            ok_stores.add(store)
        except Exception as e:
            print(f"WARN store {store} fetch failed: {e}", file=sys.stderr)
    if not ok_stores:
        print("All store fetches failed; keeping previous state, no notifications.", file=sys.stderr)
        return 1

    alerts, leads, events_new = [], [], []
    for part in all_parts:
        model, size, color = PART_META[part]
        label = f"{model} {size} {color}"
        for store in ok_stores:
            info = results[store].get(part)
            if not info: continue
            disp, quote = info["display"], info["quote"]
            cur_cat = cat(disp, quote)
            if cur_cat == "unknown":
                # unknown/error statuses are left untouched: a failed check
                # must never be recorded as "no stock"
                continue
            prev = seen.setdefault(part, {}).get(store)
            if prev is None or prev.get("legacy"):
                prev_cat = cur_cat      # first observation: log nothing
            else:
                prev_cat = cat(prev.get("d"), prev.get("q"))
            if cur_cat != prev_cat:
                events_new.append({"ts": now, "store": store, "storeName": STORES[store]["name"],
                                   "label": label, "from": prev_cat, "to": cur_cat, "quote": quote})
                if cur_cat == "stock":
                    open_w.setdefault(part, {})[store] = now
                    if model in ALERT_MODELS:
                        alerts.append((model, color, size, part, store, quote))
                if cur_cat == "tomorrow" and prev_cat in ("out", "unknown") and model in ALERT_MODELS:
                    leads.append((model, color, size, part, store, quote))
                if prev_cat == "stock" and cur_cat != "stock":
                    start = open_w.get(part, {}).pop(store, None)
                    if start:
                        mins = max(int((datetime.fromisoformat(now) - datetime.fromisoformat(start)).total_seconds() // 60), 0)
                        history["windows"].append({"store": store, "storeName": STORES[store]["name"],
                                                   "label": label, "start": start, "end": now, "minutes": mins})
            seen[part][store] = {"d": disp, "q": quote}

    for store, items in {a[4]: [x for x in alerts if x[4] == store] for a in alerts}.items():
        lines = []
        for model, color, size, part, _, quote in items:
            lines.append(f"iPhone {model.replace('iPhone ', '')} {size} {color} — {quote}")
            lines.append(f"Buy: {buy_link(part)}")
        lines.append("")
        lines.append(f"{STORES[store]['name']}, {STORES[store]['city']}")
        lines.append(f"https://www.apple.com/ca/retail/{STORES[store]['slug']}/")
        notify(f"In stock now at {STORES[store]['name']} ({len(items)} config{'s' if len(items) != 1 else ''})", lines)

    for store, items in {a[4]: [x for x in leads if x[4] == store] for a in leads}.items():
        lines = []
        for model, color, size, part, _, quote in items:
            lines.append(f"iPhone {model.replace('iPhone ', '')} {size} {color}")
            lines.append(f"Apple now shows '{quote}' at {STORES[store]['name']}")
            lines.append(f"Buy: {buy_link(part)}")
        lines.append("")
        lines.append("Not ready for today pickup yet — the in-stock push fires the moment it is.")
        notify(f"Heads-up: '{items[0][5]}' at {STORES[store]['name']}", lines, priority="default", tags="iphone,clock4")

    history["events"].extend(events_new)
    history["events"] = history["events"][-400:]
    history["windows"] = history["windows"][-60:]
    json.dump(history, open(hist_path, "w"), indent=1)

    state["seen"] = seen
    state["open"] = open_w
    state["lastRun"] = now
    json.dump(state, open(state_path, "w"), indent=1, sort_keys=True)

    # data.json for the site
    grid = []
    for part in all_parts:
        model, size, color = PART_META[part]
        grid.append({
                    "part": part, "model": model, "size": size, "color": color,
                    "stores": {s: ({"display": results[s][part]["display"], "quote": results[s][part]["quote"]}
                               if part in results[s] else {"display": "unknown", "quote": ""}) for s in results},
                })
    last_stock = {}
    for store in STORES:
        last = None
        for w in history["windows"]:
            if w["store"] == store and (last is None or w["end"] > last):
                last = w["end"]
        for part in open_w:
            ts = open_w[part].get(store)
            if ts and (last is None or ts > last):
                last = ts
        last_stock[store] = last
    data = {
        "updated": now,
        "ok": sorted(ok_stores),
        "alertModels": sorted(ALERT_MODELS),
        "stores": STORES,
        "items": grid,
        "freshAlerts": [list(a) for a in alerts],
        "lastStock": last_stock,
        "history": {"events": history["events"][-60:], "windows": history["windows"][-20:]},
    }
    json.dump(data, open(os.path.join(HERE, "data.json"), "w"), indent=1)
    print(f"done {now}: {len(alerts)} alert(s), {len(leads)} lead(s), {len(events_new)} change(s), stores ok: {sorted(ok_stores)}")

if __name__ == "__main__":
    sys.exit(main() or 0)
