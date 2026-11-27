#!/usr/bin/env python3
"""Trial run for new sources (owner's request, 27 Nov 2026: "be pulling in everything you possibly can").

Tests every entry in tools/feeds/trial.json from GitHub's servers, which is where the hourly collector runs, so a
source is only added to feeds.json once it has been read from there. Three kinds of entry:
  "feed"   a feed address: is it a feed, how many items, how new
  "site"   a home page: is the site live, what is it called, does it advertise a feed (as tools/feeds/probe.py)
  "links"  a news listing page with no feed: what the collector's headline-link reader finds on it
Results go to the branch "trial-data" as results.json. Same rules as the collector: honest name, robots.txt obeyed.
"""
import json, os, sys, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urlparse
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import probe, collect

def one(c):
    out = dict(c)
    try:
        if c["kind"] in ("feed", "site"):
            out.update(probe.probe(dict(c, kind="feed") if c["kind"] == "feed" else {k: v for k, v in c.items() if k != "kind"}))
            out["kind"] = c["kind"]
        else:
            st = {}
            if not collect.allowed(c["url"], st):
                out["status"] = "robots.txt does not allow"; return out
            body = collect.get(c["url"])[0]
            out["ld"] = len(collect.parse_page(body, {"url": c["url"]}))
            try:
                items = collect.parse_links(body, {"url": c["url"], "kind": "O", **({"match": c["match"]} if c.get("match") else {})})
                out["links"] = len(items); out["sample"] = [[i["title"][:90], i["url"][:140]] for i in items[:12]]
            except Exception as e:
                out["links"] = 0; out["note"] = str(e)[:200]
            if c.get("raw"):   # every same-site link with some text, to work out a "match" pattern by hand
                import re, html
                from urllib.parse import urljoin
                host = urlparse(c["url"]).netloc.replace("www.", "")
                raw = []
                for m in collect.LINK_RX.finditer(re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", body)):
                    u = urljoin(c["url"], html.unescape(m.group(1))); tx = " ".join(collect.clean(m.group(2)).split())
                    if host in u and len(tx) >= 18:
                        raw.append([tx[:80], u[:150]])
                out["raw"] = raw[:150]; out["starts"] = " ".join(collect.clean(body[:200000]).split())[:300]
            out["status"] = 200
    except Exception as e:
        out["status"] = f"{type(e).__name__}: {str(e)[:120]}"
    return out

def main():
    cands = json.load(open(os.path.join(HERE, "trial.json"), encoding="utf-8"))
    outdir = sys.argv[1] if len(sys.argv) > 1 else "trial-out"; os.makedirs(outdir, exist_ok=True)
    by_host = {}
    for c in cands:
        by_host.setdefault(urlparse(c["url"]).netloc.lower(), []).append(c)
    def run_host(lst):
        res = []
        for c in lst:
            res.append(one(c)); time.sleep(0.5)
        return res
    results = []
    with ThreadPoolExecutor(max_workers=32) as ex:
        for res in ex.map(run_host, by_host.values()):
            results += res
    json.dump({"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "results": results},
              open(os.path.join(outdir, "results.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print(len(results), "tested;", sum(1 for r in results if r.get("feed")), "feeds;", sum(1 for r in results if r.get("links", 0) >= 3), "link pages")

if __name__ == "__main__":
    main()
