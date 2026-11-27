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
    return probs + headline_problems(h) + headline_parts(h, s, pts) + body_problems(it)

# Headlines (owner's rule, 18 Nov 2026; ops/newsroom.md 3a vii): short, front-loaded, plain.
HEADLINE_MAX = 80
HEAD_LABEL = re.compile(r"^\s*(update[sd]?|breaking( news)?|watch|live|exclusive)\b\s*[:\-|]?", re.I)
HEAD_SPEAK = re.compile(r"\b(slam(s|med)?|blast(s|ed)?|probe[sd]?|axe[sd]?|shock|fury|horror)\b", re.I)

def headline_problems(h):
    h = str(h or "").strip()
    probs = []
    if len(h) > HEADLINE_MAX:
        probs.append(f"headline is {len(h)} characters (limit {HEADLINE_MAX}): cut it to one idea, place first, and move the rest to the summary")
    m = HEAD_LABEL.match(h)
    if m:
        probs.append(f'headline starts with the label "{m.group(1)}": lead with the news instead (the site has its own badges)')
    if "—" in h:
        probs.append("headline has an em dash")
    m = HEAD_SPEAK.search(h)
    if m:
        probs.append(f'headline uses tabloid headline-speak "{m.group(0)}": use a plain, exact verb')
    return probs

# Too many parts (owner's rule, 27 Nov 2026: "don't complicate", after "Essex wins £1.1m to tackle stalkers and help
# their victims to 2029" carried three ideas and a date the summary already gave). Length is fine up to 80; parts are not.
HEAD_JOIN = re.compile(r"\b(and|as|after|while|with|amid|plus|but|despite|following)\b", re.I)
JOIN_NAMES = re.compile(r"\b(army and navy|essex and (suffolk|herts|hertfordshire)|bed and breakfast|fish and chips|"
                        r"police, fire and crime|town and country)\b", re.I)
YEAR = re.compile(r"\b(19|20)\d\d\b")

def headline_parts(h, s="", pts=()):
    h = str(h or "")
    probs = []
    joins = HEAD_JOIN.findall(JOIN_NAMES.sub(" ", h))
    if len(joins) >= 2:
        probs.append(f'headline has too many parts (joined by "{joins[0]}" and "{joins[1]}"): keep the one main idea and move the rest to the summary')
    rest = " ".join([str(s or "")] + [str(p) for p in pts])
    for y in sorted({m.group(0) for m in YEAR.finditer(h)}):
        if y in rest:
            probs.append(f'headline repeats the year {y}, which the summary or key points already give: take it out of the headline')
    return probs

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
    # subheadings ("## ...", owner's long-story format, 20 Nov 2026) are not paragraphs
    body = [p for p in it.get("body") or [] if isinstance(p, str) and p.strip() and not p.startswith("## ")]
    probs = []
    # relaxed 23 Nov 2026 (owner: the old 0.5 test forced stiff, dodging openings): only a near copy of the summary fails
    if body and _overlap(it.get("summary") or "", body[0]) >= 0.8:
        probs.append("paragraph 1 is a near copy of the summary: tell it in fuller, natural words or open with the next detail")
    for i in range(len(body) - 1):
        if _overlap(body[i], body[i + 1]) >= 0.5:
            probs.append(f"paragraph {i + 2} repeats paragraph {i + 1}")
    for name, txt in [("summary", it.get("summary") or "")] + [(f"paragraph {i + 1}", p) for i, p in enumerate(body)]:
        m = AI_TELLS.search(txt)
        if m:
            probs.append(f'{name} uses stock phrasing "{m.group(0)}": say it plainly')
    if len(STAMP.findall(" ".join(body))) > 1:
        probs.append('more than one "reported on <day> <date> <year>" stamp in the body: date it once, attribute plainly after that')
    return probs + style_problems(it, body)

# House style (owner, 23 Nov 2026: "the writing sometimes feels a bit mechanical and not human ... style is so important";
# ops/style.md). Checks the habits that made copy read like a compiled report.
SENT_SPLIT = re.compile(r"(?<=[.!?])[\"')’”]*\s+(?=[A-Z\"'‘“£0-9])")
TAIL_CREDIT = re.compile(r",\s+(?:the\s+)?[A-Z][\w&'’.\- ]{1,45}?\s+(?:reports|reported|says|said)[.!]?[\"'’”)]*$")
FULL_DATE = re.compile(r"\b(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday) \d{1,2} (?:January|February|March|April|May|June|July|August|September|October|November|December)\b")
LONG_SENTENCE = 35
MIN_WORDS = 150

def _sentences(p):
    p = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", p)  # markdown links count as their words
    return [s for s in SENT_SPLIT.split(p.strip()) if s.strip()]

def style_problems(it, body=None):
    if body is None:
        body = [p for p in it.get("body") or [] if isinstance(p, str) and p.strip() and not p.startswith("## ")]
    probs = []
    sents = [s for p in body for s in _sentences(p)]
    long = [s for s in sents if len(s.split()) > LONG_SENTENCE]
    if long:
        probs.append(f"{len(long)} sentence(s) over {LONG_SENTENCE} words, e.g. \"{' '.join(long[0].split()[:12])}...\": split them, one idea per sentence")
    tails = [s for s in sents if TAIL_CREDIT.search(s.strip())]
    if len(tails) > 2:
        probs.append(f"{len(tails)} sentences end with a tagged-on credit (\", X reports\" / \", X said\"): credit each source once, naturally, and let the rest run free")
    dates = FULL_DATE.findall(" ".join(body))
    if len(dates) > 3:
        probs.append(f"{len(dates)} full weekday-and-date stamps in the body: give the key date in full once, then use plain words (\"that evening\", \"on Wednesday\")")
    if len(body) >= 4 and sum(p.split()[0] == "The" for p in body if p.split()) * 2 > len(body):
        probs.append("more than half the paragraphs start with \"The\": vary how paragraphs open")
    sid = str(it.get("id") or "")
    words_n = sum(len(p.split()) for p in body)
    exempt = (it.get("linkOnly") or it.get("summaryOnly") or sid.startswith(("o-", "c-", "ct-", "s-", "sp-"))
              or it.get("kind") or it.get("desk") in ("inquest", "sport") or (str(it.get("researchNote") or "").strip() and not it.get("researched")))
    if not exempt and words_n < MIN_WORDS:
        probs.append(f"only {words_n} words: research it and add context, background, who is affected and what happens next from more sources (ops/style.md), at least {MIN_WORDS} words")
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
