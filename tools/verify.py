#!/usr/bin/env python3
"""TRIPLE CHECK for The Seax's own reporting (owner's rule, 20 Nov 2026: "Make sure triple checks are done before
publishing on The Seax original reporting!").

Why: the first September 2026 recorded crime story went out with a misleading headline, a wrong place name, a wrong
category name and figures that were slightly off, because nobody checked the copy against the raw data or recounted
it another way. Original reporting is ours alone: nobody else's story backs it up, so every figure must be proved.

Which stories: every new or rewritten item carrying "original" (data desk, FOI, weekly pieces, primary documents) and
every new or rewritten Council Watch item. tools/publish.py refuses to publish them (exit 7, "UNVERIFIED") unless they
carry a "verified" stamp made by this tool for the exact final copy. Change one word afterwards and the stamp no longer
matches, so the checks must be done again on the final words.

The three checks (each must be done for real, then described in one or two sentences with what was compared):
  1. FIGURES: recompute every number in the headline, summary, body and points with code from the RAW source file
     (for the data desk, /tmp/data-desk/data.json or state.json, never the rounded digest line), including every
     percentage, rounding, ranking ("biggest", "most", "sharpest") and count ("rose in 45 of 56").
  2. INDEPENDENT: confirm the key figures a second, independent way: the primary official page or document itself, a
     second dataset or method, or a recount from the source. Check every name, place and category label is written
     exactly as the source writes it (a police neighbourhood called "Basildon" is not "Basildon town centre").
  3. READ-BACK: read the final headline, summary, body and points as a reader would: the headline is exactly true and
     leads on the strongest accurate fact; nothing overstates the data; "about" is not used when exact figures exist;
     caveats a fair reader needs are in the copy; no fact repeats; plain English.
If any check fails, fix the copy and do all three again. If a check cannot be done, do not publish the story.

Usage (in the checkout):
  python3 tools/verify.py stamp FILE ID --figures "..." --independent "..." --readback "..."
FILE is the file you will publish (edition, items or Council Watch file). Prints VERIFIED <id> <sig>.
"""
import hashlib, json, sys
from datetime import datetime, timezone, timedelta

SECTIONS = ("stories", "community", "official", "courts", "councilwatch", "items")
CHECKS = ("figures", "independent", "readback")
MAX_AGE_HOURS = 6


def sig(item):
    """Fingerprint of the words readers see. Any change to them needs a fresh triple check."""
    norm = lambda s: " ".join(str(s or "").split())
    words = [norm(item.get("headline")), norm(item.get("summary")),
             [norm(p) for p in (item.get("body") or []) if norm(p)], [norm(p) for p in (item.get("points") or []) if norm(p)]]
    return hashlib.sha256(json.dumps(words, ensure_ascii=False).encode()).hexdigest()[:16]


def needs(item, councilwatch=False):
    return isinstance(item, dict) and bool(councilwatch or item.get("original"))


def _items(obj):
    if isinstance(obj, list):
        yield from (x for x in obj if isinstance(x, dict))
        return
    if not isinstance(obj, dict):
        return
    for k in SECTIONS:
        for x in obj.get(k) or []:
            if isinstance(x, dict):
                yield x


def problem(item, live_item=None, councilwatch=False, now=None):
    """None when the item may be published; otherwise the reason it may not."""
    if not needs(item, councilwatch):
        return None
    s = sig(item)
    if live_item is not None and sig(live_item) == s:
        return None                       # unchanged since it was published
    v = item.get("verified") if isinstance(item.get("verified"), dict) else {}
    if not v:
        return "no triple check: do the three checks, then run tools/verify.py stamp"
    if v.get("sig") != s:
        return "the copy changed after the triple check: check the final words again and restamp"
    checks = v.get("checks") if isinstance(v.get("checks"), dict) else {}
    short = [c for c in CHECKS if len(str(checks.get(c) or "").strip()) < 25]
    if short:
        return "triple check incomplete: " + ", ".join(short)
    try:
        at = datetime.strptime(v.get("at", ""), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return "triple check has no valid time"
    if (now or datetime.now(timezone.utc)) - at > timedelta(hours=MAX_AGE_HOURS):
        return f"triple check is more than {MAX_AGE_HOURS} hours old: check again"
    return None


def gate(out, live, councilwatch_only=False):
    """[(id, reason)] for every new or rewritten original or Council Watch item in out that is not verified."""
    live_ix = {}
    for x in _items(live):
        live_ix.setdefault(x.get("id"), x)
    bad = []
    lists = [("councilwatch", out.get("councilwatch") or [])] if councilwatch_only else \
            [(k, out.get(k) or []) for k in ("stories", "community", "official", "courts", "councilwatch")]
    for sec, xs in lists:
        for x in xs:
            if not isinstance(x, dict):
                continue
            p = problem(x, live_ix.get(x.get("id")), councilwatch=(sec == "councilwatch"))
            if p:
                bad.append((x.get("id"), p))
    return bad


def stamp(path, sid, checks):
    with open(path, encoding="utf-8") as f:
        obj = json.load(f)
    hit = [x for x in _items(obj) if x.get("id") == sid]
    if not hit:
        sys.exit(f"no item with id {sid} in {path}")
    short = [c for c in CHECKS if len(str(checks.get(c) or "").strip()) < 25]
    if short:
        sys.exit("describe each check in a sentence or two (what you compared, against what): missing " + ", ".join(short))
    at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for x in hit:
        x["verified"] = {"at": at, "sig": sig(x), "checks": {c: str(checks[c]).strip() for c in CHECKS}}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    print("VERIFIED", sid, hit[0]["verified"]["sig"])


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) < 3 or a[0] != "stamp":
        sys.exit(__doc__)
    opts = {}
    for c in CHECKS:
        flag = "--" + c
        if flag in a and a.index(flag) + 1 < len(a):
            opts[c] = a[a.index(flag) + 1]
    stamp(a[1], a[2], opts)
