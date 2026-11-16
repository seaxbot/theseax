#!/usr/bin/env python3
"""The Seax news diary (owner's rule, 16 Nov 2026).

Owner: "when looking at stories we're publishing, remember key dates and then write stories on or day before
those key dates previewing what's going to happen - this creates a loop where the newsroom is across everything".

The diary lives in edition.json under the top-level key "diary" (a list), so it travels with the edition, is kept
by every desk and is preserved by tools/publish.py even if a desk's file leaves it out. Entry shape:

  {"id": "d-<slug>", "date": "YYYY-MM-DD" (UK date of the event), "time": "HH:MM" UK or "",
   "what": short neutral description, "place": Essex town(s), "areas": [...],
   "kind": inquiry|meeting|decision|court|hearing|inquest|opening|closure|roadworks|event|deadline|launch|strike|vote|other,
   "storyId": id of the story the date came from, "url": source that states the date,
   "added": ISO UTC, "status": open|previewed|done|dropped,
   "previewId": id of the preview story (or ""), "followId": id of the outcome story or update (or ""), "note": ""}

Commands (run from the checkout; FILE defaults to edition.json):
  python3 tools/diary.py due [FILE]       entries the newsroom must act on this run, and the week ahead
  python3 tools/diary.py check [FILE]     validate entries (exit 1 on problems)
"""
import json, os, re, sys
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    UK = ZoneInfo("Europe/London")
except Exception:  # pragma: no cover
    UK = timezone.utc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KINDS = {"inquiry", "meeting", "decision", "court", "hearing", "inquest", "opening", "closure", "roadworks",
         "event", "deadline", "launch", "strike", "vote", "other"}
STATUSES = {"open", "previewed", "done", "dropped"}
KEEP_DAYS = 14  # entries whose date is more than this many days past are pruned


def today_uk():
    return datetime.now(timezone.utc).astimezone(UK).date()


def ddate(e):
    try:
        return datetime.strptime(str(e.get("date", ""))[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def merge(live, mine):
    """Union of two diaries by id; entries in `mine` win. Past entries older than KEEP_DAYS are pruned."""
    out, order = {}, []
    for src in (live or [], mine or []):
        for e in src:
            if not isinstance(e, dict) or not e.get("id"):
                continue
            if e["id"] not in out:
                order.append(e["id"])
            out[e["id"]] = e
    cutoff = today_uk() - timedelta(days=KEEP_DAYS)
    res = [out[i] for i in order if (ddate(out[i]) or cutoff) >= cutoff]
    res.sort(key=lambda e: (str(e.get("date", "")), str(e.get("time", ""))))
    return res


def problems(diary, ids=()):
    probs, seen = [], set()
    for e in diary or []:
        i = e.get("id", "")
        if not re.fullmatch(r"d-[a-z0-9-]+", str(i)):
            probs.append(f"{i or '?'}: id must be 'd-' plus lowercase letters, digits and hyphens")
        if i in seen:
            probs.append(f"{i}: duplicate id")
        seen.add(i)
        if not ddate(e):
            probs.append(f"{i}: date must be YYYY-MM-DD")
        if e.get("kind") not in KINDS:
            probs.append(f"{i}: kind must be one of {', '.join(sorted(KINDS))}")
        if e.get("status", "open") not in STATUSES:
            probs.append(f"{i}: status must be one of {', '.join(sorted(STATUSES))}")
        if not e.get("what") or not e.get("url"):
            probs.append(f"{i}: needs 'what' and the 'url' of a source that states the date")
        if "—" in json.dumps(e, ensure_ascii=False):
            probs.append(f"{i}: no em dashes")
    return probs


def due(diary):
    t = today_uk()
    act, follow, ahead = [], [], []
    for e in diary or []:
        d, st = ddate(e), e.get("status", "open")
        if not d or st in ("dropped", "done"):
            continue
        if st == "open" and t <= d <= t + timedelta(days=1):
            act.append(e)
        elif (t - timedelta(days=3) <= d < t) or (d == t and st == "previewed"):
            follow.append(e)
        elif t + timedelta(days=1) < d <= t + timedelta(days=7):
            ahead.append(e)
    return act, follow, ahead


def line(e):
    when = e.get("date", "") + (" " + e["time"] if e.get("time") else "")
    extra = f" [preview {e['previewId']}]" if e.get("previewId") else ""
    return f"  {e.get('id')}  {when}  ({e.get('kind')}, {e.get('place', '')}) {e.get('what', '')}  <- {e.get('storyId', '')}{extra}"


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "due"
    path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "edition.json")
    with open(path, encoding="utf-8") as f:
        diary = json.load(f).get("diary") or []
    if cmd == "check":
        p = problems(diary)
        print("\n".join(p) if p else f"diary ok: {len(diary)} entries")
        sys.exit(1 if p else 0)
    act, follow, ahead = due(diary)
    t = today_uk()
    print(f"NEWS DIARY, {t.isoformat()} (UK): {len(diary)} entries")
    print(f"PREVIEW NOW (open, today or tomorrow): {len(act)}")
    for e in act: print(line(e))
    print(f"FOLLOW UP (event today after its preview, or in the last 3 days, not done): {len(follow)}")
    for e in follow: print(line(e))
    print(f"COMING UP (next 7 days, for planning only): {len(ahead)}")
    for e in ahead: print(line(e))


if __name__ == "__main__":
    main()
