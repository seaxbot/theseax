#!/usr/bin/env python3
"""Publish an edition to theseax.com safely. Run from inside the repository checkout.

Newsroom:    python3 tools/publish.py --edition /tmp/edition.json --base <sha noted at the start of the run>
Sport desk:  python3 tools/publish.py --sport /tmp/sport.json      (replaces sport.results, sport.fixtures, sport.tables;
             merges the file's optional "stories" list into sport.stories by id)
Council Watch desk: python3 tools/publish.py --councilwatch /tmp/cw.json   (replaces only the edition's "councilwatch" list)
Inquest desk: python3 tools/publish.py --inquests /tmp/inq.json   ({"items": [...]}; each item has "section": "stories" or
             "courts"; merged into that list by id and marked desk "inquest"; the newsroom keeps them for 72 hours)
Scheduled owner stories: python3 tools/publish.py --items /tmp/x.json --desk owner   (same file format and merge, marked
             Any of these files may also carry a top-level "diary" list: merged by id into the news diary (tools/diary.py)
             desk "owner"; used by one-off scheduled tasks that publish a story the owner set up in advance)

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
  Before writing, newsroom and sport desk files are checked for front-page repetition (tools/repeats.py): a new or
  rewritten story that repeats a fact across its headline, summary and key points is refused (exit 5) until fixed.
  Every desk's new stories are also checked against everything the site has run in the last 21 days (tools/dupes.py,
  owner's rule 18 Nov 2026): a story the site has already run is refused (exit 6) unless it is a declared follow-up
  with a new development ("followUp" + "newAngle").
Prints PUSHED <hash> on success. Exit codes: 0 pushed, 2 bad input, 3 needs a manual merge, 4 push failed, 5 repeats,
6 repeat story.
"""
import argparse, json, os, re, subprocess, sys, time
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import policy
import repeats
import dupes
import legal
import verify
import diary
BOTS = {"The Seax newsroom", "The Seax sport desk", "The Seax council watch", "The Seax inquest desk", "The Seax scheduler", "The Seax photo desk", "The Seax policy"}
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

def _items(ed):
    """Every story-like item in an edition, across all sections."""
    for k in ("stories", "official", "courts", "community", "councilwatch"):
        for x in ed.get(k) or []:
            if isinstance(x, dict) and x.get("id"):
                yield x
    for x in (ed.get("sport") or {}).get("stories") or []:
        if isinstance(x, dict) and x.get("id"):
            yield x


def headline_snapshot(ed):
    return {x["id"]: (" ".join(str(x.get("headline") or "").split()), x.get("headlineAt")) for x in _items(ed)}


PLUS_RX = re.compile(r"(\d[\d,.]*(?:k|m|bn)?)-plus\b", re.I)


def plus_headlines(out):
    """Owner's rule (20 Nov 2026): headlines write a figure with "+", never "-plus" ("9,700+ tickets", not "9,700-plus")."""
    n = 0
    for x in _items(out):
        h = str(x.get("headline") or "")
        new = PLUS_RX.sub(r"\1+", h)
        if new != h:
            x["headline"] = new
            n += 1
    for x in (out.get("lead") or {}).get("history") or []:
        if isinstance(x, dict) and isinstance(x.get("headline"), str):
            x["headline"] = PLUS_RX.sub(r"\1+", x["headline"])
    if isinstance(out.get("ticker"), list):
        out["ticker"] = [PLUS_RX.sub(r"\1+", t) if isinstance(t, str) else t for t in out["ticker"]]
    return n


def stamp_headlines(out, prev):
    """Owner's rule (Nov 2026): whenever a story's headline changes, the time shown on the site moves to the
    time of the change. Stored as "headlineAt" (display only; the newsroom's freshness and lead rules ignore it)."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    changed = 0
    for x in _items(out):
        old = prev.get(x["id"])
        if not old:
            continue  # a new story: its own "time" is when it was posted
        head = " ".join(str(x.get("headline") or "").split())
        if old[0] and head != old[0]:
            x["headlineAt"] = now
            changed += 1
        elif old[1] and not x.get("headlineAt"):
            x["headlineAt"] = old[1]
    return changed


def merge_sport_stories(live_sport, live_stories, mine):
    """Merge the sport desk's stories into the live sport.stories by id."""
    cur = list(live_sport.get("stories") or [])
    front_ids = {x.get("id") for x in live_stories or []}
    pos = {x.get("id"): i for i, x in enumerate(cur)}
    for st in mine:
        if isinstance(st, dict) and st.get("id") and st.get("remove"):
            cur = [x for x in cur if x.get("id") != st["id"]]  # owner-requested removal (also list the id in tools/takedown.txt)
            pos = {x.get("id"): i for i, x in enumerate(cur)}
            continue
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

INQ_KEEP_H = 72
KEEP_DESKS = {"inquest", "owner"}  # desk items the newsroom keeps for INQ_KEEP_H hours

def merge_inquests(out, items, desk="inquest"):
    """Merge the inquest desk's items into stories or courts by id (replacing any copy in either list)."""
    n = 0
    for it in items:
        if it.get("remove"):
            for other in ("stories", "courts", "official", "community"):
                out[other] = [x for x in out.get(other) or [] if not (x.get("id") == it["id"] and x.get("desk") == desk)]
            n += 1
            continue
        # owner rewrites of "official" and "community" items stay in their own section (owner, 22 Nov 2026: research
        # every short story, including the official and community lists)
        okay = ("stories", "courts", "official", "community") if desk == "owner" else ("stories", "courts")
        sec = it.get("section") if it.get("section") in okay else "courts"
        it = {k: v for k, v in it.items() if k != "section"}
        it["desk"] = desk
        for other in ("stories", "courts", "official", "community"):
            out[other] = [x for x in out.get(other) or [] if x.get("id") != it["id"]]
        out.setdefault(sec, []).insert(0, it)
        n += 1
    for sec in ("stories", "courts"):
        out[sec] = newest_first(out.get(sec) or [])
    return n


def keep_inquests(out, live):
    """Newsroom runs: put back any recent inquest desk item that the newsroom's file dropped."""
    have = {x.get("id") for k in ("stories", "courts", "official", "community") for x in out.get(k) or []}
    cutoff = datetime.now(timezone.utc) - timedelta(hours=INQ_KEEP_H)
    back = 0
    for sec in ("stories", "courts", "official", "community"):
        for x in live.get(sec) or []:
            if x.get("desk") in KEEP_DESKS and x.get("id") not in have and (story_t(x) or cutoff) > cutoff:
                out.setdefault(sec, []).append(x); back += 1
        out[sec] = newest_first(out.get(sec) or [])
    return back

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--edition", help="full edition file from the newsroom")
    ap.add_argument("--sport", help="file with {results, fixtures, tables} from the sport desk")
    ap.add_argument("--councilwatch", help="file with the full Council Watch list (a JSON array, or {\"councilwatch\": [...]})")
    ap.add_argument("--inquests", "--items", dest="inquests", help="file with {\"items\": [...]} from the inquest desk (or a scheduled owner story with --desk owner)")
    ap.add_argument("--desk", default="inquest", choices=["inquest", "owner"], help="desk name stamped on --items")
    ap.add_argument("--base", help="commit the newsroom started from (git rev-parse HEAD at the start of the run)")
    ap.add_argument("--force", action="store_true", help="publish even if a person edited edition.json since --base")
    ap.add_argument("--author", help="commit author name")
    ap.add_argument("--dupes-ok", default="", help="comma-separated new story ids flagged as a repeat story that you checked and judged a different story (not a follow-up)")
    ap.add_argument("--legal-ok", default="", help="OWNER ONLY: comma-separated story ids the owner has decided to publish despite a legal gate hold")
    ap.add_argument("--repeats-ok", default="", help="comma-separated story ids whose repetition flag you checked and judged wrong")
    a = ap.parse_args()
    if sum(map(bool, (a.edition, a.sport, a.councilwatch, a.inquests))) != 1:
        sys.exit("give exactly one of --edition, --sport, --councilwatch or --inquests")
    mine = load(a.edition or a.sport or a.councilwatch or a.inquests)
    sent_diary = mine.get("diary") if isinstance(mine, dict) and isinstance(mine.get("diary"), list) else []
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
    elif a.inquests:
        items = mine.get("items") if isinstance(mine, dict) else mine
        bad = [x for x in items or [] if not (isinstance(x, dict) and x.get("id") and (x.get("remove") or (x.get("headline") and x.get("url"))))] if isinstance(items, list) else [1]
        if not isinstance(items, list) or bad:
            print("bad inquest file: needs {\"items\": [...]} with id, headline and url on every item"); sys.exit(2)
        mine = items
    else:
        if isinstance(mine, dict):
            mine = mine.get("councilwatch")
        if not isinstance(mine, list) or not all(isinstance(x, dict) and x.get("id") and x.get("headline") for x in mine):
            print("bad council watch file: needs a list of items with id and headline"); sys.exit(2)
    author = a.author or ("The Seax newsroom" if a.edition else "The Seax sport desk" if a.sport else
                          ("The Seax scheduler" if a.desk == "owner" else "The Seax inquest desk") if a.inquests else "The Seax council watch")

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
        prev_heads = headline_snapshot(live)
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
            kept = keep_inquests(out, live)
            if kept:
                print("inquest desk items kept:", kept)
        elif a.inquests:
            out = live
            print(f"{a.desk} items merged:", merge_inquests(out, mine, a.desk))
            out["updatedAt"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
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
        # never list the same story twice (owner's note, 12 Nov 2026, after one charity story appeared twice in Community):
        # within each list, keep the first copy of an id and drop later ones
        dropped = []
        for sec in ("stories", "official", "courts", "community", "councilwatch"):
            seen, keep = set(), []
            for x in out.get(sec) or []:
                i = x.get("id") if isinstance(x, dict) else None
                if i and i in seen:
                    dropped.append(i); continue
                if i: seen.add(i)
                keep.append(x)
            if sec in out: out[sec] = keep
        sp = out.get("sport") or {}
        if sp.get("stories"):
            in_stories = {x.get("id") for x in out.get("stories") or []}
            seen, keep = set(), []
            for x in sp["stories"]:
                i = x.get("id")
                if i in seen or i in in_stories:
                    dropped.append(i); continue
                seen.add(i); keep.append(x)
            sp["stories"] = keep
        if dropped:
            print("duplicates removed:", ", ".join(dropped))
        # news diary (owner's rule, 16 Nov 2026): kept from the live edition whatever a desk sends, merged by id
        # with any entries the desk adds, past entries pruned (tools/diary.py)
        out["diary"] = diary.merge(live.get("diary") or [], sent_diary)
        dprobs = diary.problems(out["diary"])
        if dprobs:
            print("DIARY WARNINGS (fix next run):", " | ".join(dprobs[:8]))
        print("diary:", len(out["diary"]), "entries")
        print("plus to +:", plus_headlines(out))
        print("headlines changed:", stamp_headlines(out, prev_heads))
        rep = policy.apply(out)
        print("policy:", json.dumps({k: (v if isinstance(v, int) else len(v)) for k, v in rep.items()}))
        # owner, 22 Nov 2026 ("we now need to make stories longer when we only have one source... find the story from
        # official sources"): list every news story still going out short (link-only or single source, not researched),
        # so each run researches them under ops/newsroom.md 3g ii MAKE IT OUR OWN until they grow
        thin = [s.get("id") for sec in ("stories", "official", "community") for s in out.get(sec) or []
                if isinstance(s, dict) and (s.get("linkOnly") or s.get("singleSource")) and not s.get("researched")]
        if thin:
            print(f"SHORT STORIES TO RESEARCH ({len(thin)}; 3g ii, owner 22 Nov: find the official source and make each one our own): " + ", ".join(thin[:25]))
        if a.edition and (out.get("lead") or {}).get("id") not in {s.get("id") for s in out.get("stories", [])}:
            print("bad edition: the lead story was removed by the source policy (opt-out outlet); choose another lead"); sys.exit(2)
        if a.edition or a.sport or a.inquests:
            secs = ("stories", "community", "official", "sport") if a.edition else ("stories", "courts") if a.inquests else ("sport",)
            fresh, older = repeats.check(out, live, secs)
            ok = {x.strip() for x in a.repeats_ok.split(",") if x.strip()}
            fresh = [f for f in fresh if f[0] not in ok]
            if fresh:
                print("REPEATS: these new or rewritten stories repeat a fact across headline, summary and key points "
                      "(the front page shows all three), or break the headline rules (ops/newsroom.md 3a vii). Fix them, then rerun:")
                for sid, probs in fresh:
                    print(f"  {sid}: " + "; ".join(probs))
                sys.exit(5)
            if older:
                print(f"older stories with repeats ({len(older)}; tidy up to 10 per run): " +
                      " | ".join(f"{sid}: {'; '.join(p)}" for sid, p in older[:10]))
        # repeat stories (owner's rule, 18 Nov 2026, after Fatima Whitbread's Freewoman of Brentwood honour ran on
        # 14 Nov and again under a new id on 18 Nov): nothing the site has already run goes up again as a new story
        # unless it is a declared follow-up with a new development (tools/dupes.py)
        arch_p = os.path.join(ROOT, "data", "archive.json")
        archive = load(arch_p) if os.path.exists(arch_p) else {}
        dok = {x.strip() for x in a.dupes_ok.split(",") if x.strip()}
        reps = [d for d in dupes.check(out, live, archive) if d[0] not in dok]
        if reps:
            print("REPEAT STORY: these new stories repeat something The Seax has already run (owner's rule, 18 Nov 2026). "
                  "Drop each one, or if it carries a genuine new development, update the earlier story instead (same id, "
                  "if it is still in the edition), or give the new story \"followUp\": \"<earlier id>\" and \"newAngle\": "
                  "\"<the new development in one sentence>\" and lead its headline and first paragraph with that new development. "
                  "Then rerun:")
            for sid, h, oid, oh, ot, shared in reps:
                print(f"  {sid}: \"{h}\"\n      already ran as {oid} (first {str(ot)[:10]}): \"{oh}\"")
            sys.exit(6)
        # legal gate (owner's go-ahead, 20 Nov 2026; tools/legal.py): a new or rewritten crime, court or inquest story
        # that fails a rule is held back from this edition; everything else publishes. Never exits: a held story must
        # not stop the news.
        lok = {x.strip() for x in a.legal_ok.split(",") if x.strip()}
        try:
            held, warned = legal.check(out, live, lok)
        except Exception as e:  # the gate must never break publishing
            held, warned = [], []
            print("legal gate error (nothing held):", type(e).__name__, str(e)[:200])
        if held:
            hold_ids = {h[1] for h in held}
            for sec in legal.SECTIONS:
                if isinstance(out.get(sec), list):
                    out[sec] = [it for it in out[sec] if not (isinstance(it, dict) and it.get("id") in hold_ids)]
            if isinstance(out.get("front"), list):
                out["front"] = [i for i in out["front"] if i not in hold_ids]
            if isinstance(out.get("lead"), dict) and out["lead"].get("id") in hold_ids:
                rest = [it for it in (out.get("stories") or []) if isinstance(it, dict) and it.get("id") not in (out.get("front") or [])]
                rest.sort(key=lambda it: -(it.get("weight") or 0))
                if rest:
                    out["lead"] = dict(out["lead"], id=rest[0]["id"])
            print("LEGAL HOLD: these stories were NOT published (tools/legal.py). Fix each as the reason says and send it "
                  "again in your next edition; never reword just to get past the check:")
            for sec, sid, h, probs in held:
                print(f"  {sid}: \"{h}\"")
                for pr in probs:
                    print("      " + pr)
        if warned:
            print("legal gate: already-live stories that would fail if rewritten (" + str(len(warned)) + "): " +
                  " | ".join(f"{sid}: {probs[0][:90]}" for _s, sid, _h, probs in warned[:6]))
        # TRIPLE CHECK (owner's rule, 20 Nov 2026: "Make sure triple checks are done before publishing on The Seax original
        # reporting!"; tools/verify.py). A new original or Council Watch story without a valid triple-check stamp for its
        # final words is held back; a rewrite of a live one without it keeps the live, already-checked version.
        if a.edition or a.inquests or a.councilwatch:
            try:
                unver = verify.gate(out, live, councilwatch_only=bool(a.councilwatch))
            except Exception as e:  # the gate must never break publishing
                unver = []
                print("triple check gate error (nothing held):", type(e).__name__, str(e)[:200])
            if unver:
                bad_ids = {sid for sid, _ in unver}
                live_ix = {}
                for sec in ("stories", "community", "official", "courts", "councilwatch"):
                    for it in live.get(sec) or []:
                        if isinstance(it, dict):
                            live_ix.setdefault((sec, it.get("id")), it)
                removed = set()
                for sec in ("stories", "community", "official", "courts", "councilwatch"):
                    if not isinstance(out.get(sec), list):
                        continue
                    keep = []
                    for it in out[sec]:
                        if isinstance(it, dict) and it.get("id") in bad_ids:
                            old = live_ix.get((sec, it.get("id")))
                            if old is not None:
                                keep.append(old)
                            else:
                                removed.add(it.get("id"))
                            continue
                        keep.append(it)
                    out[sec] = keep
                if isinstance(out.get("front"), list):
                    out["front"] = [i for i in out["front"] if i not in removed]
                if isinstance(out.get("lead"), dict) and out["lead"].get("id") in removed:
                    rest = [it for it in (out.get("stories") or []) if isinstance(it, dict) and it.get("id") not in (out.get("front") or [])]
                    rest.sort(key=lambda it: -(it.get("weight") or 0))
                    if rest:
                        out["lead"] = dict(out["lead"], id=rest[0]["id"])
                print("UNVERIFIED HOLD: these original-reporting stories were NOT published (new ones held back, rewrites "
                      "kept at their live version) because they have no valid triple check (tools/verify.py, owner's rule "
                      "20 Nov 2026). Do all three checks on the final words, stamp with tools/verify.py, and send them again:")
                for sid, why in unver:
                    print(f"  {sid}: {why}")
        # takedowns (owner's rule): ids in tools/takedown.txt never go back into the edition, whichever desk sends them
        tkp = os.path.join(ROOT, "tools", "takedown.txt")
        if os.path.exists(tkp):
            with open(tkp, encoding="utf-8") as f:
                tkn = {l.strip() for l in f if l.strip() and not l.startswith("#")}
            for sec in ("stories", "official", "community", "courts", "councilwatch"):
                if isinstance(out.get(sec), list):
                    out[sec] = [it for it in out[sec] if not (isinstance(it, dict) and it.get("id") in tkn)]
            if isinstance(out.get("sport"), dict) and isinstance(out["sport"].get("stories"), list):
                out["sport"]["stories"] = [it for it in out["sport"]["stories"] if it.get("id") not in tkn]
            if isinstance(out.get("front"), list):
                out["front"] = [i for i in out["front"] if i not in tkn]
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
        msg = ("Edition " if a.edition else "Sport desk " if a.sport else ("Scheduled story " if a.desk == "owner" else "Inquest desk ") if a.inquests else "Council Watch ") + out.get("updatedAt", "")
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
