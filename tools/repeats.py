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
    return probs + body_problems(it)

# Story page copy (owner's rule, 12 Nov 2026: "write like a world class journalist; no story should sound written by AI").
# The page reads headline, standfirst (summary), then the body, so the first paragraph must move the story on from the
# standfirst, and each paragraph must add something new rather than restate the one before.
AI_TELLS = re.compile(r"\b(amid|comes as|in a move (that|which)|underscor\w*|highlights? the|it remains to be seen|testament to|"
                      r"significant step|pivotal|game[- ]changer|bustling|nestled|vibrant|delve\w*|furthermore|moreover|additionally|"
                      r"in conclusion|navigat\w+ (the )?(challenges|complexities)|ever[- ]evolving|tapestry|seamless\w*|"
                      r"plays? an? (crucial|vital|key|pivotal) role|serves? as a (reminder|testament)|stark reminder|"
                      r"sent shockwaves|in the heart of|a raft of|look(s|ing)? to bolster)\b", re.I)
STAMP = re.compile(r"\breported on (monday|tuesday|wednesday|thursday|friday|saturday|sunday) \d{1,2} \w+ \d{4}\b", re.I)

def _overlap(a, b):
    A, B = set(words(a)), set(words(b))
    return len(A & B) / max(1, min(len(A), len(B))) if A and B else 0.0

def body_problems(it):
    body = [p for p in it.get("body") or [] if isinstance(p, str) and p.strip()]
    probs = []
    if body and _overlap(it.get("summary") or "", body[0]) >= 0.5:
        probs.append("paragraph 1 repeats the summary: open it with what the summary leaves out")
    for i in range(len(body) - 1):
        if _overlap(body[i], body[i + 1]) >= 0.5:
            probs.append(f"paragraph {i + 2} repeats paragraph {i + 1}")
    for name, txt in [("summary", it.get("summary") or "")] + [(f"paragraph {i + 1}", p) for i, p in enumerate(body)]:
        m = AI_TELLS.search(txt)
        if m:
            probs.append(f'{name} uses stock phrasing "{m.group(0)}": say it plainly')
    if len(STAMP.findall(" ".join(body))) > 1:
        probs.append('more than one "reported on <day> <date> <year>" stamp in the body: date it once, attribute plainly after that')
    return probs

def _text(it):
    return (it.get("headline"), it.get("summary"), tuple(it.get("points") or []), tuple(it.get("body") or []))

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
