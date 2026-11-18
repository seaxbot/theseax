"""Repeat-story check (owner's rule, 18 Nov 2026, after the Fatima Whitbread Freewoman of Brentwood story ran on
14 Nov and then again, from a different outlet under a new id, on 18 Nov): a story the site has already run must not
go up again as a new story unless there is a new angle or a new development.

How it works: every story that is new to the edition (an id not in the live edition) is compared with every story
page the site has built in the last LOOKBACK_DAYS (data/archive.json) and with every story in the live edition.
Headlines are compared on their distinctive words (names, places, things), weighted so that words the site uses all
the time ("Essex", "police", "council", "crash") count for little and rare ones ("Whitbread", "Freewoman") count for
a lot. A close match is a likely repeat.

A genuine follow-up is allowed only when the story says what is new, in two fields:
  "followUp": "<id of the earlier story>"
  "newAngle": "<one sentence: the new development or angle, e.g. 'the ceremony took place on Tuesday night'>"
Better still, when the earlier story is still in the edition, update that story (same id) instead of adding a new one.
Used by tools/publish.py (exit 6, "REPEAT STORY")."""
import math, re
from datetime import datetime, timezone, timedelta

LOOKBACK_DAYS = 21
THRESHOLD = 0.6     # share of the smaller headline's distinctive weight that the two headlines have in common
MIN_SHARED = 3      # and at least this many distinctive words in common
STOP = set("""the a an and or of to in on at for by with from as is are was were be been has have had it its this that
his her their our after over into up out new more than will would could not no but who which what when where why how
all can may set get gets got make makes made back off down being them they she he him you your we us one two three
four five six seven eight nine ten first last year years day days week weeks month months today tonight now still just
says said say told tells calls call plan plans bid hit hits sees see seen amid after before during near""".split())


def _norm(t):
    return re.sub(r"[^a-z0-9£%]+", " ", str(t or "").lower().replace("'s", "").replace("’s", "")).strip()


def toks(t):
    return {w for w in _norm(t).split() if len(w) > 2 and w not in STOP and not w.isdigit()}


def _parse(v):
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except Exception:
        return None


def _idf(docs):
    df = {}
    for d in docs:
        for w in d:
            df[w] = df.get(w, 0) + 1
    n = max(1, len(docs))
    return lambda w: math.log((n + 1) / (df.get(w, 0) + 1)) + 0.1


def score(a, b, idf):
    """(score, shared words) for two headline token sets."""
    shared = a & b
    if not shared:
        return 0.0, shared
    wa, wb = sum(map(idf, a)), sum(map(idf, b))
    return sum(map(idf, shared)) / max(1e-9, min(wa, wb)), shared


def _items(ed):
    for k in ("stories", "official", "courts", "community", "councilwatch"):
        for x in ed.get(k) or []:
            if isinstance(x, dict) and x.get("id"):
                yield x
    for x in (ed.get("sport") or {}).get("stories") or []:
        if isinstance(x, dict) and x.get("id"):
            yield x


def check(out, live, archive, now=None):
    """Stories new to this edition that look like a repeat of something already run.
    Returns a list of (new_id, new_headline, old_id, old_headline, old_first_seen, shared_words)."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=LOOKBACK_DAYS)
    live_ids = {x["id"] for x in _items(live)}
    # earlier stories: recent archive records plus everything in the live edition
    earlier = {}
    for sid, r in (archive or {}).items():
        t = _parse(r.get("first")) or _parse(r.get("t"))
        if t and t >= cutoff and r.get("h"):
            earlier[sid] = (r["h"], r.get("first") or r.get("t") or "")
    for x in _items(live):
        earlier.setdefault(x["id"], (x.get("headline") or "", x.get("time") or ""))
    idf = _idf([toks(h) for h, _ in earlier.values()])
    found = []
    for it in _items(out):
        sid = it["id"]
        if sid in live_ids:
            continue  # already running: updates to it are fine
        if it.get("followUp") and str(it.get("newAngle") or "").strip():
            continue  # a declared follow-up with a stated new development
        a = toks(it.get("headline"))
        if len(a) < 2:
            continue
        best = None
        for oid, (oh, ot) in earlier.items():
            if oid == sid:
                # the same id coming back after it dropped off the site: a re-run unless something changed
                if sid not in live_ids and _parse(ot) and _parse(ot) < now - timedelta(hours=36):
                    best = (2.0, oid, oh, ot, a)
                continue
            s, shared = score(a, toks(oh), idf)
            if s >= THRESHOLD and len(shared) >= MIN_SHARED and (best is None or s > best[0]):
                best = (s, oid, oh, ot, shared)
        if best:
            found.append((sid, it.get("headline") or "", best[1], best[2], best[3], sorted(best[4])))
    return found


if __name__ == "__main__":
    # audit: list likely repeats already in the archive (each record against older ones within LOOKBACK_DAYS)
    import json, os, sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    arch = json.load(open(os.path.join(root, "data", "archive.json"), encoding="utf-8"))
    recs = sorted([(sid, r) for sid, r in arch.items() if r.get("h") and _parse(r.get("first"))], key=lambda kv: kv[1]["first"])
    idf = _idf([toks(r["h"]) for _, r in recs])
    for i, (sid, r) in enumerate(recs):
        t = _parse(r["first"])
        a = toks(r["h"])
        for oid, o in recs[:i]:
            if t - _parse(o["first"]) > timedelta(days=LOOKBACK_DAYS):
                continue
            s, shared = score(a, toks(o["h"]), idf)
            if s >= THRESHOLD and len(shared) >= MIN_SHARED:
                print(f"{s:.2f} {r['first'][:10]} {sid}\n     {r['h']}\n  vs {o['first'][:10]} {oid}\n     {o['h']}\n     shared: {sorted(shared)}")
