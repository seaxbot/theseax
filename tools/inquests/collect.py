#!/usr/bin/env python3
"""Essex Coroner inquest list collector (owner's request, 13 Nov 2026).

Runs on GitHub Actions twice a day. It reads the Essex Coroner's public "Search for an inquest" list
(https://coroner.essex.gov.uk/inquests/search-for-an-inquest/), which the coroner publishes each working day by
5pm with two days' notice of hearings. The list is newest first, so the collector reads page 1 onwards until it
reaches hearings more than LOOKBACK days old.

Outputs (written to OUT, default ./inquest-out):
  inquests.json  {"generated", "pagesRead", "rows": every row seen, "cases": rows grouped by person}
  seen.json      first time each case was seen (kept between runs, so the desk can spot new listings)
  status.json    pages read, rows, cases, errors
  page1.html     the first page as fetched (for checking the parser)
Rules: identifies itself honestly, obeys robots.txt, waits between requests, standard library only.
"""
import html, json, os, re, sys, time, urllib.request, urllib.robotparser
from datetime import datetime, timezone, date, timedelta
from html.parser import HTMLParser
from urllib.parse import urljoin

UA = "TheSeaxNewsDesk/1.0 (+https://theseax.com/about/; info@theseax.com)"
HEAD = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml", "Accept-Language": "en-GB,en;q=0.9"}
BASE = "https://coroner.essex.gov.uk"
LIST = BASE + "/inquests/search-for-an-inquest/"
NOW = datetime.now(timezone.utc)
TODAY = NOW.date()
LOOKBACK = 21          # days of past hearings to keep (for outcome follow-ups)
MAX_PAGES = 80
PAUSE = 1.5
MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}

log_lines = []
def log(*a):
    s = " ".join(str(x) for x in a)
    log_lines.append(s)
    print(s, flush=True)


class TableParser(HTMLParser):
    """Collects every table row as a list of (text, [hrefs]) cells, plus the largest page number linked."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows, self.row, self.cell, self.links = [], None, None, None
        self.max_page = 1
        self.depth_skip = 0
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style"):
            self.depth_skip += 1
        if tag == "tr":
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell, self.links = [], []
        elif tag == "br" and self.cell is not None:
            self.cell.append("\n")
        elif tag == "a":
            href = a.get("href") or ""
            m = re.search(r"[?&]page=(\d+)", href)
            if m:
                self.max_page = max(self.max_page, int(m.group(1)))
            if self.cell is not None and href:
                self.links.append(urljoin(LIST, href))
        if tag in ("p", "div", "span", "li") and self.cell is not None:
            self.cell.append("\n")
    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.depth_skip = max(0, self.depth_skip - 1)
        if tag in ("td", "th") and self.cell is not None and self.row is not None:
            txt = "".join(self.cell)
            lines = [" ".join(l.split()) for l in txt.split("\n")]
            self.row.append((" | ".join(l for l in lines if l), self.links))
            self.cell, self.links = None, None
        elif tag == "tr" and self.row is not None:
            if self.row:
                self.rows.append(self.row)
            self.row = None
    def handle_data(self, d):
        if self.cell is not None and not self.depth_skip:
            self.cell.append(d)


def parse_date(s):
    s = s or ""
    m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?\s+(\d{4})", s)
    if m and m.group(2)[:3].lower() in MONTHS:
        try:
            return date(int(m.group(3)), MONTHS[m.group(2)[:3].lower()], int(m.group(1)))
        except ValueError:
            return None
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


COLS = [("hearing", ("date of inquest", "inquest date", "hearing")), ("name", ("name",)), ("type", ("type",)),
        ("death", ("date of death",)), ("age", ("age",)), ("place", ("place",)), ("conclusion", ("conclusion",))]

def col_map(header):
    out = {}
    for i, (t, _) in enumerate(header):
        t = t.lower()
        for key, words in COLS:
            if key in out:
                continue
            if key == "hearing" and "death" in t:
                continue
            if key == "type" and "date" in t:
                continue
            if any(w in t for w in words):
                out[key] = i
                break
    return out


def rows_from(page_html, page_no):
    p = TableParser()
    p.feed(page_html)
    header, cmap, out = None, None, []
    for r in p.rows:
        texts = [c[0].lower() for c in r]
        if any("name" in t for t in texts) and any("death" in t for t in texts) and len(r) >= 4:
            header, cmap = r, col_map(r)
            continue
        if not cmap or len(r) < 4:
            continue
        get = lambda k: r[cmap[k]][0] if k in cmap and cmap[k] < len(r) else ""
        hearing_txt = get("hearing")
        hd = parse_date(hearing_txt)
        tm = re.search(r"\b(\d{1,2}[:.]\d{2})\b", hearing_txt)
        room = re.search(r"(Court\s*Room\s*\d+|Courtroom\s*\d+)", hearing_txt, re.I)
        venue = hearing_txt
        for bit in filter(None, [hd and re.search(r"\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]{3,9}\.?\s+\d{4}|\d{1,2}/\d{1,2}/\d{4}", hearing_txt), tm, room]):
            venue = venue.replace(bit.group(0), " ")
        venue = re.sub(r"^[\s|,:\-]+|[\s|,:\-]+$", "", re.sub(r"(\s*\|\s*)+", " | ", venue))
        venue = re.sub(r"^(at|in)\s+", "", venue, flags=re.I).strip(" |,")
        dd = parse_date(get("death"))
        links = [l for c in r for l in c[1] if "page=" not in l]
        row = {
            "hearingDate": hd.isoformat() if hd else "",
            "hearingTime": tm.group(1).replace(".", ":") if tm else "",
            "room": " ".join(room.group(1).split()) if room else "",
            "venue": venue,
            "hearingRaw": hearing_txt,
            "name": get("name").replace(" | ", " "),
            "type": get("type").replace(" | ", " "),
            "deathDate": dd.isoformat() if dd else "",
            "deathRaw": get("death"),
            "age": get("age"),
            "place": get("place").replace(" | ", ", "),
            "conclusion": get("conclusion").replace(" | ", " "),
            "links": links[:3],
            "page": page_no,
        }
        if row["name"]:
            out.append(row)
    return out, p.max_page, bool(cmap)


def case_key(r):
    n = re.sub(r"[^a-z0-9]+", "-", r["name"].lower()).strip("-")
    return f"{n}-{r['deathDate'] or re.sub(r'[^0-9a-z]+', '', r['deathRaw'].lower())}"


def nice_name(listed):
    """'MALIK Muhammad Ahmad Mahmood' -> 'Muhammad Ahmad Mahmood Malik' (surname is the capitalised word(s) first)."""
    parts = listed.split()
    sur = []
    while parts and parts[0].isupper() and len(parts[0]) > 1:
        sur.append(parts.pop(0))
    if not sur or not parts:
        return listed.title() if listed.isupper() else listed
    return " ".join(parts + [s.title() for s in sur])


class Fetcher:
    def __init__(self):
        self.rp, self.last = None, 0.0
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
    def get(self, url):
        if not self.allowed(url):
            raise RuntimeError("robots.txt disallows " + url)
        wait = PAUSE - (time.time() - self.last)
        if wait > 0:
            time.sleep(wait)
        req = urllib.request.Request(url, headers=HEAD)
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                return r.read().decode("utf-8", "replace")
        finally:
            self.last = time.time()


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "inquest-out"
    os.makedirs(out_dir, exist_ok=True)
    seen_p = os.path.join(out_dir, "seen.json")
    try:
        seen = json.load(open(seen_p))
    except Exception:
        seen = {}
    f = Fetcher()
    rows, errors, pages, last_page = [], [], 0, None
    cutoff = TODAY - timedelta(days=LOOKBACK)
    page = 1
    while page <= MAX_PAGES:
        url = LIST if page == 1 else f"{LIST}?page={page}"
        try:
            h = f.get(url)
        except Exception as e:
            errors.append(f"{url}: {e}")
            log("ERROR", url, e)
            if page == 1:
                break
            page += 1
            continue
        pages += 1
        if page == 1:
            open(os.path.join(out_dir, "page1.html"), "w").write(h)
        got, mp, has_table = rows_from(h, page)
        last_page = max(last_page or 1, mp)
        log(f"page {page}: {len(got)} rows" + ("" if has_table else " (no inquest table found)"))
        if not got:
            break
        for r in got:
            r["url"] = url
        rows.extend(got)
        dates = [r["hearingDate"] for r in got if r["hearingDate"]]
        if dates and max(dates) < cutoff.isoformat():
            break
        if page >= last_page:
            break
        page += 1
    rows = [r for r in rows if not r["hearingDate"] or r["hearingDate"] >= cutoff.isoformat()]
    # de-duplicate identical rows (same person, same hearing slot)
    uniq, keys = [], set()
    for r in rows:
        k = (r["name"], r["hearingDate"], r["hearingTime"], r["type"], r["room"])
        if k in keys:
            continue
        keys.add(k)
        uniq.append(r)
    rows = uniq
    cases = {}
    for r in rows:
        k = case_key(r)
        r["key"] = k
        c = cases.setdefault(k, {"key": k, "listedName": r["name"], "name": nice_name(r["name"]), "age": r["age"],
                                 "deathDate": r["deathDate"], "deathRaw": r["deathRaw"], "place": r["place"],
                                 "hearings": [], "conclusion": ""})
        c["hearings"].append({"date": r["hearingDate"], "time": r["hearingTime"], "type": r["type"], "room": r["room"],
                              "venue": r["venue"], "url": r["url"]})
        if r["conclusion"] and not c["conclusion"]:
            c["conclusion"] = r["conclusion"]
        if r["links"] and not c.get("links"):
            c["links"] = r["links"]
    stamp = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
    for k, c in cases.items():
        c["hearings"].sort(key=lambda h: (h["date"], h["time"]))
        days = sorted({h["date"] for h in c["hearings"] if h["type"].lower().startswith("inquest hearing")})
        c["hearingDays"] = len(days)
        c["types"] = sorted({h["type"] for h in c["hearings"]})
        c["firstHearing"] = c["hearings"][0]["date"] if c["hearings"] else ""
        c["lastHearing"] = c["hearings"][-1]["date"] if c["hearings"] else ""
        if k not in seen:
            seen[k] = stamp
        c["firstSeen"] = seen[k]
    # forget cases not seen for 60 days
    keep_after = (NOW - timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
    seen = {k: v for k, v in seen.items() if k in cases or v >= keep_after}
    case_list = sorted(cases.values(), key=lambda c: (c["firstHearing"], c["name"]))
    json.dump({"generated": stamp, "source": LIST, "pagesRead": pages, "lastPage": last_page,
               "rows": rows, "cases": case_list}, open(os.path.join(out_dir, "inquests.json"), "w"), ensure_ascii=False, indent=1)
    json.dump(seen, open(seen_p, "w"), indent=0)
    status = {"generated": stamp, "pagesRead": pages, "lastPage": last_page, "rows": len(rows), "cases": len(case_list),
              "errors": errors[:20]}
    json.dump(status, open(os.path.join(out_dir, "status.json"), "w"), indent=1)
    log(json.dumps(status))


if __name__ == "__main__":
    main()
