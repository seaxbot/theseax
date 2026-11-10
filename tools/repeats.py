"""Front-page repetition check (owner's rule, Nov 2026): a fact should appear once across a story's headline,
summary and key points, because the front page shows all three. Used by tools/publish.py."""
import re
NUM_WORDS = r"one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|half|dozen|hundred|thousand|million|billion"
STOP = set("the a an and or of to in on at for by with from as is are was were be been has have had it its this that his her their our after over into up out new more than will would could not no but who which what when where".split())

def _norm(t):
    return re.sub(r"[^a-z0-9£%.]+", " ", str(t or "").lower().replace(",", "")).strip()

def figures(t):
    """Figure phrases: a number (digits or number words, with £ or %) plus the next word, e.g. 'two years', '11 months', '£1m'."""
    t = _norm(t)
    out = set()
    for m in re.finditer(rf"(£?\d+(?:\.\d+)?(?:m|bn|k|%)?|\b(?:{NUM_WORDS})\b)(?: (?:and|point) \S+)?(?: ([a-z]+))?", t):
        num, unit = m.group(1), m.group(2)
        if re.fullmatch(r"(19|20)\d\d", num):
            continue  # years are dates, not figures
        if unit and unit not in STOP:
            out.add(f"{num} {unit}")
    return out

def words(t):
    return [w for w in _norm(t).split() if len(w) > 2 and w not in STOP]

def repeats(it):
    """Front-page repetition in one story: the same figure in two of headline, summary and points, or a key point that
    only restates the headline or summary. Returns a list of plain-English problems."""
    h, s, pts = it.get("headline") or "", it.get("summary") or "", [p for p in it.get("points") or [] if isinstance(p, str)]
    probs = []
    parts = [("headline", h), ("summary", s)] + [(f"point {i + 1}", p) for i, p in enumerate(pts)]
    seen = {}
    for name, txt in parts:
        for f in figures(txt):
            seen.setdefault(f, []).append(name)
    for f, where in seen.items():
        if len(where) > 1:
            probs.append(f'"{f}" appears in the {" and the ".join(where)}')
    top = set(words(h)) | set(words(s))
    for i, p in enumerate(pts):
        w = words(p)
        if len(w) >= 2 and sum(x in top for x in w) / len(w) >= 0.75:
            probs.append(f'point {i + 1} only repeats the headline or summary: "{p}"')
    return probs

def _text(it):
    return (it.get("headline"), it.get("summary"), tuple(it.get("points") or []))

def check(out, live, sections):
    """(fresh, older): stories in the given sections with repeats. 'fresh' are new or rewritten since the live edition
    (publishing is refused until they are fixed); 'older' are unchanged stories still carrying repeats."""
    def walk(ed):
        for sec in sections:
            src = (ed.get("sport") or {}).get("stories") if sec == "sport" else ed.get(sec)
            for it in src or []:
                if isinstance(it, dict) and it.get("id"):
                    yield it
    before = {it["id"]: _text(it) for it in walk(live)}
    fresh, older = [], []
    for it in walk(out):
        probs = repeats(it)
        if probs:
            (older if before.get(it["id"]) == _text(it) else fresh).append((it["id"], probs))
    return fresh, older
