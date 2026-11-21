#!/usr/bin/env python3
"""Post The Seax's most significant new story to The Seax X account through Buffer (owner's request, 21 Nov 2026).

Runs on GitHub Actions every hour (.github/workflows/x-buffer.yml). Uses Buffer's GraphQL API (https://api.buffer.com)
with a personal API key stored as the repository secret BUFFER_API_KEY. Standard library only. Without the key it
does nothing.

Built to stay inside Buffer's FREE plan:
  - Free allows 10 scheduled posts per channel at one time. This script never queues ahead: each run sends at most
    ONE post, timed two minutes from now, so there is only ever one post waiting in Buffer.
  - Free API limits are 100 requests per 15 minutes, 250 per day and 3,000 per 30 days. A run uses one request
    (three the very first time, to find the X channel, which is then remembered in the state file). At most
    17 runs a day, so well under 600 requests a month.
Rules (the same editorial choice as the Facebook Page poster, tools/fbpage.py):
  - Quiet hours 23:00 to 06:30 UK time. At most one post per run, at most MAX_PER_DAY posts a day.
  - Picks from stories changed in the last 3 hours that have a story page: breaking first, then the lead, then the
    front-page picks, then weight and freshness. Stories below weight 5 only if breaking, the lead or on the front.
  - Never the same story twice, except one "Update:" for breaking news or the lead with a changed headline.
  - The post is the headline and the story link (X shows the story's picture from the link). No em dashes.
State: data/x-posted.json. Use --dry-run to see what would be posted without posting.
"""
import json, os, sys, urllib.request
from datetime import timedelta, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fbpage  # shares the story choice

ROOT = fbpage.ROOT
SITE = fbpage.SITE
API = "https://api.buffer.com"
STATE = os.path.join(ROOT, "data", "x-posted.json")
MAX_PER_DAY = 12
LINK_LEN = 23   # X counts every link as 23 characters
LIMIT = 280

def gql(key, query, variables=None):
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(API, data=body, headers={"Content-Type": "application/json",
                                 "Authorization": f"Bearer {key}", "User-Agent": "TheSeaxXPoster/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        out = json.loads(r.read().decode())
    if out.get("errors"):
        raise RuntimeError("Buffer said: " + "; ".join(str(e.get("message")) for e in out["errors"])[:400])
    return out.get("data") or {}

def find_channel(key):
    """The id of the X channel in the owner's Buffer account (two requests, done once)."""
    orgs = (gql(key, "query { account { organizations { id name } } }").get("account") or {}).get("organizations") or []
    for o in orgs:
        chans = gql(key, "query { channels(input: {organizationId: %s}) { id name service } }" % json.dumps(o["id"])).get("channels") or []
        for c in chans:
            if str(c.get("service") or "").lower() in ("twitter", "x"):
                return c["id"], c.get("name") or ""
    return None, ""

def text_for(it, update):
    head = " ".join(str(it.get("headline") or "").split()).replace("—", ",").replace("–", "-")
    head = ("Update: " if update else "") + head
    link = f'{SITE}/story/{it["id"]}/?ref=x'
    room = LIMIT - LINK_LEN - 2
    if len(head) > room:
        head = head[:room - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return f"{head}\n\n{link}", head

def main():
    dry = "--dry-run" in sys.argv
    key = os.environ.get("BUFFER_API_KEY", "").strip()
    now = datetime.now(timezone.utc)
    st = fbpage.load(STATE, {})
    posts = st.get("posts") or []
    ed = fbpage.load(os.path.join(ROOT, "edition.json"), {})
    today = fbpage.uk_now(now).strftime("%Y-%m-%d")
    n_today = sum(1 for p in posts if fbpage.uk_now(fbpage.parse_t(p["at"]) or now).strftime("%Y-%m-%d") == today)
    if n_today >= MAX_PER_DAY:
        print(f"nothing posted: {n_today} posts already today (cap {MAX_PER_DAY})"); return
    pick, why = fbpage.choose(now, posts, ed, ignore_clock=dry)
    if not pick:
        print("nothing posted:", why); return
    it, update = pick
    text, head = text_for(it, update)
    if dry:
        print("would post:\n" + text); return
    if not key:
        print("nothing posted: BUFFER_API_KEY is not set"); return
    if not st.get("channelId"):
        cid, name = find_channel(key)
        if not cid:
            print("nothing posted: no X channel found in Buffer"); sys.exit(1)
        st["channelId"], st["channelName"] = cid, name
    due = (now + timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    # values are written into the query as JSON strings (valid GraphQL string literals), so no variable types to get wrong
    q = """mutation {
      createPost(input: {text: %s, channelId: %s, schedulingType: automatic, mode: customScheduled, dueAt: %s}) {
        __typename
        ... on PostActionSuccess { post { id dueAt } }
        ... on MutationError { message }
      } }""" % (json.dumps(text), json.dumps(st["channelId"]), json.dumps(due))
    res = (gql(key, q).get("createPost")) or {}
    post = res.get("post")
    if not post:
        print("Buffer did not accept the post:", res.get("__typename"), res.get("message")); sys.exit(1)
    posts.append({"id": it["id"], "headline": " ".join(str(it.get("headline") or "").split()),
                  "at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "update": bool(update), "buffer": post.get("id")})
    st["posts"] = posts[-500:]
    json.dump(st, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("sent to Buffer for X:", head)

if __name__ == "__main__":
    main()
