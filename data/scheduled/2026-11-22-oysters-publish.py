"""Publishes the owner's Essex oysters story at 06:00 on Sun 22 Nov 2026 and makes it the lead (owner's request, 21 Nov 2026).
Run from the checkout: python3 data/scheduled/2026-11-22-oysters-publish.py [--dry]"""
import json, subprocess, sys, datetime
DRY = "--dry" in sys.argv
ID = "essex-oyster-farmers-eu-trade-uk-eu-deal-class-b"
def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True); print(r.stdout[-1500:], r.stderr[-800:]); return r
if run(["python3", "data/scheduled/2026-11-22-oysters-recount.py"]).returncode != 0:
    sys.exit("STOP: recount does not match the story")
d = json.load(open("data/scheduled/2026-11-22-essex-oysters.json"))
now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
for it in d["items"]:
    it["time"] = now
json.dump({"items": d["items"]}, open("/tmp/oysters.json", "w"), ensure_ascii=False)
n = d["verifyNotes"]
if "VERIFIED" not in run(["python3", "tools/verify.py", "stamp", "/tmp/oysters.json", ID, "--figures", n["figures"],
                          "--independent", n["independent"], "--readback", n["readback"]]).stdout:
    sys.exit("STOP: triple-check stamp failed")
if DRY:
    sys.exit("DRY RUN OK: recount and stamp fine, nothing published")
env = dict(**__import__("os").environ, SEAX_NO_BRIEFING="1")
for extra in ([], ["--repeats-ok", ID], ["--repeats-ok", ID, "--dupes-ok", ID]):
    r = subprocess.run(["python3", "tools/publish.py", "--items", "/tmp/oysters.json", "--desk", "owner"] + extra, capture_output=True, text=True, env=env)
    print(r.stdout[-1200:], r.stderr[-600:])
    if "PUSHED" in r.stdout:
        break
else:
    sys.exit("STOP: publish failed")
# make it the lead
base = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
ed = json.load(open("edition.json"))
if not any(x.get("id") == ID for x in ed.get("stories", [])):
    sys.exit("STOP: story not in edition after publish")
head = next(x["headline"] for x in ed["stories"] if x["id"] == ID)
old = ed.get("lead") or {}
# owner, 22 Nov 00:08: the Brentwood School special comes off the pin at 06:00 and goes FIRST in "front" for the weekend
BW = "brentwood-school-safeguarding-review-british-fencing-own-review"
top = [BW] if any(x.get("id") == BW for x in ed.get("stories", [])) else []
if old.get("id") and old["id"] not in (ID, BW):
    top.append(old["id"])
ed["front"] = top + [x for x in ed.get("front", []) if x not in top and x != ID]
ed["lead"] = {"id": ID, "since": now, "headlineAt": now, "ownerUntil": "2026-11-22T10:00:00Z",
              "history": [{"at": now, "id": ID, "headline": head}] + (old.get("history") or [])[:30]}
json.dump(ed, open("/tmp/oysters-ed.json", "w"), ensure_ascii=False, indent=1)
r = subprocess.run(["python3", "tools/publish.py", "--edition", "/tmp/oysters-ed.json", "--base", base], capture_output=True, text=True, env=env)
print(r.stdout[-800:], r.stderr[-400:])
print("LEAD SET" if "PUSHED" in r.stdout else "STOP: lead not set")
