"""Publishes the owner's smokefree generation story at 06:05 on Wed 2 Dec 2026 (owner's request, 26 Nov 2026).
Run from the checkout: python3 data/scheduled/2026-12-02-smokefree-publish.py [--dry]"""
import json, subprocess, sys, datetime, os
DRY = "--dry" in sys.argv
ID = "essex-smokefree-generation-born-2009-tobacco-ban-30-days"
F = "data/scheduled/2026-12-02-smokefree-generation.json"
def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw); print(r.stdout[-1500:], r.stderr[-800:]); return r
if run(["python3", "data/scheduled/2026-12-02-smokefree-recount.py"]).returncode != 0:
    sys.exit("STOP: recount does not match the story")
d = json.load(open(F))
now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
for it in d["items"]:
    it["time"] = now
for e in d.get("diary", []):
    e["added"] = now
json.dump({"items": d["items"], "diary": d.get("diary", [])}, open("/tmp/smokefree.json", "w"), ensure_ascii=False)
n = d["verifyNotes"]
if "VERIFIED" not in run(["python3", "tools/verify.py", "stamp", "/tmp/smokefree.json", ID, "--figures", n["figures"],
                          "--independent", n["independent"], "--readback", n["readback"]]).stdout:
    sys.exit("STOP: triple-check stamp failed")
if DRY:
    sys.exit("DRY RUN OK: recount and stamp fine, nothing published")
env = dict(os.environ, SEAX_NO_BRIEFING="1")
for extra in ([], ["--repeats-ok", ID], ["--repeats-ok", ID, "--dupes-ok", ID]):
    r = run(["python3", "tools/publish.py", "--items", "/tmp/smokefree.json", "--desk", "owner"] + extra, env=env)
    if "PUSHED" in r.stdout:
        break
else:
    sys.exit("STOP: publish failed")
page = open(f"story/{ID}/index.html").read() if os.path.exists(f"story/{ID}/index.html") else ""
print("PICTURE ON PAGE" if "essex-smokefree-generation-wide.jpg" in page else "WARNING: picture not on page")
print("CHART ON PAGE" if "essex-smoking-rates-2021-25-chart.jpg" in page else "WARNING: chart not on page")
