#!/usr/bin/env python3
"""Tell Bing (and the other IndexNow engines) about new and changed pages the moment they go live.

Run by .github/workflows/indexnow.yml after every push to main:
    python3 tools/indexnow.py <before-sha> <after-sha>

It lists the built pages that changed between the two commits (story pages, area pages, Council Watch,
briefings, the front page), turns them into theseax.com URLs and posts them to api.indexnow.org.
Bing feeds ChatGPT search, so this is how new stories reach AI search quickly.
The key file (<key>.txt) sits in the site root so the engines can check we own the site.
"""
import json, os, subprocess, sys, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = "https://theseax.com"
HOST = "theseax.com"
KEY = "b06cc39c0c39b416b21345fec750c62c"
WATCH = ("story/", "news/", "council-watch/", "briefing/", "about/")


def changed(before, after):
    for rng in ([f"{before}..{after}"] if before and set(before) != {"0"} else []) + [f"{after}~1..{after}"]:
        r = subprocess.run(["git", "-C", ROOT, "diff", "--name-only", "--diff-filter=AM", rng],
                           capture_output=True, text=True)
        if r.returncode == 0:
            return r.stdout.split()
    return []


def to_urls(paths):
    urls = set()
    for p in paths:
        if p == "edition.json" or p == "index.html":
            urls.add(SITE + "/")
        elif p.endswith("/index.html") and p.startswith(WATCH):
            urls.add(f"{SITE}/{p[:-len('index.html')]}")
    return sorted(urls)


def main():
    before = sys.argv[1] if len(sys.argv) > 1 else ""
    after = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else "HEAD"
    urls = to_urls(changed(before, after))
    if not urls:
        print("indexnow: nothing to send")
        return 0
    body = json.dumps({"host": HOST, "key": KEY, "keyLocation": f"{SITE}/{KEY}.txt",
                       "urlList": urls[:10000]}).encode()
    req = urllib.request.Request("https://api.indexnow.org/indexnow", data=body,
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"indexnow: sent {len(urls)} URL(s), HTTP {r.status}")
    except urllib.error.HTTPError as e:
        # 403 = key file not live yet; 422 = URL not on this host; 429 = too many requests. None should fail the run.
        print(f"indexnow: HTTP {e.code} {e.read()[:200]!r} for {len(urls)} URL(s)")
    for u in urls[:20]:
        print("  ", u)
    return 0


if __name__ == "__main__":
    sys.exit(main())
