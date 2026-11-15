#!/usr/bin/env python3
"""Print collected feed items in full:  python3 tools/feeds/read.py <id> [<id> ...]   (ids from /tmp/feed-data/latest.txt)
Reads /tmp/feed-data/items.json (or the folder given as --dir). Kind O items print the organisation's own text."""
import json, sys
a = sys.argv[1:]
d = "/tmp/feed-data"
if "--dir" in a:
    d = a[a.index("--dir") + 1]; a = [x for i, x in enumerate(a) if x != "--dir" and (i == 0 or a[i - 1] != "--dir")]
items = json.load(open(d + "/items.json", encoding="utf-8"))["items"]
for i in a:
    it = items.get(i)
    if not it:
        print(f"{i}: not found (older than 3 days, or a wrong id)\n"); continue
    print(f"=== {i} | {it['source']} | {it.get('time') or it.get('at')}\n{it['title']}\n{it['url']}\n")
    print((it.get("text") or it.get("summary") or "(no text in the feed: confirm through a search)") + "\n")
