#!/usr/bin/env python3
"""
ARC Hours Scraper v4 — hybrid with built-in fallback.
Tries to scrape the live ARC hours page. If blocked (403) or parsing yields
nothing, falls back to a built-in copy of the published 25-26 special hours.
Update KNOWN_SPECIAL once a year from the ARC page.
"""
import json, re, sys
from datetime import datetime, timezone

URL = "https://campusrecreation.ucdavis.edu/arc/hours-location-and-contact-arc"
MONTHS = {m:i+1 for i,m in enumerate(
    ["January","February","March","April","May","June","July","August",
     "September","October","November","December"])}

# ---- Built-in fallback: 2025-26 published special hours ----
# Source: campusrecreation.ucdavis.edu ARC hours page. Update yearly.
KNOWN_SPECIAL = {
    "2025-08-19":{"open":"13:00","close":"22:00"},  # Dept Training
    "2025-08-21":{"open":"13:00","close":"22:00"},
    "2025-08-22":{"open":"13:00","close":"22:00"},
    "2025-08-29":{"open":"06:00","close":"20:00"},  # Labor Day wknd
    "2025-08-30":{"open":"09:00","close":"17:00"},
    "2025-08-31":{"open":"09:00","close":"17:00"},
    "2025-09-01":{"open":"10:00","close":"20:00"},
    "2025-11-11":{"open":"09:00","close":"22:00"},  # Veterans Day
    "2025-11-26":{"open":"05:00","close":"17:00"},  # Thanksgiving
    "2025-11-27":{"closed":True},
    "2025-11-28":{"closed":True},
    "2025-11-29":{"open":"09:00","close":"17:00"},
    "2025-11-30":{"open":"09:00","close":"17:00"},
    "2025-12-23":{"closed":True},                   # Winter closure
    "2025-12-24":{"closed":True},
    "2025-12-25":{"closed":True},
    "2025-12-26":{"open":"10:00","close":"17:00"},
    "2025-12-31":{"closed":True},                   # New Years
    "2026-01-01":{"closed":True},
    "2026-01-16":{"open":"05:00","close":"22:00"},  # MLK wknd
    "2026-01-17":{"open":"09:00","close":"17:00"},
    "2026-01-18":{"open":"09:00","close":"17:00"},
    "2026-01-19":{"open":"09:00","close":"22:00"},
    "2026-06-19":{"open":"10:00","close":"20:00"},  # Juneteenth
    "2026-07-03":{"open":"10:00","close":"20:00"},  # Independence Day
    "2026-07-04":{"open":"09:00","close":"17:00"},
    "2026-07-05":{"open":"09:00","close":"17:00"},
    "2026-07-06":{"open":"10:00","close":"20:00"},
}

def clean_text(html):
    html=re.sub(r'<(script|style)[^>]*>.*?</\1>',' ',html,flags=re.S|re.I)
    html=re.sub(r'<[^>]+>',' ',html)
    for a,b in [('&nbsp;',' '),('&amp;','&'),('\u2013','-'),('\u2014','-')]:
        html=html.replace(a,b)
    return re.sub(r'\s+',' ',html)

def to24(s):
    s=s.strip().lower().replace(' ','');m=re.match(r'(\d{1,2})(?::(\d{2}))?([ap])m',s)
    if not m:return None
    h=int(m.group(1));mn=m.group(2) or "00";ap=m.group(3)
    if ap=='p' and h!=12:h+=12
    if ap=='a' and h==12:h=0
    return f"{h:02d}:{mn}"

def parse_specials(text):
    specials={}
    pat=re.compile(r'(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s*,?\s*'
        r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+'
        r'(\d{1,2})(?:st|nd|rd|th)\s*(Closed|\d{1,2}(?::\d{2})?\s*[ap]m\s*-\s*\d{1,2}(?::\d{2})?\s*[ap]m)',re.I)
    for mo,day,tp in pat.findall(text):
        mn=MONTHS[mo.capitalize()];yr=2025 if mn>=8 else 2026
        key=f"{yr}-{mn:02d}-{int(day):02d}"
        if re.search(r'closed',tp,re.I):specials[key]={"closed":True}
        else:
            tm=re.search(r'(\d{1,2}(?::\d{2})?\s*[ap]m)\s*-\s*(\d{1,2}(?::\d{2})?\s*[ap]m)',tp,re.I)
            if tm:
                o,c=to24(tm.group(1)),to24(tm.group(2))
                if o and c:specials[key]={"open":o,"close":c}
    return specials

def main():
    scraped={}
    try:
        import requests
        r=requests.get(URL,timeout=30,headers={
            "User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            "Accept":"text/html,application/xhtml+xml","Accept-Language":"en-US,en;q=0.9",
        })
        if r.status_code==200:
            scraped=parse_specials(clean_text(r.text))
        print(f"Scrape: HTTP {r.status_code}, parsed {len(scraped)} specials")
    except Exception as e:
        print(f"Scrape failed: {e}",file=sys.stderr)

    # Use scraped data if it worked; otherwise fall back to built-in known hours.
    if scraped:
        special=scraped; source="live"
    else:
        special=KNOWN_SPECIAL; source="builtin"
    print(f"Using {source} special hours ({len(special)} dates)")

    result={
        "status":"ok","source":source,
        "updated":datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z"),
        "regular":{"weekday":{"open":"05:00","close":"24:00"},"weekend":{"open":"08:00","close":"23:00"}},
        "summer":{"weekday":{"open":"06:00","close":"22:00"},"weekend":{"open":"09:00","close":"21:00"}},
        "special":special,
    }
    json.dump(result,open("hours.json","w"),indent=2)
    print(f"Wrote hours.json with {len(special)} special dates")

if __name__=="__main__":
    main()
