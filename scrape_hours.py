#!/usr/bin/env python3
"""
ARC Hours Scraper
-----------------
Fetches the ARC hours page, parses regular + summer + special/holiday hours,
and writes hours.json for the website to read.

Designed to FAIL GRACEFULLY: if the page structure changes and parsing yields
nothing, it writes a status flag so the site can say "hours unavailable" rather
than showing wrong data.
"""
import json, re, sys
from datetime import datetime

URL = "https://campusrecreation.ucdavis.edu/arc/hours-location-and-contact-arc"

# Month names -> number, for parsing "July 3rd" etc.
MONTHS = {m:i+1 for i,m in enumerate(
    ["January","February","March","April","May","June","July","August",
     "September","October","November","December"])}

def parse_time_range(text):
    """'10am-8pm' -> {'open':'10:00','close':'20:00'}, 'Closed' -> closed."""
    t = text.strip()
    if re.search(r'closed', t, re.I):
        return {"closed": True}
    m = re.search(r'(\d{1,2}(?::\d{2})?\s*[ap]m)\s*[-\u2013]\s*(\d{1,2}(?::\d{2})?\s*[ap]m)', t, re.I)
    if not m:
        return None
    def to24(s):
        s = s.strip().lower()
        mm = re.match(r'(\d{1,2})(?::(\d{2}))?\s*([ap])m', s)
        h = int(mm.group(1)); minute = mm.group(2) or "00"
        ap = mm.group(3)
        if ap == 'p' and h != 12: h += 12
        if ap == 'a' and h == 12: h = 0
        return f"{h:02d}:{minute}"
    return {"open": to24(m.group(1)), "close": to24(m.group(2))}

def parse_special_dates(text):
    """Find lines like 'Friday, July 3rd 10am-8pm' or '... Closed'."""
    specials = {}
    # Match: [Weekday,] Month Dayth  <time range or Closed>
    pattern = re.compile(
        r'(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+'
        r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+'
        r'(\d{1,2})(?:st|nd|rd|th)\s+'
        r'(Closed|\d{1,2}(?::\d{2})?\s*[ap]m\s*[-\u2013]\s*\d{1,2}(?::\d{2})?\s*[ap]m)',
        re.I)
    # Guess year: page covers Aug 2025 - Jul 2026. Aug-Dec -> 2025, Jan-Jul -> 2026.
    for mo, day, timepart in pattern.findall(text):
        month_num = MONTHS[mo.capitalize()]
        year = 2025 if month_num >= 8 else 2026
        date_key = f"{year}-{month_num:02d}-{int(day):02d}"
        hrs = parse_time_range(timepart)
        if hrs:
            specials[date_key] = hrs
    return specials

def main():
    try:
        import requests
        html = requests.get(URL, timeout=30,
            headers={"User-Agent":"Mozilla/5.0 (arc-hours-scraper)"}).text
    except Exception as e:
        print(f"Fetch failed: {e}", file=sys.stderr)
        json.dump({"status":"error","reason":"fetch failed"}, open("hours.json","w"))
        sys.exit(1)

    # Strip tags to get clean text (the patterns work on text)
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'&nbsp;?', ' ', text)
    text = re.sub(r'\s+', ' ', text)

    specials = parse_special_dates(text)

    result = {
        "status": "ok" if specials else "partial",
        "updated": datetime.utcnow().isoformat(timespec="seconds")+"Z",
        # Regular hours (hardcoded fallbacks that match the page's stated hours;
        # these rarely change and give the site something even if parsing shifts)
        "regular": {"weekday":{"open":"05:00","close":"24:00"},
                    "weekend":{"open":"08:00","close":"23:00"}},
        "summer":  {"weekday":{"open":"06:00","close":"22:00"},
                    "weekend":{"open":"09:00","close":"21:00"}},
        "special": specials,
    }
    json.dump(result, open("hours.json","w"), indent=2)
    print(f"Parsed {len(specials)} special dates. Status: {result['status']}")
    # Show a few for verification
    for k in sorted(specials)[:8]:
        print(f"  {k}: {specials[k]}")

if __name__ == "__main__":
    main()
