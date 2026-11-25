#!/usr/bin/env python3
"""Hourly feed collector for the newsroom (owner's go-ahead, 15 Nov 2026; widened the same night after a forensic
probe of the whole source directory found about 200 sources with live feeds that no run was reading).

The newsroom's unattended runs cannot open pages on their own without a search turning them up first, so sources
were being missed (15 Nov: the Maldon Salt story sat on NewsNow from 05:01). This collector runs on GitHub Actions
every hour, reads the sources itself and saves the headlines to the branch "feed-data", where every newsroom run
reads them at no cost.

  NewsNow   https://www.newsnow.co.uk/h/UK/England/Essex?type=ln   NewsNow's Essex page, latest first (headlines only)
  Feeds     every feed in tools/feeds/feeds.json (RSS, Atom or JSON), each marked:
              kind O = an organisation's own releases (councils, NHS, fire, GOV.UK, charities, clubs, venues):
                       the text of each item is kept (up to 4,000 characters) so a story can be written from it
              kind M = a news outlet: headline, link and a short summary only, as a lead
              kind L = a link-only outlet under the owner's source policy (Newsquest, Reach): lead only
              filter "essex" = keep only items that mention an Essex place (national, regional and trade sources)
              "page": "ld" = the source has no feed, so its news listing page is read instead: every link to an
                       article that carries schema.org NewsArticle data (headline, date). For kind O pages, up to
                       PAGE_TEXT_MAX new articles a run from the last 3 days are opened once each for their text,
                       obeying robots.txt (owner's request, 17 Nov 2026, after the newsroom missed a University of
                       Essex story: the university has no feed and its site refuses the newsroom's own fetches)
              "page": "ehaat" = the Essex & Herts Air Ambulance mission reports listing (owner's request, 20 Nov
                       2026): one item per mission card (type, date logged, place, one-line summary); the place alone
                       is the item's Essex test, so the newsroom decides which missions are in Essex

Outputs (written to OUT, default ./feeds-out):
  latest.txt    what is new in the last 4 hours, for every run: NewsNow, then feed items by kind, one line each
  day.txt       the same for the last 24 hours, for the first run of the day
  items.json    every feed item from the last 3 days by id, with its summary or text (tools/feeds/read.py prints them)
  newsnow.json  the NewsNow list;  status.json  what was read and what failed;  state.json  bookkeeping
Rules: identifies itself honestly, obeys robots.txt, one request per feed per run (and none when the site says the
feed has not changed), standard library only. It never downloads articles. On a failed read the previous items are
kept (an organisation's own article page is opened only for "page" sources, above). Essex Police's website refuses GitHub's servers (HTTP 403, tested 15 Nov 2026), so its news stays with the
newsroom's police desk (2i) and the Essex Police Facebook desk.
"""
import glob, hashlib, html, json, os, re, ssl, sys, threading, time, urllib.error, urllib.request, urllib.robotparser
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

UA = "TheSeaxNewsDesk/1.0 (+https://theseax.com/about/; info@theseax.com)"
HEAD = {"User-Agent": UA, "Accept": "application/rss+xml,application/atom+xml,application/xml;q=0.9,text/html;q=0.8,*/*;q=0.7", "Accept-Language": "en-GB,en;q=0.9"}
NOW = datetime.now(timezone.utc)
ISO = "%Y-%m-%dT%H:%M:%SZ"
HERE = os.path.dirname(os.path.abspath(__file__))
NEWSNOW = "https://www.newsnow.co.uk/h/UK/England/Essex?type=ln"

# An item from a national, regional or trade source is kept only if it names somewhere in Essex.
PLACES = ("Essex|Southend|Chelmsford|Colchester|Basildon|Thurrock|Harlow|Braintree|Brentwood|Maldon|Clacton|Harwich|"
          "Tendring|Uttlesford|Saffron Walden|Stansted|Epping|Loughton|Waltham Abbey|Chigwell|Ongar|Billericay|Wickford|"
          "Rayleigh|Rochford|Canvey|Benfleet|Castle Point|Leigh-on-Sea|Westcliff|Shoeburyness|Grays|Tilbury|Purfleet|"
          "Lakeside|South Ockendon|Stanford-le-Hope|Corringham|Witham|Halstead|Coggeshall|Dunmow|Thaxted|Frinton|"
          "Walton-on-the-Naze|Jaywick|Brightlingsea|Mersea|Tiptree|Wivenhoe|Manningtree|Burnham-on-Crouch|"
          "South Woodham|Heybridge|Danbury|Writtle|Ingatestone|Shenfield|Pitsea|Laindon|Wethersfield|Bradwell|"
          "Dartford Crossing|Lower Thames Crossing|London Gateway|Greater Anglia|c2c|Hylands|Foulness")
ESSEX_RX = re.compile(r"\b(" + PLACES + r")\b")
NOT_UK_RX = re.compile(r"Essex County|New Jersey|Massachusetts|Connecticut|Vermont|Ontario|Tennessee|Maryland|Iowa|\bN\.?J\.?\b|\bMass\.")
MEDIA_SUMMARY, ORG_TEXT = 280, 4000
PAGE_TEXT_MAX = 6

# Some sites (www.essex.ac.uk, 17 Nov 2026) use Let's Encrypt's newer "Y" chain, whose ISRG Root YR is not yet in the
# runner's trust store. tools/feeds/certs/ holds those Let's Encrypt intermediates (valid to 2028), trusted as anchors;
# hostnames and expiry are still checked as normal. Applies to every request, robots.txt included.
CTX = ssl.create_default_context()
for _pem in sorted(glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "certs", "*.pem"))):
    CTX.load_verify_locations(_pem)
CTX.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
urllib.request.install_opener(urllib.request.build_opener(urllib.request.HTTPSHandler(context=CTX)))
ROBOTS, LOCK = {}, threading.Lock()

def load(p, d):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return d

def allowed(url, state):
    p = urlparse(url); key = p.scheme + "://" + p.netloc
    with LOCK:
        if key in ROBOTS:
            return ROBOTS[key].can_fetch(UA, url) if ROBOTS[key] is not True else True
        cached = (state.get("robots") or {}).get(key)
    day_ago = (NOW - timedelta(hours=24)).strftime(ISO)
    if cached and cached.get("at", "") >= day_ago and cached.get("lines") is not None:
        lines = cached["lines"]
    else:
        try:
            with urllib.request.urlopen(urllib.request.Request(key + "/robots.txt", headers=HEAD), timeout=10) as r:
                lines = r.read(200000).decode("utf-8", "replace").splitlines()
        except Exception:
            lines = []
        with LOCK:
            state.setdefault("robots", {})[key] = {"at": NOW.strftime(ISO), "lines": lines[:400]}
    rp = urllib.robotparser.RobotFileParser(); rp.parse(lines)
    with LOCK:
        ROBOTS[key] = rp
    return rp.can_fetch(UA, url)

def get(url, cond=None, limit=2500000):
    h = dict(HEAD)
    if cond:
        if cond.get("etag"):
            h["If-None-Match"] = cond["etag"]
        if cond.get("modified"):
            h["If-Modified-Since"] = cond["modified"]
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=15) as r:
        return r.read(limit).decode("utf-8", "replace"), {"etag": r.headers.get("ETag") or "", "modified": r.headers.get("Last-Modified") or ""}

def clean(s):
    s = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", s or "")
    s = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h[1-6]>", "\n", s)
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    return re.sub(r"[ \t\r\f\v]+", " ", re.sub(r"\s*\n\s*", "\n", s)).strip()

def when(s):
    s = (s or "").strip()
    if not s:
        return ""
    for f in (lambda x: parsedate_to_datetime(x), lambda x: datetime.fromisoformat(x.replace("Z", "+00:00"))):
        try:
            d = f(s)
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            return d.astimezone(timezone.utc).strftime(ISO)
        except Exception:
            pass
    return ""

# ---------- NewsNow ----------
class Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip, self.open = [], 0, False
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.skip += 1
        if tag == "a":
            a = dict(attrs)
            self.out.append({"href": a.get("href") or "", "cls": a.get("class") or "", "text": "", "after": ""}); self.open = True
    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.skip = max(0, self.skip - 1)
        if tag == "a":
            self.open = False
    def handle_data(self, data):
        if self.skip or not self.out:
            return
        if self.open:
            self.out[-1]["text"] += data
        elif len(self.out[-1]["after"]) < 200:
            self.out[-1]["after"] += " " + data

TIME_RX = re.compile(r"\b(\d{1,2}:\d{2}|\d{1,2}\s?(?:m|h|d)\b|\d{1,2}-[A-Z][a-z]{2}-\d{2})")

def newsnow(page, base):
    p = Links(); p.feed(page); ls = p.out
    for l in ls:
        l["text"], l["after"], l["href"] = " ".join(l["text"].split()), " ".join(l["after"].split()), urljoin(base, l["href"])
    items, seen = [], set()
    for i, l in enumerate(ls):
        t, host = l["text"], urlparse(l["href"]).netloc
        art = "newsnow.co.uk/A/" in l["href"] or "hll" in l["cls"] or (host and "newsnow" not in host)
        if not art or len(t) < 28 or len(t) > 260 or l["href"] in seen:
            continue
        seen.add(l["href"])
        after = l["after"]; nxt = ls[i + 1] if i + 1 < len(ls) else None; src = ""
        if nxt and 2 < len(nxt["text"]) < 45 and "newsnow" in urlparse(nxt["href"]).netloc and "/A/" not in nxt["href"]:
            src = nxt["text"]; after = (after + " " + nxt["after"]).strip()
        m = TIME_RX.search(after)
        if not src:
            src = TIME_RX.split(after)[0].strip(" -|·,")[:60]
        items.append({"title": t, "url": l["href"], "source": src, "time": m.group(1) if m else ""})
    # the page ends with boxes of headlines from other NewsNow topics; the Essex list is the big group sharing one link code
    codes = [i["url"].split("?", 1)[-1] for i in items if "?" in i["url"]]
    if codes:
        top = max(set(codes), key=codes.count)
        items = [i for i in items if i["url"].endswith("?" + top)]
    # the page shows clock times only (UK time), newest first: when the clock jumps forward, the list has moved back a day
    day, prev = 0, None
    for i in items:
        m = re.match(r"^(\d{1,2}):(\d{2})$", i["time"])
        if m:
            mins = int(m.group(1)) * 60 + int(m.group(2))
            if prev is not None and mins > prev + 5:
                day += 1
            prev = mins
        i["day"] = ["today", "yesterday"][day] if day < 2 else f"{day} days ago"
    return items

# ---------- feeds ----------
LD_CARD = re.compile(r'(?is)<a\b[^>]*href="([^"#]+)"[^>]*>(.*?)</a>')
DATED_URL = re.compile(r"/news/(20\d\d)/(\d\d)/(\d\d)/[a-z0-9-]+/?$")
LD_JSON = re.compile(r'(?s)\{"@type"\s*:\s*"(?:News)?Article".*?\}(?=\s*</script>)')

def parse_page(text, feed):
    """A news listing page with schema.org NewsArticle data in each card (University of Essex)."""
    out, seen = [], set()
    for m in LD_CARD.finditer(text):
        href, inner = m.group(1), m.group(2)
        j = LD_JSON.search(inner); d = {}
        if j:
            try:
                d = json.loads(j.group(0))
            except Exception:
                pass
        dated = DATED_URL.search(href)
        if not d and not dated:
            continue
        if not d.get("datePublished") and dated:   # cards without the data (the page's featured story): date from the address
            d["datePublished"] = "-".join(dated.groups())
        url = urljoin(feed["url"], html.unescape(href))
        title = " ".join(clean(d.get("headline") or inner).split())
        if len(title) < 15 or len(title) > 220:
            continue
        if not title or url in seen:
            continue
        seen.add(url)
        img = d.get("image")
        img = img.get("url") if isinstance(img, dict) else img if isinstance(img, str) else ""
        if not img:   # featured cards carry the picture only in the card itself
            m2 = re.search(r'<img[^>]+(?:data-src|src)="([^"]+)"', inner)
            img = m2.group(1).split("?")[0] if m2 else ""
        out.append({"title": title, "url": url, "time": when(d.get("datePublished") or ""), "body": "",
                    "image": urljoin(feed["url"], html.unescape(img)) if img else ""})
    return out


def parse_missions(text, feed):
    """Essex & Herts Air Ambulance mission reports (owner's request, 20 Nov 2026). The charity has no feed: its listing page
    shows one card per mission with the type, the date it was logged (DD.MM.YYYY), the place and a one-line summary.
    Reports are logged in batches, often a few days after the mission, and the full report adds little; the card is enough.
    Matched loosely (a heading link to /missions/..., the paragraph after it, the type and date just before it)."""
    out, seen = [], set()
    for m in re.finditer(r'(?is)<h\d[^>]*>\s*<a[^>]+href=["\']([^"\']*/missions/[^"\']+)["\'][^>]*>(.*?)</a>\s*</h\d>\s*(?:<p[^>]*>(.*?)</p>)?', text):
        url, place = html.unescape(m.group(1)), " ".join(clean(m.group(2)).split())
        before = text[max(0, m.start() - 700):m.start()]
        kind = re.findall(r'(?is)mission-type[^>]*>(.*?)</span>', before)
        kind = " ".join(clean(kind[-1]).split()) if kind else "Mission"
        d = re.findall(r'(\d\d)\.(\d\d)\.(20\d\d)', before)
        d = d[-1] if d else None
        summary = " ".join(clean(m.group(3) or "").split())
        if not place or url in seen:
            continue
        seen.add(url)
        # the charity's own name contains "Essex", so the summary is not used for the Essex filter: the place decides
        # no "time": the charity logs missions days late, so an item counts from when the collector first sees it;
        # the charity's own logged date goes in the title instead
        logged = f", logged {d[0]}.{d[1]}.{d[2]}" if d else ""
        out.append({"title": f"Air ambulance mission: {place} ({kind}{logged})", "url": urljoin(feed["url"], url),
                    "time": "", "body": summary, "place": place})
    if not out:   # say what came back, so a changed or blocked page shows in status.json instead of silently giving nothing
        raise ValueError("no mission cards found; page starts: " + " ".join(clean(text[:4000]).split())[:160])
    return out

def article_text(url):
    """The readable paragraphs of an organisation's own article page."""
    page = get(url)[0]
    page = re.sub(r"(?is)<(script|style|nav|header|footer|form|aside)\b.*?</\1>", " ", page)
    paras = [clean(p) for p in re.findall(r"(?is)<p\b[^>]*>(.*?)</p>", page)]
    paras = [" ".join(p.split()) for p in paras if len(p) > 40 and "cookie" not in p.lower()]
    return "\n".join(dict.fromkeys(paras))[:ORG_TEXT]

def parse_feed(text, feed):
    """Items of an RSS, Atom or JSON feed (or a listing page) as {title, url, time, body}."""
    if feed.get("page") == "ld":
        return parse_page(text, feed)
    if feed.get("page") == "ehaat":
        return parse_missions(text, feed)
    t = text.lstrip(); out = []
    if feed.get("json"):
        for i in (json.loads(t).get("items") or []):   # Environment Agency flood warnings
            out.append({"title": f"{i.get('severity', 'Flood alert')}: {i.get('description', '')}", "url": str(i.get("@id") or ""),
                        "time": when(i.get("timeMessageChanged") or i.get("timeRaised")), "body": clean(i.get("message") or "")})
        return out
    root = ET.fromstring(t.encode("utf-8"))
    strip = lambda tag: tag.split("}")[-1]
    for it in root.iter():
        if strip(it.tag) not in ("item", "entry"):
            continue
        r = {"title": "", "url": "", "time": "", "body": ""}; short = ""
        for ch in it:
            n = strip(ch.tag)
            if n == "title":
                r["title"] = clean(ch.text)
            elif n == "link":
                href = ch.attrib.get("href")
                if href and ch.attrib.get("rel", "alternate") == "alternate":
                    r["url"] = href
                elif ch.text and not r["url"]:
                    r["url"] = ch.text.strip()
            elif n in ("pubDate", "published", "date") or (n == "updated" and not r["time"]):
                r["time"] = when(ch.text) or r["time"]
            elif n in ("encoded", "content"):
                r["body"] = clean(ch.text or "".join(ch.itertext()))
            elif n in ("description", "summary"):
                short = clean(ch.text or "".join(ch.itertext()))
        r["body"] = r["body"] if len(r["body"]) > len(short) else short
        if r["title"] and r["url"]:
            r["url"] = urljoin(feed["url"], r["url"])
            out.append(r)
    return out

def read_feed(feed, state):
    """Returns (items or None, error, cached). Items carry id, title, url, time, source, kind and summary or text."""
    url = feed["url"]; prev = (state.get("cache") or {}).get(url)
    try:
        if not allowed(url, state):
            return None, "robots.txt does not allow this feed", False
        try:
            body, cond = get(url, (state.get("http") or {}).get(url) if prev is not None else None)
        except urllib.error.HTTPError as e:
            if e.code == 304 and prev is not None:
                return prev, "", True
            raise
        raw = parse_feed(body, feed)
        with LOCK:
            state.setdefault("http", {})[url] = cond
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}", False
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:120]}", False
    if feed.get("page") == "ld" and feed["kind"] == "O":
        with LOCK:
            texts = state.setdefault("pagetext", {})
        cut = (NOW - timedelta(days=3)).strftime(ISO); opened = 0
        for r in raw:
            u = r["url"]
            if u in texts:
                r["body"] = texts[u]
            elif r["time"] >= cut and opened < PAGE_TEXT_MAX and allowed(u, state):
                opened += 1
                try:
                    r["body"] = article_text(u); time.sleep(0.5)
                except Exception:
                    continue
                with LOCK:
                    texts[u] = r["body"]
        with LOCK:
            keep = {r["url"] for r in raw}
            for u in [u for u in texts if u not in keep and u.startswith(feed["url"])]:
                texts.pop(u, None)
    items = []
    skip = re.compile(feed["skip"]) if feed.get("skip") else None
    for r in raw[:60]:
        if skip and skip.search(r["title"]):
            continue
        blob = r["place"] if r.get("place") else r["title"] + " " + r["body"][:1500]
        if feed.get("filter") == "essex" and (not ESSEX_RX.search(blob) or (NOT_UK_RX.search(blob) and not re.search(r"\b(UK|England|Britain|British|council|NHS)\b", blob))):
            continue
        it = {"id": feed["kind"] + hashlib.sha1(r["url"].encode()).hexdigest()[:5], "title": r["title"][:220], "url": r["url"],
              "time": r["time"], "source": feed["name"], "kind": feed["kind"], "group": feed.get("group", "")}
        if feed.get("political"):
            it["political"] = True
        if feed["kind"] == "O":
            it["text"] = r["body"][:ORG_TEXT]
            if r.get("image"):
                it["image"] = r["image"]
        else:
            it["summary"] = " ".join(r["body"][:MEDIA_SUMMARY].split())
        items.append(it)
    return items, "", False

def edition_urls(root):
    """Every source link already used on the site, so items we have covered are not offered again."""
    ed = load(os.path.join(root, "edition.json"), {}); urls = set()
    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k in ("url", "freshUrl") and isinstance(v, str):
                    urls.add(v.split("?")[0].rstrip("/").replace("http://", "https://").replace("://www.", "://"))
                else:
                    walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(ed)
    return urls

SECTIONS = [("O", "ORGANISATIONS' OWN RELEASES (councils, NHS, fire, GOV.UK, charities, clubs, venues). The text of each is collected: "
                  "run  python3 tools/feeds/read.py <id> [<id> ...]  to read it, and you may write the story from that text."),
            ("M", "NEWS OUTLETS (leads: confirm and get a readable link through a search, as for NewsNow leads)"),
            ("L", "LINK-ONLY OUTLETS (Newsquest and Reach: leads only; if used, our own headline and one sentence, no body)")]

def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "feeds-out"
    root = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(os.path.dirname(HERE))
    os.makedirs(out, exist_ok=True)
    now = NOW.strftime(ISO)
    state = load(os.path.join(out, "state.json"), {})
    if state.get("v") != 4:   # the item format or the filters changed: read every feed afresh once
        state["cache"], state["http"], state["v"] = {}, {}, 4
    seen = state.setdefault("seen", {}); known = set(state.get("known") or [])
    feeds = load(os.path.join(HERE, "feeds.json"), [])
    status = {"at": now, "newsnow": (load(os.path.join(out, "status.json"), {}).get("newsnow") or {})}

    # NewsNow
    prev = load(os.path.join(out, "newsnow.json"), {"items": []}); err, nn = "", None
    try:
        if not allowed(NEWSNOW, state):
            err = "robots.txt does not allow this page"
        else:
            nn = newsnow(get(NEWSNOW)[0], NEWSNOW)
            if not nn:
                err, nn = "page read but no headlines found", None
    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:120]}"
    if nn is None:
        nn_doc = {"fetchedAt": prev.get("fetchedAt", ""), "ok": False, "error": err, "items": prev.get("items") or []}
    else:
        for it in nn:
            it["firstSeen"] = seen.setdefault("newsnow|" + it["url"], now)
        nn_doc = {"fetchedAt": now, "ok": True, "error": "", "items": nn[:120]}
        status["newsnow"]["lastOk"] = now
    cut3 = (NOW - timedelta(hours=3)).strftime(ISO)
    status["newsnow"].update({"ok": nn_doc["ok"], "error": err, "items": len(nn_doc["items"]),
                              "new": sum(1 for i in nn_doc["items"] if i.get("firstSeen", "") >= cut3) if nn_doc["ok"] else 0})
    json.dump(nn_doc, open(os.path.join(out, "newsnow.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # feeds, one host at a time, several hosts at once
    by_host = {}
    for f in feeds:
        by_host.setdefault(urlparse(f["url"]).netloc, []).append(f)
    def run_host(lst):
        res = []
        for f in lst:
            res.append((f, *read_feed(f, state))); time.sleep(0.3)
        return res
    results = []
    with ThreadPoolExecutor(max_workers=20) as ex:
        for res in ex.map(run_host, by_host.values()):
            results += res
    cache = state.setdefault("cache", {}); failed, ok, unchanged = [], 0, 0
    used = edition_urls(root); items = {}
    for f, got, e, cached in results:
        if got is None:
            failed.append({"name": f["name"], "error": e}); got = cache.get(f["url"]) or []
        else:
            ok += 1; unchanged += 1 if cached else 0
            cache[f["url"]] = got
        first_time = f["url"] not in known
        for it in got:
            key = "f|" + it["url"]
            if key not in seen:
                seen[key] = "" if first_time and not it["time"] else now   # a feed's back catalogue is not "new"
            # the time an item counts from: its own date (never in the future), else when we first saw it
            it["at"] = min(it["time"], now) if it["time"] else seen[key]
            items.setdefault(it["url"], it)
        known.add(f["url"])
    state["known"] = sorted(known)
    old = (NOW - timedelta(days=7)).strftime(ISO)
    state["seen"] = {k: v for k, v in seen.items() if v == "" or v >= old}
    cut72 = (NOW - timedelta(hours=72)).strftime(ISO)
    recent, titles = [], set()
    for i in sorted((i for i in items.values() if i.get("at", "") >= cut72), key=lambda i: i["at"]):
        t = re.sub(r"[^a-z0-9]+", " ", i["title"].lower()).strip()   # the same story syndicated across sister titles: keep the first
        if t in titles:
            continue
        titles.add(t); recent.append(i)
    recent.reverse()
    json.dump({"at": now, "items": {i["id"]: i for i in recent}}, open(os.path.join(out, "items.json"), "w", encoding="utf-8"), ensure_ascii=False)
    norm = lambda u: u.split("?")[0].rstrip("/").replace("http://", "https://").replace("://www.", "://")

    def write(name, hours, nn_lines):
        cut = (NOW - timedelta(hours=hours)).strftime(ISO)
        text = [f"Feeds collected {now} (UTC). Window: the last {hours} hours. {ok} of {len(feeds)} feeds read"
                + (f", {len(failed)} failed (see status.json)" if failed else "") + ".", "",
                f"== NEWSNOW ESSEX, latest first: {NEWSNOW}",
                f"   {'read ' + nn_doc['fetchedAt'] if nn_doc['ok'] else 'NOT READ THIS HOUR (' + err + '); items below are from ' + (nn_doc['fetchedAt'] or 'never')}"
                "   NEW = first seen in the last 3 hours. Links are leads only: never fetch or publish them.", ""]
        for it in nn_doc["items"][:nn_lines]:
            whenx = (it.get("time", "") + (" " + it["day"] if it.get("day") else ""))[:22]
            text.append(f"{'NEW ' if nn_doc['ok'] and it.get('firstSeen', '') >= cut3 else '    '}{whenx:<22} | {it.get('source', '')[:32]:<32} | {it['title']}")
        counts = {}
        for kind, label in SECTIONS:
            rows = [i for i in recent if i["kind"] == kind and i["at"] >= cut and norm(i["url"]) not in used]
            counts[kind] = len(rows)
            text += ["", f"== {label}", f"   {len(rows)} items not yet on the site. Times are UTC.", ""]
            for i in rows[:(60 if kind == "L" else 120) if hours > 6 else (40 if kind == "L" else 80)]:
                extra = "  [POLITICAL SOURCE: report as their claim]" if i.get("political") else ""
                tag = " [sport desk]" if i.get("group") == "sport" else ""
                text.append(f"{i['id']} | {i['at'][5:16].replace('T', ' ')} | {i['source'][:30]:<30} | {i['title']}{tag}{extra}")
                if kind != "O" and i.get("summary"):
                    text.append(f"         {i['summary'][:170]}")
                if kind != "L":
                    text.append(f"         {i['url']}")
        open(os.path.join(out, name), "w", encoding="utf-8").write("\n".join(text) + "\n")
        return counts
    c4 = write("latest.txt", 4, 80)
    c24 = write("day.txt", 24, 120)
    status["feeds"] = {"total": len(feeds), "read": ok, "unchanged": unchanged, "failed": failed, "new4h": c4, "new24h": c24}
    json.dump(status, open(os.path.join(out, "status.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(state, open(os.path.join(out, "state.json"), "w", encoding="utf-8"), ensure_ascii=False)
    for stale in ("nhs.json", "police.json", "seen.json"):
        try:
            os.remove(os.path.join(out, stale))
        except OSError:
            pass
    print(f"newsnow {'ok' if nn_doc['ok'] else 'FAILED: ' + err} {len(nn_doc['items'])} items; feeds {ok}/{len(feeds)} read "
          f"({unchanged} unchanged), {len(failed)} failed; new in 4h {c4}; in 24h {c24}")
    for f in failed[:40]:
        print("  failed:", f["name"], "|", f["error"])

if __name__ == "__main__":
    main()
