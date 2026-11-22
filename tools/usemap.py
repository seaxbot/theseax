#!/usr/bin/env python3
"""Switch a story's picture to the map (owner's rule, 22 Nov 2026).

Used by the Facebook groups desk (ops/fbgroups.md) before posting a story whose picture is a town, Wikimedia
Commons or stock photo that does not show where the story happened or what it is about (the owner's example:
a Colchester Castle photo on the B&M shop opening story). Adds the id to data/map-pictures.json, which
tools/policy.py turns into "showMap": true on every publish and build, sets it on the live edition.json at once,
rebuilds the story pages and pushes.

    python3 tools/usemap.py <story-id> "<why, a few words>"

Prints PUSHED <hash> on success. Exit codes: 0 pushed (or already a map), 2 bad input, 4 push failed.
"""
import json, os, subprocess, sys, time
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP_FILE = os.path.join(ROOT, "data", "map-pictures.json")
AUTHOR = "The Seax policy"


def git(*a, check=True):
    r = subprocess.run(["git", "-C", ROOT, *a], capture_output=True, text=True)
    if check and r.returncode:
        raise RuntimeError(f"git {' '.join(a)}: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout.strip()


def items(ed):
    for sec in ("stories", "official", "community", "courts", "councilwatch"):
        for it in ed.get(sec) or []:
            if isinstance(it, dict):
                yield it
    sport = ed.get("sport") if isinstance(ed.get("sport"), dict) else {}
    for it in sport.get("stories") or []:
        if isinstance(it, dict):
            yield it


def main():
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        print(__doc__); sys.exit(2)
    sid, why = sys.argv[1].strip(), (sys.argv[2] if len(sys.argv) > 2 else "").strip()
    for attempt in range(1, 5):
        git("fetch", "-q", "--depth=20", "origin", "main")
        git("reset", "-q", "--hard", "origin/main")
        ep = os.path.join(ROOT, "edition.json")
        ed = json.load(open(ep, encoding="utf-8"))
        hit = [it for it in items(ed) if it.get("id") == sid]
        if not hit:
            print(f"no story with id {sid} in the live edition"); sys.exit(2)
        try:
            d = json.load(open(MAP_FILE, encoding="utf-8"))
        except (OSError, ValueError):
            d = {"ids": []}
        ids = d.setdefault("ids", [])
        if any((x.get("id") if isinstance(x, dict) else x) == sid for x in ids) and all(it.get("showMap") is True for it in hit):
            print("ALREADY A MAP", sid); return
        if not any((x.get("id") if isinstance(x, dict) else x) == sid for x in ids):
            ids.append({"id": sid, "why": why, "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
        with open(MAP_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
        for it in hit:
            it["showMap"] = True
        with open(ep, "w", encoding="utf-8") as f:
            json.dump(ed, f, ensure_ascii=False, separators=(",", ":"))
        built = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "build.py")], capture_output=True, text=True)
        if built.returncode:
            print("WARNING build failed, pushing the map choice only:", (built.stderr or built.stdout)[-600:])
            git("checkout", "--", ".", check=False)
            git("clean", "-fdq", "story", "briefing", "about", check=False)
            with open(MAP_FILE, "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, indent=1)
            with open(ep, "w", encoding="utf-8") as f:
                json.dump(ed, f, ensure_ascii=False, separators=(",", ":"))
        git("add", "-A")
        git("-c", f"user.name={AUTHOR}", "-c", "user.email=seaxbot@users.noreply.github.com", "commit", "-q",
            "-m", f"Map picture for {sid}" + (f": {why}" if why else ""))
        r = subprocess.run(["git", "-C", ROOT, "push", "origin", "HEAD:main"], capture_output=True, text=True)
        if r.returncode == 0:
            print("PUSHED", git("rev-parse", "--short", "HEAD"), f"(attempt {attempt})")
            return
        print(f"push rejected on attempt {attempt}: {r.stderr.strip()[-300:]}")
        time.sleep(3 * attempt)
    print("PUSH FAILED after 4 attempts"); sys.exit(4)


if __name__ == "__main__":
    main()
