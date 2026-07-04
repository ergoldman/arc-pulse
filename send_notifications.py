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

def save_subscriptions(subs):
    """Write the (possibly updated) subscriber list back to jsonbin — used to
    persist per-subscriber 'already sent today' state for personalized alerts."""
    import requests
    bin_id = os.environ["JSONBIN_ID"]
    key = os.environ["JSONBIN_KEY"]
    requests.put(f"https://api.jsonbin.io/v3/b/{bin_id}",
                 headers={"Content-Type": "application/json", "X-Master-Key": key},
                 json={"subscriptions": subs}, timeout=15)

def hour_average(csv_lines, facility_name, target_dow, target_hour):
    """Historical average % full for this exact weekday+hour, real non-zero
    readings only."""
    vals = []
    for line in csv_lines[1:]:
        parts = line.split(",")
        if len(parts) < 7 or parts[2] != facility_name:
            continue
        try:
            pct = float(parts[6])
            if pct <= 0:
                continue
            pac = to_pacific(parts[0])
        except Exception:
            continue
        if pac.weekday() != target_dow or pac.hour != target_hour:
            continue
        vals.append(pct)
    if not vals:
        return None
    return sum(vals) / len(vals)

def crowd_label(pct):
    if pct < 25: return "quiet"
    if pct < 50: return "moderate"
    if pct < 75: return "busy"
    return "packed"

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

def to_pacific(ts_str):
    import zoneinfo
    dt_utc = datetime.strptime(ts_str, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=zoneinfo.ZoneInfo("UTC"))
    return dt_utc.astimezone(zoneinfo.ZoneInfo("America/Los_Angeles"))

def quiet_busy_hours_today(csv_lines, facility_name, target_dow):
    """Quietest AND busiest hour (7am-8pm) historically for this weekday,
    from real non-zero readings only. Mirrors the site's 'best time' logic."""
    hourly = {}
    for line in csv_lines[1:]:
        parts = line.split(",")
        if len(parts) < 7 or parts[2] != facility_name:
            continue
        try:
            pct = float(parts[6])
            if pct <= 0:
                continue
            pac = to_pacific(parts[0])
        except Exception:
            continue
        if pac.weekday() != target_dow:
            continue
        if not (7 <= pac.hour <= 20):
            continue
        hourly.setdefault(pac.hour, []).append(pct)
    if not hourly:
        return None
    avgs = {h: sum(v) / len(v) for h, v in hourly.items()}
    quiet_h = min(avgs, key=avgs.get)
    busy_h = max(avgs, key=avgs.get)
    return {
        "quiet_hour": quiet_h, "quiet_pct": avgs[quiet_h],
        "busy_hour": busy_h, "busy_pct": avgs[busy_h],
    }

def fmt_hour(h):
    ap = "am" if h < 12 else "pm"
    hr = h % 12 or 12
    return f"{hr}{ap}"

def check_facility(facility_name, cfg, hours_all, csv_lines, now, today_state):
    """Returns list of (title, body, tag) to send for this facility, and
    mutates today_state[facility_name] with which alerts fired."""
    label = cfg["label"]
    hset = hours_all.get(cfg["hours_key"])
    fstate = today_state.setdefault(facility_name, {})
    to_send = []
    if not hset:
        return to_send  # no hours data for this facility yet

    today_hours = hours_for_day(hset, now)
    cur_min = now.hour * 60 + now.minute

    if not today_hours.get("closed"):
        open_m = hm_to_minutes(today_hours["open"])
        close_m = hm_to_minutes(today_hours["close"]) if today_hours["close"] != "24:00" else 1440

        if 0 <= close_m - cur_min <= CLOSING_WINDOW_MIN and not fstate.get("closing_sent"):
            to_send.append(("closing", f"{label} closing soon", f"Closes in {close_m-cur_min} min today.", f"{facility_name}-closing"))
            fstate["closing_sent"] = True

        # Combined: opening soon + today's forecast (quietest & busiest hour),
        # sent once as a single notification within the pre-open window.
        if 0 <= open_m - cur_min <= OPENING_WINDOW_MIN and not fstate.get("opening_sent"):
            qb = quiet_busy_hours_today(csv_lines, facility_name, now.weekday())
            body = f"Opens in {open_m-cur_min} min today."
            if qb:
                body += (f" Quietest ~{fmt_hour(qb['quiet_hour'])} (~{qb['quiet_pct']:.0f}%), "
                         f"busiest ~{fmt_hour(qb['busy_hour'])} (~{qb['busy_pct']:.0f}%).")
            to_send.append(("opening", f"{label} opening soon", body, f"{facility_name}-opening"))
            fstate["opening_sent"] = True

    tomorrow = now + timedelta(days=1)
    tmr_hours = hours_for_day(hset, tomorrow)
    tmr_key = tomorrow.strftime("%Y-%m-%d")
    is_special = tmr_key in hset.get("special", {})
    if is_special and not fstate.get("tomorrow_sent"):
        if tmr_hours.get("closed"):
            to_send.append(("tomorrow", f"{label} heads up", f"{label} is closed tomorrow.", f"{facility_name}-tomorrow"))
        else:
            to_send.append(("tomorrow", f"{label} heads up", f"{label} has special hours tomorrow: {tmr_hours['open']}–{tmr_hours['close']}.", f"{facility_name}-tomorrow"))
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

    subs_raw = get_subscriptions()
    print(f"{len(subs_raw)} subscribers")

    all_to_send = []
    for facility_name, cfg in FACILITIES.items():
        msgs = check_facility(facility_name, cfg, hours_all, csv_lines, now, today_state)
        all_to_send.extend(msgs)

    if not all_to_send:
        print("No notifications to send this cycle.")
    for kind, title, body, tag in all_to_send:
        print(f"Sending [{kind}]: {title} — {body}")
        sent = 0
        for entry in subs_raw:
            # Support both old (raw subscription) and new ({sub, prefs}) shapes.
            sub = entry.get("sub", entry)
            prefs = entry.get("prefs", {"closing": True, "opening": True, "tomorrow": True, "forecast": True})
            if not prefs.get(kind, True):
                continue  # this subscriber opted out of this notification type
            if send_push(sub, title, body, tag):
                sent += 1
        print(f"  sent to {sent}/{len(subs_raw)} subscribers (after preference filter)")

    # ---- Personalized: "my favorite time to go" reminder ----------------
    # Each subscriber picks their own facility + hour. This now fires in the
    # SAME window as that facility's "opening soon + forecast" notification
    # (i.e. once, shortly before opening) — so people check their phone once
    # in the morning and get both, rather than a separate later-day ping.
    # The content is still about their chosen hour's predicted crowd level;
    # only the TIMING is tied to opening. De-dup is PER SUBSCRIBER (stored on
    # their own record, favorite_last_sent), since each person's choice differs.
    cur_min = now.hour * 60 + now.minute
    subs_changed = False
    for entry in subs_raw:
        prefs = entry.get("prefs", {})
        if not prefs.get("favoriteEnabled"):
            continue
        fac_name = prefs.get("favoriteFacility") or "ARC Access"
        hour = prefs.get("favoriteHour")
        if hour is None:
            continue
        if entry.get("favorite_last_sent") == today_key:
            continue  # already sent today for this person

        fac_cfg = FACILITIES.get(fac_name)
        hset = hours_all.get(fac_cfg["hours_key"]) if fac_cfg else None
        if not hset:
            continue  # no hours data for their chosen facility yet
        today_hours = hours_for_day(hset, now)
        if today_hours.get("closed"):
            continue  # facility closed today — nothing to send
        open_m = hm_to_minutes(today_hours["open"])
        if not (0 <= open_m - cur_min <= OPENING_WINDOW_MIN):
            continue  # not yet in the pre-opening window

        label = fac_cfg["label"]
        avg = hour_average(csv_lines, fac_name, now.weekday(), int(hour))
        if avg is not None:
            body = f"At {fmt_hour(int(hour))}, {label} is usually ~{avg:.0f}% full — {crowd_label(avg)}."
        else:
            body = f"Your {fmt_hour(int(hour))} {label} check-in is coming up — not enough data yet to predict the crowd."
        sub = entry.get("sub", entry)
        print(f"Sending [favorite]: {label} @ {fmt_hour(int(hour))} — {body}")
        if send_push(sub, f"Your {fmt_hour(int(hour))} {label} reminder", body, f"{fac_name}-favorite"):
            entry["favorite_last_sent"] = today_key
            subs_changed = True

    if subs_changed:
        save_subscriptions(subs_raw)

    state = {k: v for k, v in state.items() if k >= (now - timedelta(days=2)).strftime("%Y-%m-%d")}
    state[today_key] = today_state
    json.dump(state, open("notif_state.json", "w"), indent=2)

if __name__ == "__main__":
    main()
