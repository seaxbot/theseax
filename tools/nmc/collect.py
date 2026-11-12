#!/usr/bin/env python3
"""NMC Essex hearings collector (owner's choice, 11 Nov 2026).

Runs on GitHub Actions twice a day. It reads the Nursing and Midwifery Council's public monthly hearings pages
(nmc.org.uk, "Hearings <Month> <Year>": name and PIN, part of register, venue and dates, county where the
allegation took place, committee and hearing type, allegation type, outcome with a link to the reasons) for last
month, this month and next month, keeps only the rows whose county is in Essex (Essex, Southend-on-Sea, Thurrock),
and for finished cases with a published reasons document downloads it and keeps its text for the newsroom.

Outputs (written to OUT, default ./nmc-out):
  essex.json   every Essex row seen, newest first, with a "kind" (outcome, interim, review, upcoming, other)
  reasons/     <key>.txt: plain text of each reasons document for Essex outcomes (first 60,000 characters)
  status.json  pages read, rows seen, Essex rows, documents fetched, errors
Rules: identifies itself honestly, obeys robots.txt, waits between requests, standard library plus pdftotext.
"""
import html, json, os, re, subprocess, sys, tempfile, time, urllib.error, urllib.request, urllib.robotparser
from datetime import datetime, timezone, date
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

UA = "TheSeaxNewsDesk/1.0 (+https://theseax.com/about/; info@theseax.com)"
HEAD = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8", "Accept-Language": "en-GB,en;q=0.9"}
BASE = "https://www.nmc.org.uk"
INDEX = BASE + "/concerns-nurses-midwives/hearings/hearings-sanctions/"
NOW = datetime.now(timezone.utc)
PAUSE = 2.0
MAX_DOCS = 12
ESSEX_RX = re.compile(r"\b(essex|southend|thurrock)\b", re.I)
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
TYPES = {
    "FTPCSH": "Fitness to Practise Committee substantive hearing", "FTPCSM": "Fitness to Practise Committee substantive meeting",
    "FTPCSORH": "substantive order review hearing", "FTPCSORM": "substantive order review meeting",
    "FTPCIO": "interim order hearing or meeting", "ICIO": "interim order hearing or meeting",
    "FTPCRH": "restoration hearing", "AgR": "agreed removal", "ICFESH": "incorrect or fraudulent entry hearing",
    "ICFESM": "incorrect or fraudulent entry meeting",
}

log_lines = []
def log(*a):
    s = " ".join(str(x) for x in a)
    log_lines.append(s)
    print(s, flush=True)

class Fetcher:
    def __init__(self):
        self.rp, self.last, self.n = None, 0.0, 0
    def allowed(self, url):
        if self.rp is None:
            self.rp = urllib.robotparser.RobotFileParser()
            try:
                req = urllib.request.Request(BASE + "/robots.txt", headers=HEAD)
                with urllib.request.urlopen(req, timeout=30) as r:
                    self.rp.parse(r.read().decode("utf-8", "replace").splitlines())
            except Exception as e:
                log("robots.txt unreadable, treating as allowed:", e)
                self.rp.parse([])
        return self.rp.can_fetch(UA, url)
    def get(self, url, binary=False):
        if urlparse(url).netloc not in ("www.nmc.org.uk", "nmc.org.uk"):
            raise RuntimeError("off-site url " + url)
        if not self.allowed(url):
            raise RuntimeError("robots.txt disallows " + url)
        wait = PAUSE - (time.time() - self.last)
        if wait > 0:
            time.sleep(wait)
        self.last = time.time(); self.n += 1
        req = urllib.request.Request(url, headers=HEAD)
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
            final = r.geturl()
        return (data if binary else data.decode("utf-8", "replace")), final

class Tables(HTMLParser):
    """Collects every table as rows of cells; each cell keeps its text and its links."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables, self.links, self.stack = [], [], []
        self.row = self.cell = None
        self.a_href = None
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "table":
            self.stack.append([]); self.tables.append(self.stack[-1])
        elif tag == "tr" and self.stack:
            self.row = []; self.stack[-1].append(self.row)
        elif tag in ("td", "th") and self.row is not None:
            self.cell = {"text": "", "links": [], "th": tag == "th"}; self.row.append(self.cell)
        elif tag == "br" and self.cell is not None:
            self.cell["text"] += "\n"
        elif tag == "a":
            self.a_href = a.get("href")
            if self.a_href:
                self.links.append(self.a_href)
                if self.cell is not None:
                    self.cell["links"].append(self.a_href)
    def handle_endtag(self, tag):
        if tag == "table" and self.stack:
            self.stack.pop(); self.row = self.cell = None
        elif tag in ("td", "th"):
            self.cell = None
        elif tag == "tr":
            self.row = None
        elif tag == "a":
            self.a_href = None
    def handle_data(self, d):
        if self.cell is not None:
            self.cell["text"] += d

def clean(s):
    return re.sub(r"[ \t\r\f\v]+", " ", re.sub(r"\s*\n\s*", "\n", s or "")).strip()

def month_pages(f):
    """URLs of the hearings pages for last month, this month and next month."""
    want = []
    y, m = NOW.year, NOW.month
    for dm in (-1, 0, 1):
        mm, yy = m + dm, y
        if mm < 1: mm, yy = 12, y - 1
        if mm > 12: mm, yy = 1, y + 1
        want.append((MONTHS[mm - 1], yy))
    found = {}
    try:
        page, final = f.get(INDEX)
        p = Tables(); p.feed(page)
        for href in p.links:
            u = urljoin(final, href)
            mt = re.search(r"/hearings-(%s)-(\d{4})/?$" % "|".join(MONTHS), u.split("?")[0].split("#")[0].rstrip("/") + "/")
            if mt:
                found[(mt.group(1), int(mt.group(2)))] = u
    except Exception as e:
        log("index unreadable:", e)
    out = []
    for mon, yy in want:
        if (mon, yy) in found:
            out.append((mon, yy, [found[(mon, yy)]]))
        else:
            out.append((mon, yy, [f"{INDEX}hearings-{mon}-{yy}/", f"{INDEX}archived-hearings-{yy}/hearings-{mon}-{yy}/"]))
    return out

def header_map(cells):
    names = [clean(c["text"]).lower() for c in cells]
    col = {}
    for i, n in enumerate(names):
        if "name" in n and "pin" in n: col["name"] = i
        elif "part of register" in n or n == "register": col["register"] = i
        elif "venue" in n: col["venue"] = i
        elif "county" in n: col["county"] = i
        elif "committee" in n or "hearing type" in n: col["type"] = i
        elif "allegation" in n: col["allegation"] = i
        elif "outcome" in n: col["outcome"] = i
    return col if {"name", "county", "outcome"} <= set(col) else None

def kind_of(htype, outcome):
    o = (outcome or "").lower()
    t = (htype or "").upper()
    if not o or o in ("tbc", "to be confirmed") or re.search(r"\b(adjourned|postponed|part[- ]heard|split event|referred to a hearing|not yet|pending)\b", o):
        return "upcoming" if not re.search(r"adjourned|postponed|part[- ]heard|split event", o) else "other"
    if "ICIO" in t or "FTPCIO" in t:
        return "interim"
    if "SOR" in t:
        return "review"
    if re.search(r"striking[- ]off|suspension order|conditions of practice|caution order|no further action|no case to answer|removal|restor|not impaired|impaired|struck", o):
        return "outcome"
    return "other"

def parse_dates(venue, day_hdr, mon, yy):
    m = re.search(r"(\d{1,2})\s+([A-Za-z]{3})[a-z]*\s*[-–]\s*(\d{1,2})\s+([A-Za-z]{3})", venue or "")
    def mk(d, mname):
        try:
            mi = [x[:3] for x in MONTHS].index(mname.lower()[:3]) + 1
            yr = yy + (1 if (mon == "december" and mi == 1) else 0) - (1 if (mon == "january" and mi == 12) else 0)
            return date(yr, mi, int(d)).isoformat()
        except Exception:
            return ""
    if m:
        return mk(m.group(1), m.group(2)), mk(m.group(3), m.group(4))
    m = re.match(r"(\d{1,2})\s+([A-Za-z]{3})", day_hdr or "")
    if m:
        s = mk(m.group(1), m.group(2)); return s, s
    return "", ""

def parse_page(text, url, mon, yy):
    p = Tables(); p.feed(text)
    rows, seen = [], 0
    for t in p.tables:
        col, day = None, ""
        for r in t:
            if not r: continue
            if col is None:
                col = header_map(r)
                continue
            texts = [clean(c["text"]) for c in r]
            if len([x for x in texts if x]) <= 1 and len(r) < len(col):
                if re.match(r"^\d{1,2}\s+[A-Za-z]{3}", texts[0] if texts else ""):
                    day = texts[0]
                continue
            if max(col.values()) >= len(r):
                continue
            seen += 1
            g = lambda k: texts[col[k]] if k in col and col[k] < len(texts) else ""
            county = g("county")
            if not ESSEX_RX.search(county):
                continue
            name_pin = g("name")
            pm = re.search(r"\(([0-9A-Z]{6,10})\)", name_pin)
            pin = pm.group(1) if pm else ""
            name = clean(re.sub(r"\([0-9A-Z]{6,10}\)", "", name_pin)).replace("\n", " ")
            oc = r[col["outcome"]]
            docs = [urljoin(url, h) for h in oc["links"]]
            venue = g("venue").replace("\n", " ")
            start, end = parse_dates(venue, day, mon, yy)
            htype = g("type").replace("\n", " ")
            outcome = g("outcome").replace("\n", " ")
            rows.append({
                "key": f"{pin or re.sub(r'[^a-z0-9]+', '-', name.lower())}-{start or day}".strip("-"),
                "name": name, "pin": pin, "register": g("register").replace("\n", " ").strip(" ;"), "county": re.sub(r"\s*;\s*", "; ", county).strip(" ;"),
                "venue": venue, "start": start, "end": end, "type": htype,
                "typeName": "; ".join(TYPES[x] for x in re.findall(r"[A-Za-z]+", htype) if x in TYPES),
                "allegation": g("allegation").replace("\n", " "), "outcome": outcome,
                "kind": kind_of(htype, outcome), "reasonsUrl": docs[0] if docs else "", "page": url,
            })
    return rows, seen

def pdf_text(data):
    with tempfile.NamedTemporaryFile(suffix=".pdf") as tf:
        tf.write(data); tf.flush()
        r = subprocess.run(["pdftotext", "-layout", tf.name, "-"], capture_output=True, timeout=120)
        return r.stdout.decode("utf-8", "replace")

def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "nmc-out"
    os.makedirs(os.path.join(out, "reasons"), exist_ok=True)
    prev = {}
    try:
        for r in json.load(open(os.path.join(out, "essex.json"), encoding="utf-8")).get("rows", []):
            prev[r["key"]] = r
    except Exception:
        pass
    f = Fetcher()
    status = {"at": NOW.isoformat(timespec="seconds"), "pages": [], "rowsSeen": 0, "essexRows": 0, "docsFetched": 0, "errors": []}
    rows = {}
    for mon, yy, urls in month_pages(f):
        ok = False
        for u in urls:
            try:
                text, final = f.get(u)
            except urllib.error.HTTPError as e:
                if e.code == 404: continue
                status["errors"].append(f"{u}: HTTP {e.code}"); continue
            except Exception as e:
                status["errors"].append(f"{u}: {e}"); continue
            got, seen = parse_page(text, final, mon, yy)
            status["pages"].append({"month": f"{mon} {yy}", "url": final, "rows": seen, "essex": len(got)})
            status["rowsSeen"] += seen
            for r in got:
                rows[r["key"]] = r
            log(f"{mon} {yy}: {seen} rows, {len(got)} Essex  {final}")
            ok = True
            break
        if not ok:
            log(f"{mon} {yy}: no page found")
    # keep earlier Essex rows for 120 days so finished cases stay findable
    for k, r in prev.items():
        if k not in rows:
            try:
                if (NOW.date() - date.fromisoformat(r["start"])).days <= 120:
                    rows[k] = r
            except Exception:
                pass
    docs = 0
    for k, r in sorted(rows.items(), key=lambda kv: kv[1].get("start", ""), reverse=True):
        path = os.path.join(out, "reasons", re.sub(r"[^A-Za-z0-9_-]+", "-", k) + ".txt")
        if r["kind"] in ("outcome", "review", "interim") and r.get("reasonsUrl") and not os.path.exists(path) and docs < MAX_DOCS:
            try:
                data, final = f.get(r["reasonsUrl"], binary=True)
                txt = pdf_text(data) if data[:4] == b"%PDF" else re.sub(r"<[^>]+>", " ", data.decode("utf-8", "replace"))
                txt = re.sub(r"\n{3,}", "\n\n", txt).strip()
                if txt:
                    open(path, "w", encoding="utf-8").write(txt[:60000])
                    docs += 1
            except Exception as e:
                status["errors"].append(f"reasons {k}: {e}")
        if os.path.exists(path):
            r["reasonsFile"] = "reasons/" + os.path.basename(path)
    status["docsFetched"] = docs
    status["essexRows"] = len(rows)
    ordered = sorted(rows.values(), key=lambda r: (r.get("start", ""), r["key"]), reverse=True)
    json.dump({"at": status["at"], "source": INDEX, "rows": ordered}, open(os.path.join(out, "essex.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(status, open(os.path.join(out, "status.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    log(f"done: {status['rowsSeen']} rows read, {len(rows)} Essex rows kept, {docs} reasons documents fetched, {len(status['errors'])} errors")
    for e in status["errors"][:10]:
        log("  error:", e)

if __name__ == "__main__":
    main()
