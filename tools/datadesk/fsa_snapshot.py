"""One-off snapshot of every Food Standards Agency hygiene rating held by the 14 Essex councils, for The Seax's
weekend analysis (owner's choice, 27 Nov 2026). Writes OUT/fsa-<council>.json and OUT/summary.json. Open
Government Licence data from api.ratings.food.gov.uk."""
import json, os, sys, time, urllib.request, urllib.parse

FSA = "https://api.ratings.food.gov.uk"
H = {"x-api-version": "2", "Accept": "application/json", "User-Agent": "TheSeax-datadesk/1.0 (theseax.com)"}
COUNCILS = ["Basildon", "Braintree", "Brentwood", "Castle Point", "Chelmsford", "Colchester", "Epping Forest", "Harlow",
            "Maldon", "Rochford", "Southend-On-Sea", "Tendring", "Thurrock", "Uttlesford"]
OUT = sys.argv[1] if len(sys.argv) > 1 else "."
os.makedirs(OUT, exist_ok=True)

def get(url):
    for i in range(4):
        try:
            req = urllib.request.Request(url, headers=H)
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r)
        except Exception as e:
            print("retry", i, url, e); time.sleep(5 * (i + 1))
    raise SystemExit("failed " + url)

auths = get(FSA + "/Authorities/basic").get("authorities") or []
ids = {}
for a in auths:
    nm = str(a.get("Name") or "")
    for c in COUNCILS:
        if nm.lower() == c.lower() or nm.lower().replace("-", " ") == c.lower().replace("-", " "):
            ids[c] = a.get("LocalAuthorityId")
print("councils found:", ids, "missing:", [c for c in COUNCILS if c not in ids])
summary = {}
for c, aid in ids.items():
    rows, page = [], 1
    while True:
        q = urllib.parse.urlencode({"localAuthorityId": aid, "pageSize": 5000, "pageNumber": page})
        d = get(FSA + "/Establishments?" + q)
        est = d.get("establishments") or []
        for x in est:
            sc = x.get("scores") or {}
            geo = x.get("geocode") or {}
            rows.append({"id": x.get("FHRSID"), "name": x.get("BusinessName"), "type": x.get("BusinessType"),
                         "typeId": x.get("BusinessTypeID"), "a1": x.get("AddressLine1"), "a2": x.get("AddressLine2"),
                         "a3": x.get("AddressLine3"), "a4": x.get("AddressLine4"), "pc": x.get("PostCode"),
                         "rating": x.get("RatingValue"), "date": x.get("RatingDate"), "pending": x.get("NewRatingPending"),
                         "hyg": sc.get("Hygiene"), "str": sc.get("Structural"), "man": sc.get("ConfidenceInManagement"),
                         "lat": geo.get("latitude"), "lon": geo.get("longitude"), "la": x.get("LocalAuthorityName")})
        meta = d.get("meta") or {}
        tp = meta.get("totalPages") or 1
        print(c, "page", page, "of", tp, len(est))
        if page >= tp or not est:
            break
        page += 1; time.sleep(1)
    json.dump(rows, open(os.path.join(OUT, f"fsa-{c.lower().replace(' ', '-')}.json"), "w"), ensure_ascii=False)
    summary[c] = len(rows)
    time.sleep(1)
summary["_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
json.dump(summary, open(os.path.join(OUT, "summary.json"), "w"), indent=1)
print(summary)
