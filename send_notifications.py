#!/usr/bin/env python3
"""
ARC Pulse — Notification Sender
Runs every cycle (via the GitHub Action, same cadence as the logger).
Checks four conditions against the latest data + hours, and sends Web Push
notifications to subscribers via jsonbin.io-stored subscriptions.

De-duplication: a small state file (notif_state.json, on the data branch)
tracks which alerts have already fired today, so e.g. "closing soon" only
sends once, not every 15 minutes.

Env vars required (set as GitHub Actions secrets):
  VAPID_PRIVATE_KEY_PEM  - the private key PEM (keep secret!)
  VAPID_CLAIM_EMAIL      - contact email for push service (any address is fine)
  JSONBIN_ID             - the subscriptions bin id
  JSONBIN_KEY            - the jsonbin master key
"""
import json, os, sys
from datetime import datetime, timezone, timedelta

QUIET_THRESHOLD = 30     # % full below which we consider it "a good time to go"
CLOSING_WINDOW_MIN = 30  # notify this many minutes before close
OPENING_WINDOW_MIN = 30  # notify this many minutes before open

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

def send_push(sub, title, body, tag, url="/"):
    from pywebpush import webpush, WebPushException
    try:
        webpush(
            subscription_info=sub,
            data=json.dumps({"title": title, "body": body, "tag": tag, "url": url}),
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
    weekend = d.weekday() >= 5  # Sat=5, Sun=6
    m, day = d.month, d.day
    is_summer = (m > 6 and m < 9) or (m == 6 and day >= 15) or (m == 9 and day < 22)
    season = hours_set["summer"] if is_summer else hours_set["regular"]
    if weekend:
        return season["weekend"]
    if d.weekday() == 4 and "friday" in season:  # Friday envelope (pool)
        return season["friday"]
    return season["weekday"]

def hm_to_minutes(hm):
    h, m = hm.split(":")
    return int(h) * 60 + int(m)

def main():
    now = pacific_now()
    today_key = now.strftime("%Y-%m-%d")
    state = load_json("notif_state.json", {})
    today_state = state.get(today_key, {})

    hours = load_json("hours.json", {})
    # latest occupancy: read the CSV tail for ARC Access (main facility for now)
    pct_now = None
    try:
        lines = open("arc_occupancy.csv").read().strip().split("\n")
        for line in reversed(lines[1:]):
            parts = line.split(",")
            if len(parts) >= 7 and parts[2] == "ARC Access":
                pct_now = float(parts[6])
                break
    except Exception as e:
        print(f"Couldn't read occupancy: {e}", file=sys.stderr)

    subs = get_subscriptions()
    print(f"{len(subs)} subscribers, occupancy now={pct_now}")

    to_send = []  # list of (title, body, tag)

    arc_hours = hours.get("arc")
    if arc_hours:
        today_hours = hours_for_day(arc_hours, now)
        cur_min = now.hour * 60 + now.minute

        if not today_hours.get("closed"):
            open_m = hm_to_minutes(today_hours["open"])
            close_m = hm_to_minutes(today_hours["close"]) if today_hours["close"] != "24:00" else 1440

            # Closing soon
            if 0 <= close_m - cur_min <= CLOSING_WINDOW_MIN and not today_state.get("closing_sent"):
                to_send.append(("ARC closing soon", f"Closes in {close_m-cur_min} min today.", "closing"))
                today_state["closing_sent"] = True

            # Opening soon (before open_m, within window)
            if 0 <= open_m - cur_min <= OPENING_WINDOW_MIN and not today_state.get("opening_sent"):
                to_send.append(("ARC opening soon", f"Opens in {open_m-cur_min} min today.", "opening"))
                today_state["opening_sent"] = True

            # Quiet now (only during open hours)
            if pct_now is not None and open_m <= cur_min < close_m and pct_now < QUIET_THRESHOLD and not today_state.get("quiet_sent"):
                to_send.append(("Good time to go", f"ARC is at {pct_now:.0f}% right now — quiet.", "quiet"))
                today_state["quiet_sent"] = True

        # Holiday/special hours tomorrow
        tomorrow = now + timedelta(days=1)
        tmr_hours = hours_for_day(arc_hours, tomorrow)
        tmr_key = tomorrow.strftime("%Y-%m-%d")
        is_special = tmr_key in arc_hours.get("special", {})
        if is_special and not today_state.get("tomorrow_sent"):
            if tmr_hours.get("closed"):
                to_send.append(("Heads up", "ARC is closed tomorrow.", "tomorrow"))
            else:
                to_send.append(("Heads up", f"ARC has special hours tomorrow: {tmr_hours['open']}–{tmr_hours['close']}.", "tomorrow"))
            today_state["tomorrow_sent"] = True

    if not to_send:
        print("No notifications to send this cycle.")
    for title, body, tag in to_send:
        print(f"Sending: {title} — {body}")
        sent = 0
        for sub in subs:
            if send_push(sub, title, body, tag):
                sent += 1
        print(f"  sent to {sent}/{len(subs)} subscribers")

    # Save de-dup state (prune old days to keep the file small)
    state = {k: v for k, v in state.items() if k >= (now - timedelta(days=2)).strftime("%Y-%m-%d")}
    state[today_key] = today_state
    json.dump(state, open("notif_state.json", "w"), indent=2)

if __name__ == "__main__":
    main()
