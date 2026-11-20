"""Daily GoatCounter read-out for The Seax (owner gave a read-only API key on 20 Nov 2026, saved as the GitHub secret
GOATCOUNTER_TOKEN; it is never written to the repo). Saves most-read pages and where readers came from, for the last
24 hours and 7 days, to OUT/goatcounter.json on the "stats-data" branch. Desks read it; the site may show a ranked
most-read list with no numbers (owner's choice, 20 Nov 2026)."""
import json, os, sys, urllib.request, urllib.parse
from datetime import datetime, timedelta, timezone

API = "https://theseax.goatcounter.com/api/v0"
TOKEN = os.environ.get("GOATCOUNTER_TOKEN", "").strip()
OUT = sys.argv[1] if len(sys.argv) > 1 else "."

def get(path, **q):
    url = API + path + ("?" + urllib.parse.urlencode(q) if q else "")
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def window(hours):
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    start = end - timedelta(hours=hours)
    f = "%Y-%m-%dT%H:%M:%SZ"
    q = {"start": start.strftime(f), "end": end.strftime(f)}
    out = {"start": q["start"], "end": q["end"]}
    try:
        out["total"] = get("/stats/total", **q)
    except Exception as e:
        out["totalError"] = str(e)[:200]
    try:
        h = get("/stats/hits", limit=50, **q)
        out["pages"] = [{"path": x.get("path"), "title": x.get("title"), "count": x.get("count")} for x in h.get("hits", [])]
    except Exception as e:
        out["pagesError"] = str(e)[:200]
    try:
        r = get("/stats/toprefs", limit=30, **q)
        out["referrers"] = [{"name": x.get("name") or "(direct or unknown)", "count": x.get("count")} for x in r.get("stats", [])]
    except Exception as e:
        out["referrersError"] = str(e)[:200]
    return out

if not TOKEN:
    sys.exit("GOATCOUNTER_TOKEN secret is not set")
data = {"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "day": window(24), "week": window(24 * 7)}
os.makedirs(OUT, exist_ok=True)
json.dump(data, open(os.path.join(OUT, "goatcounter.json"), "w"), ensure_ascii=False, indent=1)
d = data["day"]
print("24h:", json.dumps(d.get("total"))[:200], "| top:", [p["path"] for p in d.get("pages", [])[:5]],
      "| errors:", {k: v for k, v in d.items() if k.endswith("Error")})
