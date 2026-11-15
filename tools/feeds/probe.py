#!/usr/bin/env python3
"""Source probe (owner's request, 15 Nov 2026: "go as deep as you can, be forensic").

Tests every source in tools/feeds/candidates.json (the site's whole directory plus new candidates): is the site
live, what is it called, and does it publish a feed (RSS or Atom) the hourly collector could read? Run by hand
from GitHub Actions (.github/workflows/feeds-probe.yml); results go to the branch "probe-data" as results.json.
Rules: identifies itself honestly, obeys robots.txt, one host at a time with a pause, a handful of requests per
site, headlines only. Standard library only.
"""
import html, json, os, re, sys, threading, time, urllib.error, urllib.request, urllib.robotparser
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

UA = "TheSeaxNewsDesk/1.0 (+https://theseax.com/about/; info@theseax.com)"
HEAD = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "en-GB,en;q=0.9"}
SKIP = re.compile(r"(facebook|twitter|instagram|youtube|tripadvisor|eventbrite|whatsapp|linkedin|tiktok)\.com$|(^|\.)x\.com$")
PATHS = ["feed/", "rss", "rss.xml", "feed.xml", "atom.xml", "news/feed/", "news/rss/", "news/rss.xml", "rss/news", "index.xml"]
ROBOTS, LOCK = {}, threading.Lock()

def robots(url):
    p = urlparse(url); key = p.scheme + "://" + p.netloc
    with LOCK:
        rp = ROBOTS.get(key)
    if rp is None:
        rp = urllib.robotparser.RobotFileParser()
        try:
            with urllib.request.urlopen(urllib.request.Request(key + "/robots.txt", headers=HEAD), timeout=10) as r:
                rp.parse(r.read(200000).decode("utf-8", "replace").splitlines())
        except Exception:
            rp.parse([])
        with LOCK:
            ROBOTS[key] = rp
    return rp.can_fetch(UA, url)

def get(url, limit=1500000):
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEAD), timeout=12) as r:
        return r.status, r.geturl(), r.headers.get("Content-Type", ""), r.read(limit).decode("utf-8", "replace")

def clean(s):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", s or "")).split())

def when(s):
    s = (s or "").strip()
    if not s:
        return ""
    try:
        return parsedate_to_datetime(s).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return ""

def parse_feed(text):
    """Returns (count, newest ISO date, sample titles) or None if this is not a feed."""
    t = text.lstrip()
    if t.startswith("{"):
        try:
            d = json.loads(t)
            items = d.get("items") if isinstance(d, dict) else None
            if isinstance(items, list):
                return len(items), "", [str(i.get("description") or i.get("title") or "")[:90] for i in items[:3]], "json"
        except Exception:
            return None
        return None
    if not re.search(r"<(rss|feed|rdf:RDF)\b", t[:3000]):
        return None
    try:
        root = ET.fromstring(t.encode("utf-8"))
    except Exception:
        return None
    strip = lambda tag: tag.split("}")[-1]
    items = [e for e in root.iter() if strip(e.tag) in ("item", "entry")]
    dates, titles = [], []
    for it in items:
        d = ""
        for ch in it:
            n = strip(ch.tag)
            if n == "title" and len(titles) < 3:
                titles.append(clean(ch.text)[:90])
            if n in ("pubDate", "updated", "published", "date") and not d:
                d = when(ch.text)
        if d:
            dates.append(d)
    return len(items), max(dates) if dates else "", titles, "atom" if strip(root.tag) == "feed" else "rss"

def probe(c):
    url = c["url"]; out = dict(c)
    host = urlparse(url).netloc.lower()
    if SKIP.search(host):
        out["status"] = "skipped (social or ticketing site)"; return out
    tried = 0
    def feed_at(u):
        nonlocal tried
        if tried >= 9 or not robots(u):
            return None
        tried += 1; time.sleep(0.4)
        try:
            st, final, ct, body = get(u)
        except Exception:
            return None
        f = parse_feed(body)
        return (final, f) if f else None
    try:
        if c.get("kind") == "feed":
            if not robots(url):
                out["status"] = "robots.txt does not allow"; return out
            st, final, ct, body = get(url)
            f = parse_feed(body)
            out["status"] = st
            if f:
                out["feed"] = {"url": url, "items": f[0], "newest": f[1], "sample": f[2], "type": f[3]}
            else:
                out["note"] = "not a feed: " + clean(body[:160])
            return out
        if not robots(url):
            out["status"] = "robots.txt does not allow"; return out
        st, final, ct, body = get(url, 500000)
        out["status"], out["final"] = st, final
        m = re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I)
        out["title"] = clean(m.group(1))[:120] if m else ""
        f0 = parse_feed(body)
        if f0:
            out["feed"] = {"url": final, "items": f0[0], "newest": f0[1], "sample": f0[2], "type": f0[3]}; return out
        cands = []
        for tag in re.findall(r"<link\b[^>]*>", body, re.I):
            if re.search(r'rel=["\']?alternate', tag, re.I) and re.search(r"application/(rss|atom)\+xml", tag, re.I):
                h = re.search(r'href=["\']([^"\']+)', tag, re.I)
                if h and "comments" not in h.group(1):
                    cands.append(urljoin(final, html.unescape(h.group(1))))
        base = final if final.endswith("/") else final + "/"
        root = f"{urlparse(final).scheme}://{urlparse(final).netloc}/"
        cands += [base + "feed/", base + "rss"] if base != root else []
        cands += [root + p for p in PATHS]
        seen = set()
        for u in cands:
            if u in seen:
                continue
            seen.add(u)
            r = feed_at(u)
            if r:
                f = r[1]
                out["feed"] = {"url": r[0], "items": f[0], "newest": f[1], "sample": f[2], "type": f[3]}
                break
    except urllib.error.HTTPError as e:
        out["status"] = f"HTTP {e.code}"
    except Exception as e:
        out["status"] = f"{type(e).__name__}: {str(e)[:100]}"
    return out

def main():
    here = os.path.dirname(os.path.abspath(__file__))
    cands = json.load(open(os.path.join(here, "candidates.json"), encoding="utf-8"))
    outdir = sys.argv[1] if len(sys.argv) > 1 else "probe-out"
    os.makedirs(outdir, exist_ok=True)
    by_host = {}
    for c in cands:
        by_host.setdefault(urlparse(c["url"]).netloc.lower(), []).append(c)
    def run_host(lst):
        res = []
        for c in lst:
            res.append(probe(c)); time.sleep(0.5)
        return res
    results = []
    with ThreadPoolExecutor(max_workers=24) as ex:
        for res in ex.map(run_host, by_host.values()):
            results += res
    json.dump({"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "results": results},
              open(os.path.join(outdir, "results.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    ok = sum(1 for r in results if r.get("status") == 200)
    print(len(results), "sources tested;", ok, "live;", sum(1 for r in results if r.get("feed")), "with a feed")

if __name__ == "__main__":
    main()
