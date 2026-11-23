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
THRESHOLD_FULL = 0.45  # headline + summary comparison (owner, 23 Nov 2026)
MIN_SHARED_FULL = 5
STOP = set("""the a an and or of to in on at for by with from as is are was were be been has have had it its this that
his her their our after over into up out new more than will would could not no but who which what when where why how
all can may set get gets got make makes made back off down being them they she he him you your we us one two three
four five six seven eight nine ten first last year years day days week weeks month months today tonight now still just
says said say told tells calls call plan plans bid hit hits sees see seen amid after before during near""".split())


def _norm(t):
    return re.sub(r"[^a-z0-9£%]+", " ", str(t or "").lower().replace("'s", "").replace("’s", "")).strip()


def _stem(w):
    # plural and simple verb endings, so "taxis" matches "taxi" and "checks" matches "check" (owner, 23 Nov 2026:
    # a Harlow taxi checks story ran twice, a week apart, under two different headlines)
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
        return w[:-1]
    return w


def toks(t, numbers=False):
    out = set()
    for w in _norm(t).split():
        if w.isdigit():
            # distinctive figures ("62 taxis", "£3,672") help spot the same story; years and small counts do not
            if numbers and len(w) >= 2 and not re.fullmatch(r"(19|20)\d\d", w):
                out.add("#" + w)
            continue
        if len(w) > 2 and w not in STOP:
            out.add(_stem(w))
    return out


# source links: the same specific article or press release behind two stories is a strong sign of a repeat
_GENERIC = re.compile(r"(facebook\.com/profile|whatsapp\.com|theseax\.com|fonts\.(googleapis|gstatic)\.com|"
                      r"wikimedia\.org|wikipedia\.org|creativecommons\.org|openverse|flickr\.com|unsplash\.com|pexels\.com|"
                      r"members\.parliament\.uk/member/\d+/portrait|football-scores-fixtures|/fixtures|/results|/table|"
                      r"metoffice\.gov\.uk/(forecast|weather)|news-search|/divisions/|/our-teams/|geograph\.org\.uk/profile|"
                      r"petition\.parliament\.uk/?$|/news/?$|/latest/?$|/press-releases/?$|/media/?$)")


def norm_url(u):
    u = re.sub(r"^https?://(www\.)?", "", str(u or "").strip().lower())
    return re.sub(r"[?#].*$", "", u).rstrip("/")


def specific_url(u):
    n = norm_url(u)
    if not n or _GENERIC.search(n) or _GENERIC.search(str(u).lower()):
        return False
    path = n.split("/", 1)[1] if "/" in n else ""
    return len([p for p in path.split("/") if p]) >= 2 or len(path) >= 25


def urls_of(it):
    us = [it.get("url")] + [a.get("url") for a in (it.get("also") or []) if isinstance(a, dict)]
    return {norm_url(u) for u in us if u and specific_url(u)}


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
    earlier, extra = {}, {}
    for sid, r in (archive or {}).items():
        t = _parse(r.get("first")) or _parse(r.get("t"))
        if t and t >= cutoff and r.get("h"):
            earlier[sid] = (r["h"], r.get("first") or r.get("t") or "")
            extra[sid] = (r.get("s") or "", set(r.get("src") or []))
    for x in _items(live):
        earlier.setdefault(x["id"], (x.get("headline") or "", x.get("time") or ""))
        extra.setdefault(x["id"], (x.get("summary") or "", urls_of(x)))
    # a link shared by three or more earlier stories is a hub (a fixtures page, a council's meeting papers), not one story
    seen = {}
    for _, us in extra.values():
        for u in us:
            seen[u] = seen.get(u, 0) + 1
    extra = {k: (sm, {u for u in us if seen.get(u, 0) < 3}) for k, (sm, us) in extra.items()}
    idf = _idf([toks(h) for h, _ in earlier.values()])
    full = {oid: toks(oh + " " + extra.get(oid, ("", set()))[0], numbers=True) for oid, (oh, _) in earlier.items()}
    idf2 = _idf(list(full.values()))
    found = []
    for it in _items(out):
        sid = it["id"]
        if sid.startswith("s-") or str(it.get("tag") or "") in ("Football", "Racing", "Cricket", "Ice Hockey", "Rugby"):
            continue  # match reports and round-ups belong to the sport desk and share fixture pages by design
        if sid in live_ids:
            continue  # already running: updates to it are fine
        if it.get("followUp") and str(it.get("newAngle") or "").strip():
            continue  # a declared follow-up with a stated new development
        a = toks(it.get("headline"))
        if len(a) < 2:
            continue
        b = toks((it.get("headline") or "") + " " + (it.get("summary") or ""), numbers=True)
        mine = urls_of(it)
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
                continue
            # 2) the same specific source article or release (url or "also" links)
            same = mine & extra.get(oid, ("", set()))[1]
            if same and (best is None or 1.5 > best[0]):
                best = (1.5, oid, oh, ot, {"same source: " + sorted(same)[0]})
                continue
            # 3) headline and summary together: catches the same story told under a different headline
            s2, shared2 = score(b, full.get(oid, set()), idf2)
            if s2 >= THRESHOLD_FULL and len(shared2) >= MIN_SHARED_FULL and s >= 0.25 and (best is None or s2 > best[0]):
                best = (s2, oid, oh, ot, shared2)
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
