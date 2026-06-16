#!/usr/bin/env python3
"""
ARC Occupancy Logger (with weather)
-----------------------------------
Fetches UC Davis live facility occupancy + current Davis weather,
appends one timestamped row per zone to a CSV.

Weather via Open-Meteo (no API key needed).
"""

import argparse, csv, os, re, sys
from datetime import datetime
import requests

URL = "https://rec.ucdavis.edu/FacilityOccupancy"
# Davis, CA coordinates
WEATHER_URL = ("https://api.open-meteo.com/v1/forecast"
               "?latitude=38.5449&longitude=-121.7405"
               "&current=temperature_2m,precipitation,weather_code"
               "&temperature_unit=fahrenheit")
DEFAULT_CSV = "arc_occupancy.csv"
FIELDNAMES = [
    "timestamp", "facility_id", "facility_name",
    "current", "maximum", "remaining", "pct_full", "page_last_update",
    "temp_f", "precip", "weather_code",   # NEW weather columns
]

FACILITY_RE = re.compile(
    r'data-facilityid="(?P<fid>[0-9a-f\-]{36})".*?'
    r'<strong>(?P<name>[^<]+)</strong>.*?'
    r'data-occupancy="(?P<occ>\d+)"\s+'
    r'data-remaining="(?P<rem>\d+)"',
    re.DOTALL,
)
LAST_UPDATE_RE = re.compile(r'id="last-update">([^<]+)<')


def fetch_weather():
    """Grab current Davis weather. Returns dict; blanks if it fails."""
    try:
        r = requests.get(WEATHER_URL, timeout=15)
        r.raise_for_status()
        cur = r.json().get("current", {})
        return {
            "temp_f": cur.get("temperature_2m", ""),
            "precip": cur.get("precipitation", ""),
            "weather_code": cur.get("weather_code", ""),
        }
    except Exception as e:
        print(f"[weather] failed: {e}", file=sys.stderr)
        return {"temp_f": "", "precip": "", "weather_code": ""}


def fetch_html(session):
    headers = {"User-Agent": "Mozilla/5.0 (occupancy-logger; personal project)"}
    cookie = os.environ.get("COOKIE", "").strip()
    if cookie:
        headers["Cookie"] = cookie
    resp = session.get(URL, headers=headers, timeout=20)
    resp.raise_for_status()
    return resp.text


def parse(html):
    pm = LAST_UPDATE_RE.search(html)
    page_update = pm.group(1).strip() if pm else ""
    rows, seen = [], set()
    for m in FACILITY_RE.finditer(html):
        fid = m.group("fid")
        if fid in seen:
            continue
        seen.add(fid)
        cur = int(m.group("occ"))
        rem = int(m.group("rem"))
        mx = cur + rem
        rows.append({
            "facility_id": fid,
            "facility_name": m.group("name").strip(),
            "current": cur, "maximum": mx, "remaining": rem,
            "pct_full": round(cur / mx * 100, 1) if mx else 0.0,
            "page_last_update": page_update,
        })
    return rows


def append_rows(csv_path, rows, weather):
    new_file = not os.path.exists(csv_path)
    ts = datetime.now().isoformat(timespec="seconds")
    with open(csv_path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if new_file:
            w.writeheader()
        for r in rows:
            w.writerow({"timestamp": ts, **r, **weather})
    return ts


def capture_once(session, csv_path, verbose=True):
    try:
        html = fetch_html(session)
    except Exception as e:
        print(f"[{datetime.now():%H:%M:%S}] FETCH ERROR: {e}", file=sys.stderr)
        return False
    rows = parse(html)
    if not rows:
        print(f"[{datetime.now():%H:%M:%S}] NO DATA PARSED", file=sys.stderr)
        return False
    weather = fetch_weather()
    ts = append_rows(csv_path, rows, weather)
    if verbose:
        wx = f"{weather['temp_f']}F precip={weather['precip']}" if weather['temp_f'] != "" else "weather n/a"
        print(f"[{ts}] logged {len(rows)} zones · {wx}")
        for r in rows:
            print(f"    {r['facility_name']:<18} {r['current']:>4}/{r['maximum']:<5} {r['pct_full']:>5}%")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--csv", default=DEFAULT_CSV)
    ap.add_argument("--interval", type=int, default=600)
    args = ap.parse_args()
    session = requests.Session()
    if args.once:
        sys.exit(0 if capture_once(session, args.csv) else 1)
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
