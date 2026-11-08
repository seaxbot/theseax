#!/usr/bin/env python3
"""Publish an edition to theseax.com safely. Run from inside the repository checkout.

Newsroom:    python3 tools/publish.py --edition /tmp/edition.json --base <sha noted at the start of the run>
Sport desk:  python3 tools/publish.py --sport /tmp/sport.json      (replaces sport.results, sport.fixtures, sport.tables;
             merges the file's optional "stories" list into sport.stories by id)
Council Watch desk: python3 tools/publish.py --councilwatch /tmp/cw.json   (replaces only the edition's "councilwatch" list)

What it does, retrying up to 4 times if someone else pushes first:
  1. fetches origin/main and resets this checkout to it (only edition.json and built files ever change here)
  2. newsroom: refuses (exit 3) if a person, not a bot, changed edition.json since --base, unless --force
  3. newsroom: takes sport.results, sport.fixtures and sport.tables from the live file (the sport desk owns them),
     and the "councilwatch" list (the Council Watch desk owns it); also puts back any sport desk match report
     (desk "sport", under 72 hours old) that is missing from the newsroom's file, so a newsroom run that started
     before the sport desk pushed cannot wipe it
  4. applies the owner's source and copyright policy (tools/policy.py: no features, link-only outlets,
     single-source length cap, opt-outs) to the whole edition
  5. writes edition.json, runs tools/build.py (story pages, sitemaps, feeds, briefing), commits and pushes
If the build fails, the edition is still published without the built pages.
Prints PUSHED <hash> on success. Exit codes: 0 pushed, 2 bad input, 3 needs a manual merge, 4 push failed.
"""
import argparse, json, os, subprocess, sys, time
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import policy
BOTS = {"The Seax newsroom", "The Seax sport desk", "The Seax council watch", "The Seax photo desk", "The Seax policy"}
SPORT_KEYS = ("results", "fixtures", "tables")

def git(*a, check=True):
    r = subprocess.run(["git", "-C", ROOT, *a], capture_output=True, text=True)
    if check and r.returncode:
        raise RuntimeError(f"git {' '.join(a)}: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout.strip()

def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)

def dump(obj, p):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))

def parse_t(v):
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except Exception:
        return None

def story_t(s):
    ts = [t for t in (parse_t(s.get("updated")), parse_t(s.get("time"))) if t]
    return max(ts) if ts else None

def newest_first(stories):
    floor = datetime(1970, 1, 1, tzinfo=timezone.utc)
    return sorted(stories, key=lambda s: story_t(s) or floor, reverse=True)

def merge_sport_stories(live_sport, live_stories, mine):
    """Merge the sport desk's stories into the live sport.stories by id."""
    cur = list(live_sport.get("stories") or [])
    front_ids = {x.get("id") for x in live_stories or []}
    pos = {x.get("id"): i for i, x in enumerate(cur)}
    for st in mine:
        if not isinstance(st, dict) or not st.get("id") or not st.get("headline"):
            continue
        if st["id"] in front_ids:
            continue  # the newsroom has moved it to the front page; it owns it there
        st = dict(st, desk="sport")
        st.pop("img", None)
        if st["id"] in pos:
            cur[pos[st["id"]]] = st
        else:
            cur.append(st)
    return newest_first(cur)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--edition", help="full edition file from the newsroom")
    ap.add_argument("--sport", help="file with {results, fixtures, tables} from the sport desk")
    ap.add_argument("--councilwatch", help="file with the full Council Watch list (a JSON array, or {\"councilwatch\": [...]})")
    ap.add_argument("--base", help="commit the newsroom started from (git rev-parse HEAD at the start of the run)")
    ap.add_argument("--force", action="store_true", help="publish even if a person edited edition.json since --base")
    ap.add_argument("--author", help="commit author name")
    a = ap.parse_args()
    if sum(map(bool, (a.edition, a.sport, a.councilwatch))) != 1:
        sys.exit("give exactly one of --edition, --sport or --councilwatch")
    mine = load(a.edition or a.sport or a.councilwatch)
    if a.edition:
        if not isinstance(mine.get("stories"), list) or not mine.get("updatedAt"):
            print("bad edition: needs stories and updatedAt"); sys.exit(2)
        ids = {s.get("id") for s in mine["stories"]}
        if (mine.get("lead") or {}).get("id") not in ids:
            print("bad edition: lead id is not in stories"); sys.exit(2)
    elif a.sport:
        if not all(isinstance(mine.get(k), list) for k in SPORT_KEYS):
            print("bad sport file: needs results, fixtures and tables lists"); sys.exit(2)
        if not isinstance(mine.get("stories", []), list):
            print("bad sport file: stories must be a list"); sys.exit(2)
    else:
        if isinstance(mine, dict):
            mine = mine.get("councilwatch")
        if not isinstance(mine, list) or not all(isinstance(x, dict) and x.get("id") and x.get("headline") for x in mine):
            print("bad council watch file: needs a list of items with id and headline"); sys.exit(2)
    author = a.author or ("The Seax newsroom" if a.edition else "The Seax sport desk" if a.sport else "The Seax council watch")

    for attempt in range(1, 5):
        git("fetch", "--depth=60", "origin", "main")
        remote = git("rev-parse", "origin/main")
        if a.edition and a.base and not a.force:
            try:
                log = git("log", "--format=%H|%an", f"{a.base}..origin/main", "--", "edition.json")
            except RuntimeError:
                log = ""
            humans = [l for l in log.splitlines() if l and l.split("|", 1)[1] not in BOTS]
            if humans:
                print("NEEDS MERGE: edition.json was changed by an editor since your run started:")
                print("\n".join(humans))
                print("Read the live edition.json, keep the editor's changes in your edition, then rerun with --force.")
                sys.exit(3)
        git("reset", "--hard", "origin/main")
        live = load(os.path.join(ROOT, "edition.json"))
        if a.edition:
            out = mine
            out.setdefault("sport", {})
            for k in SPORT_KEYS:
                out["sport"][k] = (live.get("sport") or {}).get(k, [])
            out["councilwatch"] = live.get("councilwatch", [])
            # keep recent sport desk match reports the newsroom's copy did not have
            have = {x.get("id") for x in out.get("stories", [])} | {x.get("id") for x in out["sport"].get("stories", [])}
            cutoff = datetime.now(timezone.utc) - timedelta(hours=72)
            back = [x for x in (live.get("sport") or {}).get("stories", [])
                    if x.get("desk") == "sport" and x.get("id") not in have and (story_t(x) or cutoff) > cutoff]
            out["sport"]["stories"] = newest_first(list(out["sport"].get("stories", [])) + back)
        elif a.councilwatch:
            out = live
            out["councilwatch"] = mine
        else:
            out = live
            out.setdefault("sport", {})
            for k in SPORT_KEYS:
                out["sport"][k] = mine[k]
            out["sport"]["stories"] = merge_sport_stories(out["sport"], out.get("stories", []), mine.get("stories", []))
            out["updatedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        rep = policy.apply(out)
        print("policy:", json.dumps({k: (v if isinstance(v, int) else len(v)) for k, v in rep.items()}))
        if a.edition and (out.get("lead") or {}).get("id") not in {s.get("id") for s in out.get("stories", [])}:
            print("bad edition: the lead story was removed by the source policy (opt-out outlet); choose another lead"); sys.exit(2)
        dump(out, os.path.join(ROOT, "edition.json"))
        built = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "build.py")], capture_output=True, text=True)
        if built.returncode:
            print("WARNING build failed, publishing the edition only:", (built.stderr or built.stdout)[-800:])
            git("checkout", "--", ".", check=False)  # undo partial build output (edition.json is rewritten next)
            git("clean", "-fdq", "story", "briefing", "about", check=False)
            dump(out, os.path.join(ROOT, "edition.json"))
        else:
            print(built.stdout.strip())
        git("add", "-A")
        if not git("status", "--porcelain"):
            print("NOTHING TO PUSH (identical to live)"); return
        msg = ("Edition " if a.edition else "Sport desk " if a.sport else "Council Watch ") + out.get("updatedAt", "")
        git("-c", f"user.name={author}", "-c", "user.email=seaxbot@users.noreply.github.com", "commit", "-q", "-m", msg)
        r = subprocess.run(["git", "-C", ROOT, "push", "origin", "HEAD:main"], capture_output=True, text=True)
        if r.returncode == 0:
            print("PUSHED", git("rev-parse", "--short", "HEAD"), f"(attempt {attempt}, remote was {remote[:7]})")
            return
        print(f"push rejected on attempt {attempt}: {r.stderr.strip()[-300:]}")
        time.sleep(3 * attempt)
    print("PUSH FAILED after 4 attempts"); sys.exit(4)

if __name__ == "__main__":
    main()
