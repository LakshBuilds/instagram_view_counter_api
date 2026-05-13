#!/usr/bin/env python3
"""
Sync payment-tracking Google Sheet → Supabase `reels` table.

Reads the team's "Payment Conformation" sheet (April + May worksheets), filters
to rows from the last N days, then for each row:

  - If column O has an Instagram reel URL and N doesn't say "bonus":
      → upsert into reels table with:
          permalink   = column O (cleaned)
          shortcode   = parsed from URL
          ownerusername = column A
          payout      = column E
          created_by_email = "<handler>@buyhatke.com"  (lowercased from K)
          created_by_name  = column K
          locationname = column L (POC name)

  - If N mentions "bonus" (case-insensitive):
      → find existing reel for that ownerusername (most recent match) and ADD
        the column E amount to its `payout`. Doesn't create a new row.

  - If O is empty AND it's not a bonus: skip (story promotion / non-reel expense).

Run dry-run (default — prints actions, doesn't touch DB):
    python3 scripts/sync_sheet_to_supabase.py

Apply for real (requires SUPABASE_SERVICE_ROLE_KEY in env):
    SUPABASE_SERVICE_ROLE_KEY=eyJ... python3 scripts/sync_sheet_to_supabase.py --apply

Override window (default 21 days):
    python3 scripts/sync_sheet_to_supabase.py --days 14
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

import gspread
from dotenv import load_dotenv

# load .env from project root (parent of scripts/)
HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(os.path.dirname(HERE), ".env"))

SERVICE_ACCOUNT_JSON = os.environ.get(
    "GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON",
    os.path.expanduser("~/google_service_account.json"),
)
# Fall back to the Mac dev path if the env-default isn't present
if not os.path.exists(SERVICE_ACCOUNT_JSON):
    mac_default = "/Users/buyhatke/Downloads/third-zephyr-483123-n7-f309dde8fb0a.json"
    if os.path.exists(mac_default):
        SERVICE_ACCOUNT_JSON = mac_default
SHEET_URL = "https://docs.google.com/spreadsheets/d/1dbXp9qvp2ul1CJiwu7-CrmQ4PQ6oFzcgqqKNKoYMfZM/edit"

SUPABASE_URL = os.environ.get("VITE_SUPABASE_URL") or os.environ.get("SUPABASE_URL")
SUPABASE_KEY = (
    os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    or os.environ.get("VITE_SUPABASE_PUBLISHABLE_KEY")
    or os.environ.get("SUPABASE_KEY")
)

# Normalize team-member name variants → canonical lowercase email local-part
HANDLER_NORMALIZE = {
    "gurimar": "gurnimar",          # typo seen in sheet
    "muskan": "muskan",
    "yash": "yash",
    "rajoshree": "rajoshree",
    "chirag": "chirag",
    "mansoor": "mansoor",
    "laksh": "laksh",
}


def handler_to_email(handler: str) -> Optional[str]:
    if not handler:
        return None
    key = handler.strip().lower().replace(" ", "")
    canon = HANDLER_NORMALIZE.get(key, key)
    if not canon.replace("_", "").isalnum():
        return None
    return f"{canon}@buyhatke.com"


SHORTCODE_RE = re.compile(
    r"instagram\.com/(?:[^/]+/)?(?:reels?|p)/([A-Za-z0-9_-]+)"
)


def parse_reel_url(raw: str) -> tuple[Optional[str], Optional[str]]:
    """Returns (clean_url, shortcode) or (None, None) if not a valid reel link."""
    if not raw or "instagram.com" not in raw:
        return None, None
    m = SHORTCODE_RE.search(raw.strip())
    if not m:
        return None, None
    sc = m.group(1)
    return f"https://www.instagram.com/reel/{sc}/", sc


# Match "1 April", "1st April", "1st april", "12th arpil" (typo), etc.
DAY_RE = re.compile(r"(\d{1,2})")
MONTH_NAMES = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4, "arpil": 4,  # arpil typo seen in sheet
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}


def parse_sheet_date(raw: str, default_year: int = None) -> Optional[datetime]:
    if not raw:
        return None
    s = raw.strip().lower()
    day_m = DAY_RE.search(s)
    if not day_m:
        return None
    day = int(day_m.group(1))
    month = None
    for name, num in MONTH_NAMES.items():
        if name in s:
            month = num
            break
    if not month:
        return None
    year = default_year or datetime.utcnow().year
    try:
        return datetime(year, month, day)
    except ValueError:
        return None


def parse_amount(raw: str) -> int:
    if not raw:
        return 0
    digits = "".join(c for c in str(raw) if c.isdigit())
    return int(digits) if digits else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Actually write to Supabase. Default: dry-run.")
    ap.add_argument("--days", type=int, default=21, help="Window of days back to sync (default 21 = 3 weeks)")
    args = ap.parse_args()

    cutoff = datetime.utcnow() - timedelta(days=args.days)
    print(f"📅 Including rows dated >= {cutoff.date()} (last {args.days} days)\n")

    gc = gspread.service_account(filename=SERVICE_ACCOUNT_JSON)
    sh = gc.open_by_url(SHEET_URL)

    all_rows = []  # (worksheet, row_num, row_data, date_obj)
    for ws_name in ("April", "May"):
        try:
            ws = sh.worksheet(ws_name)
        except gspread.WorksheetNotFound:
            continue
        rows = ws.get_all_values()
        for i, r in enumerate(rows[1:], start=2):  # skip header row
            if not any(r):
                continue
            date_str = r[7] if len(r) > 7 else ""
            dt = parse_sheet_date(date_str)
            if not dt or dt < cutoff:
                continue
            all_rows.append((ws_name, i, r, dt))
    print(f"🗂  {len(all_rows)} rows in window across April + May sheets\n")

    new_reels = []      # rows that create/update a reel record
    bonus_payments = [] # rows that bump an existing reel's payout
    skipped = []        # rows skipped (non-reel / no handler / etc.)

    for ws_name, row_num, r, dt in all_rows:
        username = (r[0] if len(r) > 0 else "").strip()
        payment = parse_amount(r[4] if len(r) > 4 else "")
        handler = (r[10] if len(r) > 10 else "").strip()
        poc = (r[11] if len(r) > 11 else "").strip()
        details = (r[13] if len(r) > 13 else "").strip()
        reel_raw = (r[14] if len(r) > 14 else "").strip()
        url, shortcode = parse_reel_url(reel_raw)
        email = handler_to_email(handler)
        is_bonus = "bonus" in details.lower()
        is_payment_done = "done" in (r[9] if len(r) > 9 else "").strip().lower()

        if not is_payment_done:
            skipped.append((ws_name, row_num, "Payment confirmation NOT done"))
            continue
        if not email:
            skipped.append((ws_name, row_num, f"Unknown handler {handler!r}"))
            continue

        if is_bonus:
            if not username:
                skipped.append((ws_name, row_num, "Bonus row missing ownerusername"))
                continue
            bonus_payments.append({
                "ws": ws_name, "row": row_num, "username": username,
                "amount": payment, "handler": handler, "email": email,
                "note": details, "matched_shortcode": shortcode,
            })
        elif url:
            new_reels.append({
                "ws": ws_name, "row": row_num, "username": username,
                "url": url, "shortcode": shortcode, "payout": payment,
                "handler": handler, "email": email, "poc": poc,
                "date": dt.date().isoformat(),
            })
        else:
            skipped.append((ws_name, row_num, "No reel URL (likely story promo / non-reel expense)"))

    print(f"📝 New reels to upsert : {len(new_reels)}")
    print(f"💰 Bonus payments      : {len(bonus_payments)}")
    print(f"⏭  Skipped             : {len(skipped)}\n")

    if new_reels:
        print("--- sample new reels (first 5) ---")
        for r in new_reels[:5]:
            print(f"  {r['ws']}:{r['row']:>3}  {r['shortcode']:14s}  @{r['username']:18s}  ₹{r['payout']:>5}  → {r['email']}")
    if bonus_payments:
        print("\n--- bonus payments (all) ---")
        for r in bonus_payments:
            print(f"  {r['ws']}:{r['row']:>3}  @{r['username']:18s}  +₹{r['amount']:>4}  → {r['email']}  ({r['note'][:50]!r})")

    if not args.apply:
        print("\n💡 Dry-run only. Re-run with --apply to send to PR-team server.")
        print(f"   Requires IMPORT_API_URL (default: https://instagram-pr-team.onrender.com)")
        print(f"   Optional: IMPORT_REELS_TOKEN if the server requires it")
        return

    # --- APPLY PATH: POST to the instagram_Pr_team Render server ---
    # Reels go through the project's own /api/import-reels endpoint, which uses the
    # server's service-role Supabase client to write — same code path as the dashboard's
    # native imports, and auto-tracks each URL for the upstream daily refresh.
    import urllib.request, urllib.error
    IMPORT_API_URL = os.environ.get("IMPORT_API_URL", "https://instagram-pr-team.onrender.com")
    IMPORT_TOKEN = os.environ.get("IMPORT_REELS_TOKEN", "")
    print(f"\n🚀 Applying via {IMPORT_API_URL}/api/import-reels …")

    def _post(path: str, body: dict) -> dict:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            f"{IMPORT_API_URL}{path}", data=data, method="POST",
            headers={"Content-Type": "application/json",
                     **({"X-Import-Token": IMPORT_TOKEN} if IMPORT_TOKEN else {})}
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return {"error": f"HTTP {e.code}: {e.read().decode('utf-8', errors='ignore')[:300]}"}
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"}

    # Send reels in batches of 50 to avoid timeouts
    import json
    BATCH = 50
    inserted = updated = bonus_applied = errors = 0
    for i in range(0, len(new_reels), BATCH):
        batch = new_reels[i:i+BATCH]
        body = {"reels": [
            {
                "url": r["url"], "shortcode": r["shortcode"], "ownerusername": r["username"],
                "payout": r["payout"], "created_by_email": r["email"],
                "created_by_name": r["handler"], "locationname": r["poc"] or None,
            }
            for r in batch
        ]}
        result = _post("/api/import-reels", body)
        if result.get("error"):
            errors += len(batch)
            print(f"   ⚠️  batch {i // BATCH + 1}: {result['error']}")
            continue
        inserted += result.get("inserted", 0)
        updated += result.get("updated", 0)
        errors += result.get("errors", 0)
        print(f"   batch {i // BATCH + 1}: +{result.get('inserted',0)} ins / +{result.get('updated',0)} upd / {result.get('errors',0)} err")

    if bonus_payments:
        body = {"bonuses": [
            {"ownerusername": b["username"], "amount": b["amount"],
             "shortcode": b["matched_shortcode"]} for b in bonus_payments
        ]}
        result = _post("/api/apply-bonuses", body)
        if result.get("error"):
            print(f"   ⚠️  bonuses: {result['error']}")
            errors += len(bonus_payments)
        else:
            bonus_applied = result.get("applied", 0)
            errors += result.get("errors", 0)
            print(f"   bonuses: +{bonus_applied} applied, {result.get('missing',0)} missing match")

    print(f"\n✅ Done: inserted={inserted}, updated={updated}, bonus_applied={bonus_applied}, errors={errors}")


if __name__ == "__main__":
    main()
