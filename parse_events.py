#!/usr/bin/env python3
"""
Parses a copy-pasted month view from the ARC court/studio schedule page
(the "Month" or "Agenda" view text) into events.json.

Expected input shape (as copy-pasted): a header line like "July 2026", then
day-of-week headers, then a sequence of day numbers and, for each day,
alternating (time range, title) line pairs until the next day number.

Usage: python parse_events.py raw_schedule.txt > events.json
"""
import json, re, sys
from datetime import date
import calendar

MONTHS = {m: i+1 for i, m in enumerate(
    ["January","February","March","April","May","June","July","August",
     "September","October","November","December"])}

TIME_RANGE_RE = re.compile(
    r'^\d{1,2}:\d{2}\s*[AP]M\s*-\s*\d{1,2}:\d{2}\s*[AP]M$')
DAY_NUM_RE = re.compile(r'^\d{1,2}$')
LOC_RE = re.compile(r'^(.*)\(([^)]+)\)\s*$')
# Titles matching this aren't real "events" worth tracking:
#  - "* Open (* Hours)" is just the facility's open/closed marker, not an
#    activity — it's present at every hour of every day with zero variation,
#    so it can never correlate with anything and is excluded on that basis.
# NOTE: Racquetball Court Reservation is intentionally KEPT (not excluded).
# We haven't yet verified whether it correlates with occupancy — that
# requires enough overlapping occupancy+schedule history to test properly.
# Revisit this decision once more July+ data has accumulated.
EXCLUDE_RE = re.compile(r'Open\s*\(.*Hours\)', re.I)

def parse(text):
    lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
    # Find "Month YYYY" header
    month_num, year = None, None
    for l in lines[:5]:
        m = re.match(r'(January|February|March|April|May|June|July|August|'
                      r'September|October|November|December)\s+(\d{4})', l)
        if m:
            month_num, year = MONTHS[m.group(1)], int(m.group(2))
            break
    if not month_num:
        print("Couldn't find a 'Month YYYY' header", file=sys.stderr)
        return {}

    days_in_month = calendar.monthrange(year, month_num)[1]

    events_by_date = {}
    phase = "before"   # before -> in -> after (padding days on either side)
    cur_day_key = None
    prev_num = None
    i = 0
    # Skip past weekday header row (Sun..Sat) if present
    while i < len(lines) and lines[i] in ("Sun","Mon","Tue","Wed","Thu","Fri","Sat"):
        i += 1
    while i < len(lines):
        line = lines[i]
        if DAY_NUM_RE.match(line) and not TIME_RANGE_RE.match(line):
            num = int(line)
            if phase == "before":
                if prev_num is not None and num < prev_num:
                    phase = "in"
                    y, m = (year, month_num)
                else:
                    y, m = (year, month_num - 1) if month_num > 1 else (year-1, 12)
            elif phase == "in":
                if prev_num is not None and num < prev_num:
                    phase = "after"
                    y, m = (year, month_num + 1) if month_num < 12 else (year+1, 1)
                else:
                    y, m = (year, month_num)
            else:
                y, m = (year, month_num + 1) if month_num < 12 else (year+1, 1)
            prev_num = num
            try:
                cur_day_key = date(y, m, num).isoformat()
            except ValueError:
                cur_day_key = None
            i += 1
            continue
        # Otherwise, expect a (time range, title) pair
        if TIME_RANGE_RE.match(line) and cur_day_key:
            time_range = line
            title_line = lines[i+1] if i+1 < len(lines) else ""
            i += 2
            # Skip non-events BEFORE splitting off the location, since the
            # exclusion pattern needs to see the full raw line (e.g. the
            # facility-hours marker only matches with its "(...Hours)" intact).
            if EXCLUDE_RE.search(title_line):
                continue
            m = LOC_RE.match(title_line)
            if m:
                title, loc = m.group(1).strip(" -"), m.group(2).strip()
            else:
                title, loc = title_line, None
            events_by_date.setdefault(cur_day_key, []).append(
                {"time": time_range, "title": title, "loc": loc})
            continue
        i += 1  # skip anything unexpected

    # Only keep dates actually within the target month (drop padding days)
    only_target_month = {k: v for k, v in events_by_date.items()
                          if k.startswith(f"{year}-{month_num:02d}-")}
    return only_target_month

if __name__ == "__main__":
    text = open(sys.argv[1]).read() if len(sys.argv) > 1 else sys.stdin.read()
    result = parse(text)
    json.dump({"days": result}, sys.stdout, indent=2)
    print(f"\nParsed {len(result)} days with events", file=sys.stderr)
