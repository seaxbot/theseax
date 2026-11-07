#!/usr/bin/env python3
"""Essex Council Watch collector.

Runs on GitHub Actions once or twice a day. For every Essex council it can reach politely, it:
  1. lists meetings from 21 days ago to 28 days ahead,
  2. reads each meeting's agenda page (items, decisions and minutes text, document links),
  3. scores every agenda item for public interest with plain keyword rules (no AI here),
  4. for the strongest items, downloads the report PDF and keeps short page-referenced excerpts.

Outputs (written to OUT, default ./cw-out):
  inbox.json     meetings that are new or changed, with scored items and excerpts, for the Council Watch desk
  calendar.json  upcoming meetings and their headline items for the website (no AI needed)
  status.json    per-council health: ok, blocked by the site, robots refused, unreachable
  state.json     fingerprints of what has been seen, so only changes are reported next time

Rules it follows: identifies itself honestly, obeys robots.txt for its own user agent, skips any site
that signals "ai-input=no", waits between requests, and caps requests per council.
Standard library only, plus the pdftotext command (poppler-utils) for PDFs.
"""
import hashlib, html, json, os, re, ssl, subprocess, sys, tempfile, time, urllib.error, urllib.request, urllib.robotparser
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse, quote

UA = "TheSeaxCouncilWatch/1.0 (+https://theseax.com/about/; theseaxessex@gmail.com)"
HEAD = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8", "Accept-Language": "en-GB,en;q=0.9"}
NOW = datetime.now(timezone.utc)
TODAY = NOW.date()
BACK, AHEAD = 21, 28
MAX_REQ = 70          # per council per run
MAX_PDF = 14          # report PDFs downloaded per run, across all councils
PAUSE = 1.2           # seconds between requests to the same host

COUNCILS = [
    # id, name, area key used on the site, system, base url
    ("thurrock", "Thurrock Council", "south", "mg", "https://democracy.thurrock.gov.uk"),
    ("southend", "Southend-on-Sea City Council", "southend", "mg", "https://democracy.southend.gov.uk"),
    ("epping", "Epping Forest District Council", "epping", "mg", "https://rds.eppingforestdc.gov.uk"),
    ("maldon", "Maldon District Council", "maldon", "mg", "https://democracy.maldon.gov.uk"),
    ("tendring", "Tendring District Council", "tendring", "mg", "https://tdcdemocracy.tendringdc.gov.uk"),
    ("harlow", "Harlow Council", "epping", "mg", "https://moderngov.harlow.gov.uk"),
    ("basildon", "Basildon Council", "south", "mg", "https://www.basildonmeetings.info"),
    ("brentwood", "Brentwood Borough Council", "brentwood", "mg", "https://brentwood.moderngov.co.uk"),
    ("uttlesford", "Uttlesford District Council", "uttlesford", "mg", "https://uttlesford.moderngov.co.uk"),
    ("essex", "Essex County Council", "all", "cmis", "https://cmis.essex.gov.uk/essexcmis5"),
    ("colchester", "Colchester City Council", "colchester", "cmis", "https://colchester.cmis.uk.com/colchester"),
    ("rochford", "Rochford District Council", "south", "cmis", "https://rochford.cmis.uk.com/rochford"),
    ("chelmsford", "Chelmsford City Council", "chelmsford", "chelmsford", "https://www.chelmsford.gov.uk"),
    ("braintree", "Braintree District Council", "braintree", "none", "https://www.braintree.gov.uk"),
    ("castlepoint", "Castle Point Borough Council", "south", "none", "https://www.castlepoint.gov.uk"),
]

# ---------- public-interest scoring (keywords, no AI) ----------
STRONG = [
    r"council tax", r"budget", r"overspend", r"deficit", r"section 114", r"bankrupt", r"commissioner", r"savings", r"\bcuts?\b",
    r"clos(e|ure|ing)", r"demoli", r"redevelop", r"regenerat", r"sell|sale of|dispos", r"acqui(re|sition)", r"purchase of",
    r"contract award|award of contract|procure", r"local plan", r"homes|housing|dwellings", r"planning application|outline planning",
    r"appeal", r"green belt", r"consultation", r"petition", r"motion", r"censure|code of conduct|standards complaint",
    r"parking charge|car park|fees and charges", r"leisure centre|swimming|library|libraries|museum|theatre|toilets",
    r"school|send\b|special educational", r"social care|care home", r"homeless|temporary accommodation", r"bin|waste|recycling",
    r"bus|rail|road|highway|pothole|cycle", r"flood|sea wall|coastal", r"climate", r"crime|antisocial|cctv", r"licen[cs]e",
    r"reorganisation|unitary|devolution|mayor", r"investment|loan|borrowing|debt", r"redundan|restructur|staff",
    r"fire|ambulance|police", r"health|nhs|hospital|gp\b", r"pier|seafront|beach|airport|port|freeport",
]
WEAK = [r"apologies for absence", r"declarations? of interest", r"minutes of (the )?(last|previous)", r"^minutes$", r"work (programme|plan)",
        r"urgent business", r"exclusion of (the )?press", r"chair'?s? announcements?", r"date of (the )?next meeting", r"webcast",
        r"questions? from (the )?public", r"public questions", r"members.? questions", r"questions? (from|to|by) (councillors|members)",
        r"minutes and decisions called in", r"reports? to council", r"\bitems?$", r"^\d{1,2} \w+ 20\d\d$", r"any other business",
        r"substitut", r"announcements", r"terms of reference", r"appointment of (vice|chair)", r"call.?in", r"forward plan", r"exclusion"]
MONEY = re.compile(r"£\s?\d[\d,\.]*\s?(m|bn|million|billion|k)?\b", re.I)

def score_item(title, text, committee, has_report=False):
    t = f"{title} {text}".lower()
    s = 0
    for p in STRONG:
        if re.search(p, t):
            s += 2
    for p in WEAK:
        if re.search(p, title.lower()):
            s -= 6
    s += min(len(MONEY.findall(t)), 4) * 2
    if re.search(r"resolved|agreed|approved|refused|rejected|deferred|decision", t):
        s += 3
    if re.search(r"cabinet|full council|^council|planning|development|scrutiny|health and wellbeing|police, fire and crime", committee.lower()):
        s += 2
    if re.search(r"exempt|confidential|private", t) and not re.search(r"public", t):
        s -= 2
    if has_report:
        s += 3
    return s

# ---------- polite fetching ----------
class Fetcher:
    def __init__(self):
        self.robots, self.signals, self.last, self.count = {}, {}, {}, {}
        self.ctx = ssl.create_default_context()

    def _robots(self, host):
        if host in self.robots:
            return self.robots[host]
        rp = urllib.robotparser.RobotFileParser()
        txt, sig = "", {}
        try:
            req = urllib.request.Request(f"https://{host}/robots.txt", headers=HEAD)
            with urllib.request.urlopen(req, timeout=20, context=self.ctx) as r:
                txt = r.read(200000).decode("utf-8", "replace")
        except Exception:
            txt = ""
        rp.parse(txt.splitlines())
        for m in re.finditer(r"(?im)^content-signal:\s*(.+)$", txt):
            for part in m.group(1).split(","):
                if "=" in part:
                    k, v = part.split("=", 1)
                    sig[k.strip().lower()] = v.strip().lower()
        self.robots[host], self.signals[host] = rp, sig
        return rp

    def allowed(self, url):
        host = urlparse(url).netloc
        rp = self._robots(host)
        if self.signals.get(host, {}).get("ai-input") == "no":
            return False, "site signals ai-input=no"
        if not rp.can_fetch(UA, url):
            return False, "robots.txt disallows"
        return True, ""

    def get(self, url, council, binary=False, limit=3_000_000):
        if self.count.get(council, 0) >= MAX_REQ:
            return 0, "", "request cap reached"
        ok, why = self.allowed(url)
        if not ok:
            return -1, "", why
        host = urlparse(url).netloc
        wait = PAUSE - (time.time() - self.last.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        self.last[host] = time.time()
        self.count[council] = self.count.get(council, 0) + 1
        safe = quote(url, safe=":/?&=%#+,;@")
        try:
            with urllib.request.urlopen(urllib.request.Request(safe, headers=HEAD), timeout=40, context=self.ctx) as r:
                data = r.read(limit)
                return r.status, (data if binary else data.decode("utf-8", "replace")), r.geturl()
        except urllib.error.HTTPError as e:
            return e.code, b"" if binary else "", str(e)
        except Exception as e:
            return 0, b"" if binary else "", repr(e)[:200]

F = Fetcher()

def clean(s):
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h\d>|</tr>", "\n", s)
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    return re.sub(r"\n\s*\n+", "\n", s).strip()

def date_from(text):
    m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|July|August|September|October|November|December),?\s+(20\d\d)", text)
    if m:
        try:
            return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%d %B %Y").date()
        except ValueError:
            return None
    m = re.search(r"(\d{2})/(\d{2})/(20\d\d)", text)
    if m:
        try:
            return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1))).date()
        except ValueError:
            return None
    return None

def months_in_window():
    d0, d1 = TODAY - timedelta(days=BACK), TODAY + timedelta(days=AHEAD)
    out, d = [], d0.replace(day=1)
    while d <= d1:
        out.append((d.month, d.year))
        d = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    return out

def in_window(d):
    return d and TODAY - timedelta(days=BACK) <= d <= TODAY + timedelta(days=AHEAD)

# ---------- ModernGov ----------
def mg_meetings(cid, base):
    meets, err = {}, None
    for m, y in months_in_window():
        st, body, info = F.get(f"{base}/mgCalendarMonthView.aspx?M={m}&Y={y}&GL=1", cid)
        if st != 200:
            err = f"calendar {st} {info}"
            continue
        for a in re.finditer(r'<a[^>]+href="(ieListDocuments\.aspx\?CId=(\d+)&amp;MId=(\d+))"[^>]*title="([^"]*)"', body):
            title = html.unescape(a.group(4))
            mm = re.match(r"Meeting of (.*), (\d{2})/(\d{2})/(\d{4})\s*(.*)", title.strip())
            if not mm:
                continue
            d = datetime(int(mm.group(4)), int(mm.group(3)), int(mm.group(2))).date()
            if not in_window(d):
                continue
            mid = a.group(3)
            meets[mid] = {"mid": mid, "committee": mm.group(1).strip(), "date": d.isoformat(), "time": mm.group(5).strip(),
                          "url": f"{base}/ieListDocuments.aspx?CId={a.group(2)}&MId={mid}"}
    return list(meets.values()), (err if not meets else None)

def mg_meeting(cid, base, meet):
    st, body, info = F.get(meet["url"], cid)
    if st != 200:
        return None, f"meeting {st}"
    head = clean(body[body.find("mgSubTitleTxt"):][:600]) if "mgSubTitleTxt" in body else ""
    cancelled = bool(re.search(r"(?i)\bcancelled\b|\bpostponed\b", head))
    packs = []
    for a in re.finditer(r'<a[^>]+href="(documents/g\d+/[^"]+)"[^>]*>(.*?)</a>', body, re.S):
        packs.append({"title": clean(a.group(2)).split(" PDF")[0].strip(), "url": urljoin(meet["url"], html.unescape(a.group(1)))})
    items = []
    tbl = body[body.find('id="mgItemTable"'):] if 'id="mgItemTable"' in body else ""
    rows = re.split(r'<td\s+class="mgItemNumberCell"', tbl)[1:]
    for r in rows:
        num = clean(r[:300]).lstrip("> ").split("\n")[0].strip().rstrip(".")
        tm = re.search(r'class="mgAiTitleTxt"\s*>(.*?)</p>', r[r.find("</td>"):], re.S)
        title = clean(tm.group(1)).split(" PDF ")[0].strip() if tm else ""
        docs = []
        for a in re.finditer(r'<a[^>]+href="(documents/s\d+/[^"]+)"[^>]*>(.*?)</a>', r, re.S):
            docs.append({"title": clean(a.group(2)).split(" PDF")[0].strip(), "url": urljoin(meet["url"], html.unescape(a.group(1)))})
        text = "\n".join(l.strip() for l in clean(r[r.find("</td>"):]).split("\n"))
        text = re.sub(r"(?m)^(Webcast for [\d\.a-z]+|Additional documents:|View the background to item [\d\.a-z]+\.?|View the reasons why .*|.* PDF \d+ KB|, item [\d\.a-z]+\.?)$", "", text)
        text = re.sub(r"\n+", "\n", text).strip()
        if title and text.startswith(title):
            text = text[len(title):].strip()
        decided = bool(re.search(r"(?i)\b(decision|minutes):", text))
        items.append({"num": num, "title": title, "text": text[:6000], "docs": docs[:8], "decided": decided})
    return {"packs": packs[:6], "items": items, "cancelled": cancelled}, None

# ---------- CMIS ----------
def cmis_meetings(cid, base):
    """CMIS calendars hold the month's meetings as scheduler data. Committee pages give each meeting's link."""
    meets, err = {}, None
    st, body, info = F.get(f"{base}/Committees.aspx", cid)
    if st != 200:
        return [], f"committees {st} {info}"
    comm = []
    for a in re.finditer(r'<a[^>]+href="([^"]*ViewCMIS_CommitteeDetails[^"]*)"[^>]*>(.*?)</a>', body, re.S):
        name = clean(a.group(2))
        if name and not re.search(r"(?i)private|appointments|employment|co-parenting|sub-committee \(|complaints", name):
            comm.append((name, urljoin(base + "/", html.unescape(a.group(1)))))
    seen = set()
    key = re.compile(r"(?i)cabinet|^council|full council|planning|development and regulation|scrutiny|health and wellbeing|police, fire and crime|local plan|licensing committee$|governance|audit|parking partnership|climate")
    comm = [c for c in comm if key.search(c[0]) and not (c[1] in seen or seen.add(c[1]))][:14]
    for name, url in comm:
        st, b2, info = F.get(url, cid)
        if st != 200:
            err = f"committee page {st}"
            continue
        for a in re.finditer(r'<a[^>]+href="([^"]*ViewMeetingPublic[^"]*Meeting/(\d+)[^"]*)"[^>]*>(.*?)</a>', b2, re.S):
            label = clean(a.group(3))
            d = date_from(label)
            if not in_window(d):
                continue
            mid = a.group(2)
            meets[mid] = {"mid": mid, "committee": name, "date": d.isoformat(), "time": "", "url": urljoin(url, html.unescape(a.group(1)))}
    return list(meets.values()), (err if not meets else None)

def cmis_meeting(cid, base, meet):
    st, body, info = F.get(meet["url"], cid)
    if st != 200:
        return None, f"meeting {st}"
    txt = clean(body)
    cancelled = bool(re.search(r"(?i)meeting (has been )?cancelled|status:\s*cancelled", txt[:3000]))
    docs = []
    for a in re.finditer(r'<a[^>]+href="([^"]*Document\.ashx\?[^"]+)"[^>]*>(.*?)</a>', body, re.S):
        t = clean(a.group(2))
        if t:
            docs.append({"title": t, "url": urljoin(meet["url"], html.unescape(a.group(1)))})
    items, cur = [], None
    # CMIS agenda items are numbered headings followed by their documents
    for line in txt.split("\n"):
        m = re.match(r"^(\d{1,2}[a-z]?)\s+(.{4,200})$", line.strip())
        if m and not re.search(r"(?i)^\d+\s+(kb|mb)", line):
            cur = {"num": m.group(1), "title": m.group(2).strip(), "text": "", "docs": [], "decided": False}
            items.append(cur)
        elif cur and len(cur["text"]) < 4000:
            cur["text"] += line + "\n"
    for it in items:
        it["docs"] = [d for d in docs if d["title"][:30].lower() in it["text"].lower() or it["title"][:25].lower() in d["title"].lower()][:6]
        it["decided"] = bool(re.search(r"(?i)resolved|decision", it["text"]))
    packs = [d for d in docs if re.search(r"(?i)agenda|minutes|pack", d["title"])][:6]
    return {"packs": packs, "items": items[:40], "cancelled": cancelled}, None

# ---------- Chelmsford (own website) ----------
def chelmsford_meetings(cid, base):
    st, body, info = F.get(f"{base}/committee-meetings/", cid)
    if st != 200:
        return [], f"list {st} {info}"
    meets = {}
    for a in re.finditer(r'<a href="(https://www\.chelmsford\.gov\.uk/committee-meetings/([a-z0-9\-]+)/?)"[^>]*>(.*?)</a>', body, re.S):
        url, slug, inner = a.group(1), a.group(2), a.group(3)
        block = clean(inner)
        d = date_from(block)
        if not d:
            mm = re.search(r"(january|february|march|april|may|june|july|august|september|october|november|december)-(20\d\d)", slug)
            if mm:
                d = datetime.strptime(f"1 {mm.group(1)} {mm.group(2)}", "%d %B %Y").date()
        if not in_window(d):
            continue
        name = re.sub(r"-(\d{1,2}-)?(january|february|march|april|may|june|july|august|september|october|november|december)-20\d\d$", "", slug).replace("-", " ").capitalize()
        meets[slug] = {"mid": slug, "committee": name, "date": d.isoformat(), "time": "", "url": url if url.endswith("/") else url + "/"}
    return list(meets.values()), None

def chelmsford_meeting(cid, base, meet):
    st, body, info = F.get(meet["url"], cid)
    if st != 200:
        return None, f"meeting {st}"
    main = body[body.find("<h1"):]
    main = main[: main.find("Is there something wrong") if "Is there something wrong" in main else 60000]
    d = date_from(clean(main[:3000]))
    if d:
        meet["date"] = d.isoformat()
    links = [{"title": clean(a.group(2)), "url": a.group(1)} for a in re.finditer(r'<a[^>]+href="(https://www\.chelmsford\.gov\.uk/media/[^"]+\.pdf)"[^>]*>(.*?)</a>', main, re.S)]
    txt = clean(main)
    items, cur = [], None
    for line in txt.split("\n"):
        m = re.match(r"^(\d{1,2}(?:\.\d{1,2})?)\.?\s+(.{3,200})$", line.strip())
        if m and not re.match(r"^\d{1,2}\s+(January|February|March|April|May|June|July|August|September|October|November|December)", line.strip()):
            cur = {"num": m.group(1), "title": m.group(2).strip(), "text": "", "docs": [], "decided": False}
            items.append(cur)
        elif cur and len(cur["text"]) < 3000:
            cur["text"] += line + "\n"
    for it in items:
        it["docs"] = [l for l in links if it["title"][:25].lower() in l["title"].lower() or l["title"].lower().startswith(it["num"] + " ")][:4]
    packs = [l for l in links if re.search(r"(?i)agenda pack|minutes|decision", l["title"])][:4]
    return {"packs": packs, "items": items, "cancelled": bool(re.search(r"(?i)cancelled", txt[:400]))}, None

ADAPT = {"mg": (mg_meetings, mg_meeting), "cmis": (cmis_meetings, cmis_meeting), "chelmsford": (chelmsford_meetings, chelmsford_meeting)}

# ---------- PDF excerpts ----------
def pdf_excerpt(cid, url):
    st, data, info = F.get(url, cid, binary=True, limit=25_000_000)
    if st != 200 or not data or not data[:5].startswith(b"%PDF"):
        return None
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(data); f.flush()
        try:
            out = subprocess.run(["pdftotext", "-layout", "-l", "40", f.name, "-"], capture_output=True, timeout=90).stdout.decode("utf-8", "replace")
        except Exception:
            return None
    pages = out.split("\f")
    keep, total = [], 0
    for i, p in enumerate(pages, 1):
        p = re.sub(r"[ \t]+", " ", p).strip()
        if not p:
            continue
        hit = i <= 2 or re.search(r"(?i)recommendation|resolved|decision|financial implications|summary|purpose of (the )?report|background|£", p)
        if hit:
            seg = p[:2200]
            keep.append(f"[page {i}]\n{seg}")
            total += len(seg)
        if total > 9000:
            break
    return {"pages": len(pages), "excerpt": "\n\n".join(keep)}

def fp(obj):
    return hashlib.sha1(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:16]

def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "cw-out"
    os.makedirs(out, exist_ok=True)
    sp = os.path.join(out, "state.json")
    state = json.load(open(sp)) if os.path.exists(sp) else {"meetings": {}, "pdfs": {}}
    status, inbox, cal = {}, [], []
    pdf_budget = MAX_PDF
    cands = []
    for cid, name, area, system, base in COUNCILS:
        st = {"name": name, "system": system, "base": base, "meetings": 0, "changed": 0, "state": "ok", "note": ""}
        status[cid] = st
        if system not in ADAPT:
            st["state"], st["note"] = "manual", "no machine-readable meetings system found; the desk checks it by search"
            continue
        ok, why = F.allowed(base + "/")
        if not ok:
            st["state"], st["note"] = "refused", why
            continue
        lister, reader = ADAPT[system]
        try:
            meets, err = lister(cid, base)
        except Exception as e:
            meets, err = [], f"error {e!r}"[:200]
        if not meets:
            st["state"] = "blocked" if err and re.search(r" 40[13] ", f" {err} ") else ("unreachable" if err else "quiet")
            st["note"] = err or "no meetings in window"
            continue
        st["meetings"] = len(meets)
        for meet in sorted(meets, key=lambda m: m["date"], reverse=True):
            try:
                det, err = reader(cid, base, meet)
            except Exception as e:
                det, err = None, repr(e)[:200]
            if not det:
                st["note"] = err or ""
                continue
            key = f"{cid}:{meet['mid']}"
            items = []
            for it in det["items"]:
                it["score"] = score_item(it["title"], it["text"], meet["committee"], bool(it["docs"]))
                items.append(it)
            sig = fp([(i["title"], i["text"][:3000], [d["url"] for d in i["docs"]]) for i in items] + [p["url"] for p in det["packs"]])
            prev = state["meetings"].get(key, {})
            changed = prev.get("fp") != sig
            state["meetings"][key] = {"fp": sig, "date": meet["date"], "seen": prev.get("seen") or NOW.isoformat(), "changed": NOW.isoformat() if changed else prev.get("changed", NOW.isoformat())}
            past = meet["date"] < TODAY.isoformat()
            rec = {"key": key, "council": cid, "councilName": name, "area": area, "committee": meet["committee"], "date": meet["date"], "time": meet["time"],
                   "url": meet["url"], "cancelled": det["cancelled"], "stage": "decided" if past and any(i["decided"] for i in items) else ("held" if past else "upcoming"),
                   "packs": det["packs"], "items": sorted([i for i in items if i["score"] > 0], key=lambda i: -i["score"])[:12],
                   "new": not prev, "changed": changed}
            if not past and not det["cancelled"]:
                cal.append({"council": cid, "councilName": name, "area": area, "committee": meet["committee"], "date": meet["date"], "time": meet["time"],
                            "url": meet["url"], "items": [i["title"] for i in rec["items"][:4] if i["score"] >= 4]})
            if changed or (NOW - datetime.fromisoformat(state["meetings"][key]["changed"])).days < 3:
                inbox.append(rec)
                st["changed"] += changed
                for it in rec["items"][:3]:
                    for d in it["docs"][:1]:
                        cands.append((it["score"] + (4 if rec["stage"] == "decided" else 0), cid, d["url"], it))
    # PDF excerpts for the strongest items, newest information first
    for sc, cid, url, it in sorted(cands, key=lambda x: -x[0]):
        if pdf_budget <= 0 or sc < 8:
            break
        if url in state["pdfs"]:
            it["excerpt"] = state["pdfs"][url].get("excerpt", "")
            it["pages"] = state["pdfs"][url].get("pages")
            continue
        ex = pdf_excerpt(cid, url)
        pdf_budget -= 1
        if ex:
            it["excerpt"], it["pages"], it["excerptOf"] = ex["excerpt"], ex["pages"], url
            state["pdfs"][url] = {"at": NOW.isoformat(), **ex}
    # trim state: forget meetings older than 70 days and pdf excerpts older than 30 days
    cut = (TODAY - timedelta(days=70)).isoformat()
    state["meetings"] = {k: v for k, v in state["meetings"].items() if v.get("date", "9") >= cut}
    pcut = (NOW - timedelta(days=30)).isoformat()
    state["pdfs"] = {k: v for k, v in state["pdfs"].items() if v.get("at", "9") >= pcut}
    inbox.sort(key=lambda r: (r["stage"] != "decided", -max([i["score"] for i in r["items"]] or [0])))
    json.dump({"at": NOW.isoformat(), "window": [str(TODAY - timedelta(days=BACK)), str(TODAY + timedelta(days=AHEAD))], "meetings": inbox},
              open(os.path.join(out, "inbox.json"), "w"), ensure_ascii=False, indent=1)
    cal.sort(key=lambda r: (r["date"], r["time"]))
    json.dump({"at": NOW.isoformat(), "meetings": cal[:120]}, open(os.path.join(out, "calendar.json"), "w"), ensure_ascii=False, indent=1)
    json.dump({"at": NOW.isoformat(), "councils": status, "requests": F.count}, open(os.path.join(out, "status.json"), "w"), ensure_ascii=False, indent=1)
    json.dump(state, open(sp, "w"), ensure_ascii=False)
    print(json.dumps({k: (v["state"], v["meetings"], v["changed"], v["note"][:80]) for k, v in status.items()}, indent=0))
    print(f"inbox {len(inbox)} meetings, calendar {len(cal)}, pdf excerpts {MAX_PDF - pdf_budget}")

if __name__ == "__main__":
    main()
