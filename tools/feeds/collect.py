#!/usr/bin/env python3
"""Hourly feed collector for the newsroom (owner's go-ahead, 15 Nov 2026).

The newsroom's unattended runs are often refused when they try to open the three pages the owner asked to be read on
every run, so stories on them were being missed (15 Nov: the Maldon Salt story sat on NewsNow from 13:02). This
collector runs on GitHub Actions every hour, reads the pages itself and saves the headlines to the branch
"feed-data", where every newsroom run reads them at no cost. Essex Police's website refuses GitHub's servers (HTTP 403,
tested 15 Nov 2026), so its news stays with the newsroom's police desk (2i) and the Essex Police Facebook desk.

  newsnow   https://www.newsnow.co.uk/h/UK/England/Essex?type=ln   NewsNow's Essex page, latest first (headlines only)
  nhs       https://www.essex.icb.nhs.uk/news/                      NHS Essex news listing

Outputs (written to OUT, default ./feeds-out):
  <name>.json  {"fetchedAt", "ok", "error", "items": [{"title", "url", "source", "time", "firstSeen"}]}, newest first
  latest.txt   the same as plain text for a quick read: one line per item, new items since the last 3 hours marked NEW
  status.json  per feed: ok, items, new items, error; and when each feed last worked
Rules: identifies itself honestly, obeys robots.txt, one request per page per run, standard library only. Headlines
and links only: it never downloads articles. On a failed read the previous items are kept and marked stale.
"""
import html, json, os, re, sys, urllib.error, urllib.request, urllib.robotparser
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

UA = "TheSeaxNewsDesk/1.0 (+https://theseax.com/about/; info@theseax.com)"
HEAD = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8", "Accept-Language": "en-GB,en;q=0.9"}
NOW = datetime.now(timezone.utc)
ISO = "%Y-%m-%dT%H:%M:%SZ"
FEEDS = {
    "newsnow": "https://www.newsnow.co.uk/h/UK/England/Essex?type=ln",
    "nhs": "https://www.essex.icb.nhs.uk/news/",
}

def allowed(url):
    rp = urllib.robotparser.RobotFileParser()
    p = urlparse(url)
    try:
        req = urllib.request.Request(f"{p.scheme}://{p.netloc}/robots.txt", headers=HEAD)
        with urllib.request.urlopen(req, timeout=20) as r:
            rp.parse(r.read().decode("utf-8", "replace").splitlines())
    except Exception:
        return True   # no readable robots.txt: nothing forbids the page
    return rp.can_fetch(UA, url)

def get(url):
    req = urllib.request.Request(url, headers=HEAD)
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", "replace")

def clean(s):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", s or "")).split())

class Links(HTMLParser):
    """Every link with its text, plus the plain text that follows it up to the next link (outlet name and time)."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.cur, self.skip = [], None, 0
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.skip += 1
        if tag == "a":
            a = dict(attrs)
            self.cur = {"href": a.get("href") or "", "cls": a.get("class") or "", "text": "", "after": ""}
            self.out.append(self.cur); self.open = True
        elif tag == "time" and self.out:
            a = dict(attrs)
            self.out[-1].setdefault("dt", a.get("datetime") or a.get("data-time") or "")
    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.skip = max(0, self.skip - 1)
        if tag == "a":
            self.open = False
    def handle_data(self, data):
        if self.skip or not self.out:
            return
        if getattr(self, "open", False):
            self.out[-1]["text"] += data
        elif len(self.out[-1]["after"]) < 200:
            self.out[-1]["after"] += " " + data

def links(page, base):
    p = Links(); p.feed(page)
    for l in p.out:
        l["text"], l["after"], l["href"] = " ".join(l["text"].split()), " ".join(l["after"].split()), urljoin(base, l["href"])
    return p.out

TIME_RX = re.compile(r"\b(\d{1,2}:\d{2}|\d{1,2}\s?(?:m|h|d)\b|\d{1,2}-[A-Z][a-z]{2}-\d{2})")

def newsnow(page, base):
    items, seen = [], set()
    ls = links(page, base)
    for i, l in enumerate(ls):
        t, host = l["text"], urlparse(l["href"]).netloc
        # article links go out through NewsNow's click counter (c.newsnow.co.uk/A/...) or straight to the outlet
        art = "newsnow.co.uk/A/" in l["href"] or "hll" in l["cls"] or (host and "newsnow" not in host)
        if not art or len(t) < 28 or len(t) > 260 or l["href"] in seen:
            continue
        seen.add(l["href"])
        after = l["after"]
        nxt = ls[i + 1] if i + 1 < len(ls) else None
        src = ""
        if nxt and 2 < len(nxt["text"]) < 45 and "newsnow" in urlparse(nxt["href"]).netloc and "/A/" not in nxt["href"]:
            src = nxt["text"]; after = (after + " " + nxt["after"]).strip()
        m = TIME_RX.search(after)
        if not src:
            src = TIME_RX.split(after)[0].strip(" -|·,")[:60]
        items.append({"title": t, "url": l["href"], "source": src, "time": l.get("dt") or (m.group(1) if m else "")})
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

def police(page, base):
    items = []
    for it in ET.fromstring(page.encode("utf-8")).iter("item"):
        d = (it.findtext("pubDate") or "").strip()
        try:
            d = parsedate_to_datetime(d).astimezone(timezone.utc).strftime(ISO)
        except Exception:
            pass
        items.append({"title": clean(it.findtext("title")), "url": (it.findtext("link") or "").strip(), "source": "Essex Police",
                      "time": d, "summary": clean(it.findtext("description"))[:400]})
    return items

def nhs(page, base):
    items, seen = [], set()
    for l in links(page, base):
        p = urlparse(l["href"])
        if "essex.icb.nhs.uk" not in p.netloc or not re.match(r"^/news/[^/?#]{12,}/?$", p.path) or len(l["text"]) < 20 or l["href"] in seen:
            continue
        if re.match(r"^/news/(page|category|tag)/", p.path):
            continue
        seen.add(l["href"])
        m = re.search(r"\b(\d{1,2} [A-Z][a-z]+ 20\d\d)\b", l["after"])
        items.append({"title": l["text"], "url": l["href"], "source": "NHS Essex", "time": m.group(1) if m else ""})
    return items

PARSE = {"newsnow": newsnow, "nhs": nhs}

def load(p, d):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return d

def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "feeds-out"
    os.makedirs(out, exist_ok=True)
    now = NOW.strftime(ISO)
    seen = load(os.path.join(out, "seen.json"), {})
    status = load(os.path.join(out, "status.json"), {})
    status = {"at": now, "feeds": status.get("feeds") or {}}
    text = [f"Feeds collected {now} (UTC). NEW = first seen in the last 3 hours.", ""]
    for name, url in FEEDS.items():
        prev = load(os.path.join(out, name + ".json"), {"items": []})
        st = status["feeds"].get(name) or {}
        err, items = "", None
        try:
            if not allowed(url):
                err = "robots.txt does not allow this page"
            else:
                page = get(url)
                items = PARSE[name](page, url)
                if not items:
                    err = f"page read ({len(page)} characters) but no headlines found"
                    open(os.path.join(out, name + "-raw.txt"), "w", encoding="utf-8").write(page[:60000])
                    items = None
        except urllib.error.HTTPError as e:
            err = f"HTTP {e.code}"
        except Exception as e:
            err = f"{type(e).__name__}: {str(e)[:160]}"
        if items is None:
            doc = {"fetchedAt": prev.get("fetchedAt", ""), "ok": False, "stale": True, "error": err, "triedAt": now, "items": prev.get("items") or []}
        else:
            for it in items:
                it["firstSeen"] = seen.setdefault(name + "|" + it["url"], now)
            doc = {"fetchedAt": now, "ok": True, "error": "", "items": items[:120]}
            st["lastOk"] = now
        cut = (NOW - timedelta(hours=3)).strftime(ISO)
        new = [it for it in doc["items"] if it.get("firstSeen", "") >= cut]
        st.update({"ok": doc["ok"], "error": err, "items": len(doc["items"]), "new": len(new) if doc["ok"] else 0})
        status["feeds"][name] = st
        json.dump(doc, open(os.path.join(out, name + ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        text += [f"== {name}: {url}", f"   {'read ' + doc['fetchedAt'] if doc['ok'] else 'NOT READ THIS HOUR (' + err + '); items below are from ' + (doc['fetchedAt'] or 'never')}", ""]
        for it in doc["items"][:80]:
            when = (it.get("time", "") + (" " + it["day"] if it.get("day") else ""))[:22]
            text.append(f"{'NEW ' if it in new and doc['ok'] else '    '}{when:<22} | {it.get('source', '')[:32]:<32} | {it['title']} | {it['url']}")
        text.append("")
        print(name, "ok" if doc["ok"] else "FAILED: " + err, len(doc["items"]), "items,", st["new"], "new")
    old = (NOW - timedelta(days=7)).strftime(ISO)
    json.dump({k: v for k, v in seen.items() if v >= old}, open(os.path.join(out, "seen.json"), "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(status, open(os.path.join(out, "status.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    open(os.path.join(out, "latest.txt"), "w", encoding="utf-8").write("\n".join(text) + "\n")

if __name__ == "__main__":
    main()
