#!/usr/bin/env python3
"""
ARC Occupancy Logger
--------------------
Fetches the UC Davis live facility occupancy page, parses every zone's
current/max count, and appends one timestamped row per zone to a CSV.

Run it on a schedule (every ~10 min). Over weeks this becomes the
historical dataset the official page never stores.

Usage:
    python3 arc_logger.py
    python3 arc_logger.py --once       # single capture, then exit
    python3 arc_logger.py --csv path   # custom output file

Auth note:
    If the occupancy page is PUBLIC (loads in incognito), no cookie needed.
    If it requires sign-in, set the COOKIE env var to your session cookie
    (see README notes) and the script will send it.
"""

import argparse
import csv
import os
import re
import sys
from datetime import datetime

import requests

URL = "https://rec.ucdavis.edu/FacilityOccupancy"
DEFAULT_CSV = "arc_occupancy.csv"
FIELDNAMES = [
    "timestamp",      # ISO8601 local time of capture
    "facility_id",    # stable GUID from the page
    "facility_name",  # human-readable zone name
    "current",        # current occupancy
    "maximum",        # max occupancy
    "remaining",      # spots left
    "pct_full",       # current / maximum, rounded to 1 decimal
    "page_last_update",  # the "last update" time the page itself reports
]

# Matches each facility block. The page wraps each zone in a div carrying
# data-facilityid, with an <h2><strong>NAME</strong></h2> and a <canvas>
# carrying data-occupancy / data-remaining. We capture them together.
FACILITY_RE = re.compile(
    r'data-facilityid="(?P<fid>[0-9a-f\-]{36})".*?'      # facility GUID
    r'<strong>(?P<name>[^<]+)</strong>.*?'               # zone name
    r'data-occupancy="(?P<occ>\d+)"\s+'                  # current count
    r'data-remaining="(?P<rem>\d+)"',                    # remaining
    re.DOTALL,
)

LAST_UPDATE_RE = re.compile(r'id="last-update">([^<]+)<')


def fetch_html(session):
    headers = {
        "User-Agent": "Mozilla/5.0 (occupancy-logger; personal project)"
    }
    cookie = os.environ.get("COOKIE", "").strip()
    if cookie:
        headers["Cookie"] = cookie
    resp = session.get(URL, headers=headers, timeout=20)
    resp.raise_for_status()
    return resp.text


def parse(html):
    page_update_match = LAST_UPDATE_RE.search(html)
    page_update = page_update_match.group(1).strip() if page_update_match else ""

    rows = []
    seen = set()
    for m in FACILITY_RE.finditer(html):
        fid = m.group("fid")
        if fid in seen:          # the page renders desktop + mobile copies;
            continue             # dedupe so we only log each zone once
        seen.add(fid)
        current = int(m.group("occ"))
        remaining = int(m.group("rem"))
        maximum = current + remaining
        pct = round(current / maximum * 100, 1) if maximum else 0.0
        rows.append({
            "facility_id": fid,
            "facility_name": m.group("name").strip(),
            "current": current,
            "maximum": maximum,
            "remaining": remaining,
            "pct_full": pct,
            "page_last_update": page_update,
        })
    return rows


def append_rows(csv_path, rows):
    new_file = not os.path.exists(csv_path)
    ts = datetime.now().isoformat(timespec="seconds")
    with open(csv_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if new_file:
            writer.writeheader()
        for r in rows:
            r = {"timestamp": ts, **r}
            writer.writerow(r)
    return ts


def capture_once(session, csv_path, verbose=True):
    try:
        html = fetch_html(session)
    except Exception as e:
        print(f"[{datetime.now():%H:%M:%S}] FETCH ERROR: {e}", file=sys.stderr)
        return False

    rows = parse(html)
    if not rows:
        # Either the page changed shape, or we got a sign-in page (no zones).
        signed_out = "account/signin" in html and "occupancy-card" not in html
        reason = "looks like a sign-in page (need COOKIE?)" if signed_out \
            else "no facility blocks found (page markup may have changed)"
        print(f"[{datetime.now():%H:%M:%S}] NO DATA PARSED — {reason}",
              file=sys.stderr)
        return False

    ts = append_rows(csv_path, rows)
    if verbose:
        print(f"[{ts}] logged {len(rows)} zones -> {csv_path}")
        for r in rows:
            bar = "#" * int(r["pct_full"] / 5)
            print(f"    {r['facility_name']:<18} "
                  f"{r['current']:>4}/{r['maximum']:<5} "
                  f"{r['pct_full']:>5}%  {bar}")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true",
                    help="capture a single sample and exit")
    ap.add_argument("--csv", default=DEFAULT_CSV, help="output CSV path")
    ap.add_argument("--interval", type=int, default=600,
                    help="seconds between samples in loop mode (default 600)")
    args = ap.parse_args()

    session = requests.Session()

    if args.once:
        ok = capture_once(session, args.csv)
        sys.exit(0 if ok else 1)

    # Loop mode (Ctrl+C to stop). For real deployment, prefer cron instead
    # — see README — but this is handy for testing.
    import time
    print(f"Logging every {args.interval}s. Ctrl+C to stop.")
    try:
        while True:
            capture_once(session, args.csv)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
