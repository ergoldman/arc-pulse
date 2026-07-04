#!/usr/bin/env python3
"""
ARC Pulse — Notification Sender (ARC + Pool)
Runs every cycle (via the GitHub Action, same cadence as the logger).
Checks four conditions PER FACILITY (ARC Access, Recreation Pool) against the
latest data + hours, and sends Web Push notifications to subscribers via
jsonbin.io-stored subscriptions.

De-duplication: notif_state.json (on the data branch) tracks which alerts have
already fired today, PER FACILITY, so e.g. "ARC closing soon" and "Pool closing
soon" are independent and each only sends once per day.

Env vars required (GitHub Actions secrets):
  VAPID_PRIVATE_KEY_PEM  - the private key PEM (keep secret!)
  VAPID_CLAIM_EMAIL      - contact email for push service (any address is fine)
  JSONBIN_ID             - the subscriptions bin id
  JSONBIN_KEY            - the jsonbin master key
"""
import json, os, sys
from datetime import datetime, timedelta

QUIET_THRESHOLD = 30     # % full below which we consider it "a good time to go"
CLOSING_WINDOW_MIN = 30
OPENING_WINDOW_MIN = 30

# Facilities to check: csv name -> (hours.json key, short label for messages)
FACILITIES = {
    "ARC Access":      {"hours_key": "arc",  "label": "ARC"},
    "Recreation Pool": {"hours_key": "pool", "label": "Pool"},
}

def pacific_now():
    import zoneinfo
    return datetime.now(zoneinfo.ZoneInfo("America/Los_Angeles"))

def load_json(path, default):
    try:
        return json.load(open(path))
    except Exception:
        return default

def get_subscriptions():
    import requests
    bin_id = os.environ["JSONBIN_ID"]
    key = os.environ["JSONBIN_KEY"]
    r = requests.get(f"https://api.jsonbin.io/v3/b/{bin_id}/latest",
                      headers={"X-Master-Key": key}, timeout=15)
    if not r.ok:
        return []
    return r.json().get("record", {}).get("subscriptions", [])

def send_push(sub, title, body, tag):
    from pywebpush import webpush, WebPushException
    try:
        webpush(
            subscription_info=sub,
            data=json.dumps({"title": title, "body": body, "tag": tag, "url": "/"}),
            vapid_private_key=os.environ["VAPID_PRIVATE_KEY_PEM"],
            vapid_claims={"sub": "mailto:" + os.environ.get("VAPID_CLAIM_EMAIL", "example@example.com")},
        )
        return True
    except WebPushException as e:
        print(f"  push failed for one subscriber: {e}", file=sys.stderr)
        return False

def hours_for_day(hours_set, d):
    key = d.strftime("%Y-%m-%d")
    special = hours_set.get("special", {})
    if key in special:
        return special[key]
    weekend = d.weekday() >= 5
    m, day = d.month, d.day
    is_summer = (m > 6 and m < 9) or (m == 6 and day >= 15) or (m == 9 and day < 22)
    season = hours_set["summer"] if is_summer else hours_set["regular"]
    if weekend:
        return season["weekend"]
    if d.weekday() == 4 and "friday" in season:
        return season["friday"]
    return season["weekday"]

def hm_to_minutes(hm):
    h, m = hm.split(":")
    return int(h) * 60 + int(m)

def latest_pct(csv_lines, facility_name):
    for line in reversed(csv_lines[1:]):
        parts = line.split(",")
        if len(parts) >= 7 and parts[2] == facility_name:
            try:
                return float(parts[6])
            except ValueError:
                return None
    return None

def check_facility(facility_name, cfg, hours_all, csv_lines, now, today_state):
    """Returns list of (title, body, tag) to send for this facility, and
    mutates today_state[facility_name] with which alerts fired."""
    label = cfg["label"]
    hset = hours_all.get(cfg["hours_key"])
    fstate = today_state.setdefault(facility_name, {})
    to_send = []
    if not hset:
        return to_send  # no hours data for this facility yet

    pct_now = latest_pct(csv_lines, facility_name)
    today_hours = hours_for_day(hset, now)
    cur_min = now.hour * 60 + now.minute

    if not today_hours.get("closed"):
        open_m = hm_to_minutes(today_hours["open"])
        close_m = hm_to_minutes(today_hours["close"]) if today_hours["close"] != "24:00" else 1440

        if 0 <= close_m - cur_min <= CLOSING_WINDOW_MIN and not fstate.get("closing_sent"):
            to_send.append((f"{label} closing soon", f"Closes in {close_m-cur_min} min today.", f"{facility_name}-closing"))
            fstate["closing_sent"] = True

        if 0 <= open_m - cur_min <= OPENING_WINDOW_MIN and not fstate.get("opening_sent"):
            to_send.append((f"{label} opening soon", f"Opens in {open_m-cur_min} min today.", f"{facility_name}-opening"))
            fstate["opening_sent"] = True

        if pct_now is not None and open_m <= cur_min < close_m and pct_now < QUIET_THRESHOLD and not fstate.get("quiet_sent"):
            to_send.append((f"Good time to go — {label}", f"{label} is at {pct_now:.0f}% right now — quiet.", f"{facility_name}-quiet"))
            fstate["quiet_sent"] = True

    tomorrow = now + timedelta(days=1)
    tmr_hours = hours_for_day(hset, tomorrow)
    tmr_key = tomorrow.strftime("%Y-%m-%d")
    is_special = tmr_key in hset.get("special", {})
    if is_special and not fstate.get("tomorrow_sent"):
        if tmr_hours.get("closed"):
            to_send.append((f"{label} heads up", f"{label} is closed tomorrow.", f"{facility_name}-tomorrow"))
        else:
            to_send.append((f"{label} heads up", f"{label} has special hours tomorrow: {tmr_hours['open']}–{tmr_hours['close']}.", f"{facility_name}-tomorrow"))
        fstate["tomorrow_sent"] = True

    return to_send

def main():
    now = pacific_now()
    today_key = now.strftime("%Y-%m-%d")
    state = load_json("notif_state.json", {})
    today_state = state.get(today_key, {})

    hours_all = load_json("hours.json", {})
    try:
        csv_lines = open("arc_occupancy.csv").read().strip().split("\n")
    except Exception as e:
        print(f"Couldn't read occupancy CSV: {e}", file=sys.stderr)
        csv_lines = []

    subs = get_subscriptions()
    print(f"{len(subs)} subscribers")

    all_to_send = []
    for facility_name, cfg in FACILITIES.items():
        msgs = check_facility(facility_name, cfg, hours_all, csv_lines, now, today_state)
        all_to_send.extend(msgs)

    if not all_to_send:
        print("No notifications to send this cycle.")
    for title, body, tag in all_to_send:
        print(f"Sending: {title} — {body}")
        sent = 0
        for sub in subs:
            if send_push(sub, title, body, tag):
                sent += 1
        print(f"  sent to {sent}/{len(subs)} subscribers")

    state = {k: v for k, v in state.items() if k >= (now - timedelta(days=2)).strftime("%Y-%m-%d")}
    state[today_key] = today_state
    json.dump(state, open("notif_state.json", "w"), indent=2)

if __name__ == "__main__":
    main()
