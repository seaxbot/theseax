"""Independent check for the weekend hygiene analysis (27 Nov 2026): downloads the FSA's own daily open data XML file
for each Essex council (the FileName listed by /Authorities) and counts ratings by business type, so the API snapshot
can be checked against a second source."""
import json, os, sys, time, urllib.request, xml.etree.ElementTree as ET, collections
H = {"x-api-version": "2", "Accept": "application/json", "User-Agent": "TheSeax-datadesk/1.0 (theseax.com)"}
OUT = sys.argv[1] if len(sys.argv) > 1 else "."
os.makedirs(OUT, exist_ok=True)
NAMES = ["Basildon", "Braintree", "Brentwood", "Castle Point", "Chelmsford", "Colchester", "Epping Forest", "Harlow",
         "Maldon", "Rochford", "Southend-On-Sea", "Tendring", "Thurrock", "Uttlesford"]
def fetch(url, hdr):
    for i in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=120) as r:
                return r.read()
        except Exception as e:
            print("retry", i, url, e); time.sleep(5 * (i + 1))
    raise SystemExit("failed " + url)
auths = json.loads(fetch("https://api.ratings.food.gov.uk/Authorities", H)).get("authorities") or []
res = {}
for a in auths:
    if a.get("Name") not in NAMES: continue
    fn = a.get("FileName"); print(a.get("Name"), fn, a.get("EstablishmentCount"), a.get("LastPublishedDate"))
    xml = fetch(fn, {"User-Agent": H["User-Agent"]})
    root = ET.fromstring(xml)
    cnt = collections.Counter(); n = 0
    for e in root.iter("EstablishmentDetail"):
        n += 1
        cnt[(e.findtext("BusinessType") or "", e.findtext("RatingValue") or "")] += 1
    res[a["Name"]] = {"file": fn, "count": n, "apiCount": a.get("EstablishmentCount"), "published": a.get("LastPublishedDate"),
                      "byTypeRating": {f"{k[0]}|{k[1]}": v for k, v in cnt.items()}}
json.dump(res, open(os.path.join(OUT, "xmlcheck.json"), "w"), indent=1)
print({k: (v["count"], v["apiCount"]) for k, v in res.items()})
