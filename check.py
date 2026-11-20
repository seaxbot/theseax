#!/usr/bin/env python3
"""One-off independent recount of Essex Police street-level crime (data.police.uk) for the Seax crime story."""
import json, time, urllib.parse, urllib.request, urllib.error
UA = "TheSeaxNewsDesk/1.0 (+https://theseax.com/about/; info@theseax.com)"
def get(url, data=None, timeout=90):
    for a in range(5):
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 502, 503, 504): time.sleep(2 + 3 * a); continue
            raise
        except Exception:
            time.sleep(2 + 3 * a)
    raise RuntimeError("failed " + url)
out = {"lastUpdated": get("https://data.police.uk/api/crime-last-updated")}
hoods = get("https://data.police.uk/api/essex/neighbourhoods")
polys = {}
for h in hoods:
    b = get(f"https://data.police.uk/api/essex/{h['id']}/boundary")
    polys[h["id"]] = (h["name"], ":".join(f"{p['latitude']},{p['longitude']}" for p in b), len(b))
    time.sleep(0.1)
out["hoods"] = len(polys)
for month in ["2026-09", "2026-08", "2025-09"]:
    ids, cats, raw, per = {}, {}, 0, {}
    for hid, (name, poly, npts) in polys.items():
        cs = get("https://data.police.uk/api/crimes-street/all-crime", data=urllib.parse.urlencode({"poly": poly, "date": month}).encode())
        raw += len(cs); per[name] = len(cs)
        for c in cs:
            ids[c["id"]] = c["category"]
        time.sleep(0.1)
    for cat in ids.values():
        cats[cat] = cats.get(cat, 0) + 1
    nl = get(f"https://data.police.uk/api/crimes-no-location?category=all-crime&force=essex&date={month}")
    out[month] = {"rawSum": raw, "unique": len(ids), "noLocation": len(nl),
                  "cats": dict(sorted(cats.items(), key=lambda kv: -kv[1])), "perHood": per}
    print(month, raw, len(ids), len(nl), flush=True)
json.dump(out, open("result.json", "w"), indent=1)
