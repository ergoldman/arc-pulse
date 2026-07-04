#!/usr/bin/env python3
"""ARC Hours Scraper v3 — with debug output to diagnose live parsing."""
import json, re, sys
from datetime import datetime, timezone

URL = "https://campusrecreation.ucdavis.edu/arc/hours-location-and-contact-arc"
MONTHS = {m:i+1 for i,m in enumerate(
    ["January","February","March","April","May","June","July","August",
     "September","October","November","December"])}

def clean_text(html):
    html = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', html, flags=re.S|re.I)
    html = re.sub(r'<[^>]+>', ' ', html)
    for a,b in [('&nbsp;',' '),('&amp;','&'),('&#39;',"'"),('&#8217;',"'"),
                ('&rsquo;',"'"),('&ndash;','-'),('&#8211;','-'),('\u2013','-'),('\u2014','-')]:
        html = html.replace(a,b)
    return re.sub(r'\s+',' ',html)

def to24(s):
    s=s.strip().lower().replace(' ','')
    m=re.match(r'(\d{1,2})(?::(\d{2}))?([ap])m',s)
    if not m:return None
    h=int(m.group(1));mn=m.group(2) or "00";ap=m.group(3)
    if ap=='p' and h!=12:h+=12
    if ap=='a' and h==12:h=0
    return f"{h:02d}:{mn}"

def parse_specials(text):
    specials={}
    pat=re.compile(
        r'(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s*,?\s*'
        r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+'
        r'(\d{1,2})(?:st|nd|rd|th)\s*'
        r'(Closed|\d{1,2}(?::\d{2})?\s*[ap]m\s*[-]\s*\d{1,2}(?::\d{2})?\s*[ap]m)',re.I)
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
    try:
        import requests
        r=requests.get(URL,timeout=30,headers={
            "User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            "Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        html=r.text
    except Exception as e:
        print(f"Fetch failed: {e}",file=sys.stderr)
        json.dump({"status":"error"},open("hours.json","w"));sys.exit(0)

    # DEBUG: show what we got
    print(f"DEBUG fetched {len(html)} chars, HTTP {r.status_code}")
    print(f"DEBUG contains 'Independence Day'? {'Independence Day' in html}")
    print(f"DEBUG contains 'July 3rd'? {'July 3rd' in html}")
    print(f"DEBUG contains 'Special Hours'? {'Special Hours' in html}")

    text=clean_text(html)
    specials=parse_specials(text)
    print(f"DEBUG parsed {len(specials)} special dates")
    if not specials:
        # Save a sample of the cleaned text so we can see the format
        idx=text.find('Special Hours')
        if idx>=0:print("DEBUG sample near 'Special Hours':",repr(text[idx:idx+300]))
        else:print("DEBUG 'Special Hours' NOT in cleaned text")

    result={
        "status":"ok" if specials else "partial",
        "updated":datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z"),
        "regular":{"weekday":{"open":"05:00","close":"24:00"},"weekend":{"open":"08:00","close":"23:00"}},
        "summer":{"weekday":{"open":"06:00","close":"22:00"},"weekend":{"open":"09:00","close":"21:00"}},
        "special":specials,
    }
    json.dump(result,open("hours.json","w"),indent=2)
    print(f"Wrote hours.json, status={result['status']}, {len(specials)} specials")

if __name__=="__main__":
    main()
