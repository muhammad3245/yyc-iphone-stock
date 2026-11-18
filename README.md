# YYC iPhone Stock

Free, real-time iPhone 18 Pro / Pro Max pickup availability for the two Apple Stores
in Calgary, Alberta: **Apple Chinook Centre (R209)** and **Apple Market Mall (R301)**.

- **Site:** GitHub Pages (this repo, `index.html`) — zero cost, no backend.
- **Checker:** `check.py` runs on GitHub Actions every 5 minutes (free on public repos).
- **Alerts:** the moment any tracked configuration flips to *available* at either store,
  a push goes out over [ntfy.sh](https://ntfy.sh) (`NTFY_TOPIC` repo secret).

## How it works

Apple's old `/shop/fulfillment-messages` endpoint has been dead since mid-2026 (it now
returns HTTP 541 for every request). This project uses the endpoint Apple's own store
pages now call: `/shop/retail/pickup-message`, which accepts multiple part numbers per
request and answers with per-store `pickupDisplay` states.

A failed check is never recorded as "no stock" — unknown states leave the previous
state untouched, so a network blip can't hide a restock.

## Adding models or stores

Edit `PARTS` and `STORES` in `check.py`. Part numbers are the unlocked Canada
(`VC/A`) SKUs from apple.com/ca. Add `"iPhone 18 Pro"` to `ALERT_MODELS` to get
alerts for the Pro as well as the Pro Max.

## Cost

$0. GitHub Actions + GitHub Pages on a public repo, and ntfy's free tier.
