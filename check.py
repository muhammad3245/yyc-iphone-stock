#!/usr/bin/env python3
"""Free iPhone 18 Pro / Pro Max Calgary pickup stock checker.

Polls Apple Canada's retail pickup API for Apple Chinook Centre (R209) and
Apple Market Mall (R301), posts ntfy alerts the moment a config goes from
unavailable -> available, and writes data.json for the GitHub Pages site.
Everything is free: GitHub Actions cron + Pages + ntfy.sh.
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
BUY_URL = "https://www.apple.com/ca/shop/buy-iphone/iphone-18-pro?partNumber={}"

def buy_link(part):
    return BUY_URL.format(urllib.request.quote(part, safe=""))
NTFY = os.environ.get("NTFY_TOPIC", "").strip()
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

def notify(title, lines):
    if not NTFY:
        print("NTFY_TOPIC not set; skipping:", title); return
    body = "\n".join(lines)
    req = urllib.request.Request(
        f"https://ntfy.sh/{NTFY}", data=body.encode("utf-8"),
        headers={"Title": title, "Priority": "high", "Tags": "iphone,rotating_light", "Markdown": "no"})
    with urllib.request.urlopen(req, timeout=30) as r:
        r.read()
    print("ntfy sent:", title)

def main():
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    state_path = os.path.join(HERE, "state.json")
    state = {"seen": {}, "lastRun": None}
    if os.path.exists(state_path):
        try: state = json.load(open(state_path))
        except Exception: pass
    seen = state.get("seen", {})

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

    alerts = []
    for part in all_parts:
        model, size, color = PART_META[part]
        for store in ok_stores:
            info = results[store].get(part)
            if not info: continue
            disp = info["display"]
            prev = (seen.setdefault(part, {})).get(store)
            if disp == "available" and prev != "available":
                seen[part][store] = "available"
                if model in ALERT_MODELS:
                    alerts.append((model, color, size, part, store, info["quote"]))
            elif disp in ("unavailable", "ineligible"):
                seen[part][store] = disp
            # unknown/error statuses are left untouched: a failed check must
            # never be recorded as "no stock"

    if alerts:
        by_store = {}
        for a in alerts: by_store.setdefault(a[4], []).append(a)
        for store, items in by_store.items():
            lines = []
            for model, color, size, part, _, quote in items:
                lines.append(f"iPhone {model.replace('iPhone ', '')} {size} {color} — {quote}")
                lines.append(f"Buy: {buy_link(part)}")
            lines.append("")
            lines.append(f"{STORES[store]['name']}, {STORES[store]['city']}")
            lines.append(f"https://www.apple.com/ca/retail/{STORES[store]['slug']}/")
            notify(f"In stock now at {STORES[store]['name']} ({len(items)} config{'s' if len(items) != 1 else ''})", lines)

    state["seen"] = seen
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
    data = {
        "updated": now,
        "ok": sorted(ok_stores),
        "alertModels": sorted(ALERT_MODELS),
        "stores": STORES,
        "items": grid,
        "freshAlerts": [list(a) for a in alerts],
    }
    json.dump(data, open(os.path.join(HERE, "data.json"), "w"), indent=1)
    print(f"done {now}: {len(alerts)} alert(s), stores ok: {sorted(ok_stores)}")

if __name__ == "__main__":
    sys.exit(main() or 0)
