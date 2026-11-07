#!/usr/bin/env python3
"""Probe round 2: save sample pages from each council's meeting system so readers can be written. Output: samples/ (data branch)."""
import json, os, re, ssl, sys, urllib.request, urllib.error
from datetime import datetime, timezone
from urllib.parse import urljoin
OUT = sys.argv[1] if len(sys.argv) > 1 else "samples"
os.makedirs(OUT, exist_ok=True)
H = {"User-Agent": "TheSeaxCouncilWatch/1.0 (+https://theseax.com/about/; theseaxessex@gmail.com)",
     "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "en-GB,en;q=0.9"}
def get(u, n=1500000):
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers=H), timeout=30, context=ssl.create_default_context()) as r:
            return r.status, r.geturl(), r.read(n).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, u, ""
    except Exception as e:
        return 0, u, repr(e)[:300]
log = {}
def save(name, u, follow=None, nfollow=1):
    st, fin, body = get(u)
    log[name] = {"url": u, "status": st, "final": fin, "len": len(body)}
    open(f"{OUT}/{name}.html", "w").write(body)
    if follow and st == 200:
        links = []
        for m in re.finditer(r'href=["\']([^"\']+)["\']', body):
            h = m.group(1).replace("&amp;", "&")
            if re.search(follow, h) and h not in links: links.append(h)
        log[name]["links"] = links[:40]
        for i, h in enumerate(links[:nfollow]):
            save(f"{name}__{i}", urljoin(fin, h))
MG = {"epping": "https://rds.eppingforestdc.gov.uk", "maldon": "https://democracy.maldon.gov.uk", "southend": "https://democracy.southend.gov.uk",
      "thurrock": "https://democracy.thurrock.gov.uk", "tendring": "https://tdcdemocracy.tendringdc.gov.uk", "harlow": "https://moderngov.harlow.gov.uk",
      "basildon": "https://www.basildonmeetings.info", "brentwood": "https://brentwood.moderngov.co.uk", "uttlesford": "https://uttlesford.moderngov.co.uk"}
for c, b in MG.items():
    save(f"mg_{c}_cal", f"{b}/mgCalendarMonthView.aspx?M=10&Y=2026&GL=1", follow=r"ieListDocuments\.aspx", nfollow=2)
    save(f"mg_{c}_robots", f"{b}/robots.txt")
    save(f"mg_{c}_new", f"{b}/mgWhatsNew.aspx?bcr=1")
save("cmis_colchester_home", "https://colchester.cmis.uk.com/colchester/", follow=r"(?i)calendar|meetings", nfollow=2)
save("cmis_essex_cal", "https://cmis.essex.gov.uk/essexcmis5/CalendarofMeetings.aspx", follow=r"(?i)ViewMeetingPublic|/Meeting/", nfollow=2)
save("cmis_rochford_home", "https://rochford.cmis.uk.com/rochford", follow=r"(?i)calendar|ViewMeetingPublic", nfollow=2)
save("cmis_essex_robots", "https://cmis.essex.gov.uk/robots.txt")
save("chelmsford_list", "https://www.chelmsford.gov.uk/committee-meetings/", follow=r"committee-meetings/[a-z0-9\-]+-2026/?$", nfollow=2)
save("chelmsford_robots", "https://www.chelmsford.gov.uk/robots.txt")
save("braintree_list", "https://www.braintree.gov.uk/meetings", follow=r"/meetings/(meeting|committee)/", nfollow=2)
save("braintree_robots", "https://www.braintree.gov.uk/robots.txt")
save("castlepoint_home", "https://www.castlepoint.gov.uk", follow=r"(?i)meeting|agenda|committee|democra", nfollow=3)
json.dump({"at": datetime.now(timezone.utc).isoformat(), "pages": log}, open(f"{OUT}/_log.json", "w"), indent=1)
print(json.dumps({k: (v["status"], v["len"]) for k, v in log.items()}, indent=0))
