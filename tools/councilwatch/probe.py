#!/usr/bin/env python3
"""One-off probe: find how each Essex council publishes its meetings. Writes data/councilwatch/probe.json."""
import json, os, re, ssl, urllib.request, urllib.error
from datetime import datetime, timezone
UA = "TheSeaxCouncilWatch/1.0 (+https://theseax.com/about/)"
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SITES = {
 "basildon": ["https://www.basildon.gov.uk", "https://www.basildonmeetings.info", "https://basildon.moderngov.co.uk"],
 "braintree": ["https://www.braintree.gov.uk/council/committee-meetings-minutes", "https://braintree.moderngov.co.uk", "https://www.braintree.gov.uk/meetings"],
 "brentwood": ["https://www.brentwood.gov.uk", "https://brentwood.moderngov.co.uk", "https://democracy.brentwood.gov.uk"],
 "castlepoint": ["https://www.castlepoint.gov.uk", "https://castlepoint.moderngov.co.uk", "https://www.castlepoint.gov.uk/meetings"],
 "chelmsford": ["https://www.chelmsford.gov.uk/committee-meetings/", "https://chelmsford.moderngov.co.uk", "https://democracy.chelmsford.gov.uk"],
 "colchester": ["https://colchester.cmis.uk.com/colchester/", "https://colchester.cmis.uk.com/colchester/CalendarofMeetings.aspx"],
 "epping": ["https://www.eppingforestdc.gov.uk", "https://rds.eppingforestdc.gov.uk", "https://eppingforestdc.moderngov.co.uk"],
 "harlow": ["https://www.harlow.gov.uk", "https://moderngov.harlow.gov.uk", "https://harlow.moderngov.co.uk"],
 "maldon": ["https://democracy.maldon.gov.uk"],
 "rochford": ["https://www.rochford.gov.uk", "https://rochford.moderngov.co.uk", "https://democracy.rochford.gov.uk"],
 "tendring": ["https://www.tendringdc.gov.uk", "https://tendring.moderngov.co.uk", "https://tdcdemocracy.tendringdc.uk"],
 "uttlesford": ["https://www.uttlesford.gov.uk", "https://uttlesford.moderngov.co.uk", "https://democracy.uttlesford.gov.uk"],
 "southend": ["https://democracy.southend.gov.uk"],
 "thurrock": ["https://democracy.thurrock.gov.uk"],
 "essex": ["https://cmis.essex.gov.uk/essexcmis5/CalendarofMeetings.aspx"],
}
PAT = re.compile(r'https?://[a-z0-9.\-]+/[^"\'\s<>]*(?:mgCommitteeDetails|mgCalendar|ieListDocuments|ieDocHome|mgListCommittees|cmis|CalendarofMeetings|committee-meetings|/meetings)[^"\'\s<>]*', re.I)
REL = re.compile(r'href="([^"]*(?:mgCalendar|ieListDocuments|mgCommitteeDetails|ViewMeetingPublic|Meeting/\d+|committee-meetings/[a-z0-9\-]+|ieDocHome)[^"]*)"', re.I)

def get(u, n=400000):
    req = urllib.request.Request(u, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=25, context=ssl.create_default_context()) as r:
            return r.status, r.geturl(), r.read(n).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, u, ""
    except Exception as e:
        return 0, u, str(e)[:200]

out = {"at": datetime.now(timezone.utc).isoformat(), "councils": {}}
now = datetime.now()
for c, urls in SITES.items():
    res = []
    for u in urls:
        st, final, body = get(u)
        info = {"url": u, "status": st, "final": final, "title": (re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I) or [None, ""])[1].strip()[:120] if st else body,
                "abs": sorted(set(PAT.findall(body)))[:12], "rel": sorted(set(REL.findall(body)))[:12]}
        if st == 200 and ("moderngov" in body.lower() or "mgCalendar" in body or "ieListDocuments" in body):
            base = final.split("/mg")[0].split("/ie")[0].rstrip("/")
            if base.endswith(".aspx"): base = base.rsplit("/", 1)[0]
            s2, f2, b2 = get(f"{base}/mgCalendarMonthView.aspx?M={now.month}&Y={now.year}")
            info["calendar"] = {"status": s2, "final": f2, "rel": sorted(set(REL.findall(b2)))[:15]}
            s3, f3, b3 = get(f"{base}/mgWebService.asmx/GetMeetings?lFromDate={now:%d/%m/%Y}&lToDate={now:%d/%m/%Y}")
            info["webservice"] = {"status": s3, "head": b3[:300]}
            s4, f4, b4 = get(f"{base.split('/', 3)[0]}//{base.split('/')[2]}/robots.txt", 4000)
            info["robots"] = b4[:600]
        res.append(info)
    out["councils"][c] = res
os.makedirs(os.path.join(ROOT, "data", "councilwatch"), exist_ok=True)
json.dump(out, open(os.path.join(ROOT, "data", "councilwatch", "probe.json"), "w"), indent=1)
print(json.dumps({c: [(r["url"], r["status"]) for r in v] for c, v in out["councils"].items()}, indent=1))
