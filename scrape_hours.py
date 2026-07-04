#!/usr/bin/env python3
"""
ARC + Pool Hours Scraper v5
Produces hours.json with SEPARATE data for "arc" and "pool" facilities,
since their hours, seasons, and special dates all differ.
Tries live scrape first; falls back to built-in known schedules if blocked.
"""
import json, re, sys
from datetime import datetime, timezone

ARC_URL = "https://campusrecreation.ucdavis.edu/arc/hours-location-and-contact-arc"
POOL_URL = "https://campusrecreation.ucdavis.edu/recreation/aquatics/hours-location-contact-aq"

# ---- ARC built-in fallback (2025-26 published special hours) ----
ARC_SPECIAL = {
    "2025-08-19":{"open":"13:00","close":"22:00"},"2025-08-21":{"open":"13:00","close":"22:00"},
    "2025-08-22":{"open":"13:00","close":"22:00"},"2025-08-29":{"open":"06:00","close":"20:00"},
    "2025-08-30":{"open":"09:00","close":"17:00"},"2025-08-31":{"open":"09:00","close":"17:00"},
    "2025-09-01":{"open":"10:00","close":"20:00"},"2025-11-11":{"open":"09:00","close":"22:00"},
    "2025-11-26":{"open":"05:00","close":"17:00"},"2025-11-27":{"closed":True},
    "2025-11-28":{"closed":True},"2025-11-29":{"open":"09:00","close":"17:00"},
    "2025-11-30":{"open":"09:00","close":"17:00"},"2025-12-23":{"closed":True},
    "2025-12-24":{"closed":True},"2025-12-25":{"closed":True},
    "2025-12-26":{"open":"10:00","close":"17:00"},"2025-12-31":{"closed":True},
    "2026-01-01":{"closed":True},"2026-01-16":{"open":"05:00","close":"22:00"},
    "2026-01-17":{"open":"09:00","close":"17:00"},"2026-01-18":{"open":"09:00","close":"17:00"},
    "2026-01-19":{"open":"09:00","close":"22:00"},"2026-06-19":{"open":"10:00","close":"20:00"},
    "2026-07-03":{"open":"10:00","close":"20:00"},"2026-07-04":{"open":"09:00","close":"17:00"},
    "2026-07-05":{"open":"09:00","close":"17:00"},"2026-07-06":{"open":"10:00","close":"20:00"},
}
ARC_REGULAR = {"weekday":{"open":"05:00","close":"24:00"},"weekend":{"open":"08:00","close":"23:00"}}
ARC_SUMMER  = {"weekday":{"open":"06:00","close":"22:00"},"weekend":{"open":"09:00","close":"21:00"}}

# ---- Pool built-in fallback ----
# Pool hours are ENVELOPES (earliest open -> latest close of the day's swim
# blocks) since the pool has multiple non-contiguous windows per day (lap
# swim gaps for classes etc). Envelope is the right level of detail for
# "is the pool open at all right now" + calendar display.
POOL_SUMMER = {  # Jun 15 - Sep 20, 2026
    "weekday":{"open":"06:30","close":"19:30"},   # Mon-Thu: 6:30a-8:45a, 1-5p, 5-7:30p
    "friday": {"open":"06:30","close":"19:30"},    # Fri: 6:30-8:45a, 1-7:30p
    "weekend":{"open":"09:00","close":"18:00"},    # Sat-Sun: 9a-12p, 1-6p
}
POOL_SPRING = {  # Mar 30 - Jun 14 (not currently active, kept for future)
    "weekday":{"open":"06:30","close":"19:00"},
    "friday": {"open":"06:30","close":"19:00"},
    "weekend":{"open":"08:00","close":"15:00"},
}
POOL_SPECIAL = {
    "2026-06-19":{"open":"15:00","close":"18:00"},   # Juneteenth
    "2026-07-03":{"open":"15:00","close":"18:00"},   # Independence Day wknd
    "2026-07-04":{"open":"15:00","close":"18:00"},
    "2026-07-05":{"open":"15:00","close":"18:00"},
    "2026-07-18":{"open":"15:00","close":"18:00"},   # July staff training
    "2026-08-15":{"open":"15:00","close":"18:00"},   # August staff training
    "2026-09-05":{"open":"15:00","close":"18:00"},   # Labor Day wknd
    "2026-09-06":{"open":"15:00","close":"18:00"},
    "2026-09-07":{"open":"15:00","close":"18:00"},
}

def clean_text(html):
    html=re.sub(r'<(script|style)[^>]*>.*?</\1>',' ',html,flags=re.S|re.I)
    html=re.sub(r'<[^>]+>',' ',html)
    for a,b in [('&nbsp;',' '),('&amp;','&'),('\u2013','-'),('\u2014','-')]:
        html=html.replace(a,b)
    return re.sub(r'\s+',' ',html)

MONTHS = {m:i+1 for i,m in enumerate(
    ["January","February","March","April","May","June","July","August",
     "September","October","November","December"])}

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

def try_scrape(url):
    try:
        import requests
        r=requests.get(url,timeout=30,headers={
            "User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"})
        if r.status_code==200:
            specials=parse_specials(clean_text(r.text))
            print(f"  {url}: HTTP 200, parsed {len(specials)} specials")
            return specials
        print(f"  {url}: HTTP {r.status_code} (blocked)")
    except Exception as e:
        print(f"  {url}: fetch failed ({e})")
    return {}

def main():
    print("Scraping ARC hours...")
    arc_scraped = try_scrape(ARC_URL)
    print("Scraping Pool hours...")
    pool_scraped = try_scrape(POOL_URL)

    arc_special = arc_scraped if arc_scraped else ARC_SPECIAL
    pool_special = pool_scraped if pool_scraped else POOL_SPECIAL

    result = {
        "status":"ok",
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z"),
        "arc": {
            "source": "live" if arc_scraped else "builtin",
            "regular": ARC_REGULAR,
            "summer": ARC_SUMMER,
            "special": arc_special,
        },
        "pool": {
            "source": "live" if pool_scraped else "builtin",
            "regular": POOL_SPRING,   # spring/regular season envelope
            "summer": POOL_SUMMER,    # summer session envelope
            "special": pool_special,
        },
    }
    json.dump(result, open("hours.json","w"), indent=2)
    print(f"Wrote hours.json: ARC {len(arc_special)} specials ({result['arc']['source']}), "
          f"Pool {len(pool_special)} specials ({result['pool']['source']})")

if __name__=="__main__":
    main()
