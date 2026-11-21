#!/usr/bin/env python3
"""Post The Seax's stories to The Seax X account through Buffer (owner's request, 21 Nov 2026; widened the same day).

Runs on GitHub Actions every 30 minutes (.github/workflows/x-buffer.yml). Uses Buffer's GraphQL API
(https://api.buffer.com) with a personal API key stored as the repository secret BUFFER_API_KEY. Standard library
only. Without the key it does nothing.

Built to stay inside Buffer's FREE plan:
  - Free allows 10 scheduled posts per channel at one time. This script never queues ahead: each run sends at most
    ONE post, timed two minutes from now, so there is only ever one post waiting in Buffer.
  - Free API limits are 100 requests per 15 minutes, 250 per day and 3,000 per 30 days. A post is one request;
    a run with nothing to post makes none. At MAX_PER_DAY = 30 that is at most about 900 requests a month.
  - Free allows one threaded post, so every post is a single tweet.

What goes out (one per run, at most MAX_PER_DAY a day, at least GAP_MIN minutes apart, quiet 23:00 to 06:30 UK):
  1. Fixed daily and weekly tweets, when due:
       morning   06:30 to 08:59, the lead story and today's weather
       sport     the day's Essex results (weekends from 17:30, weekdays from 21:45), if there are any
       events    Fridays 12:00 to 14:59, what's on this weekend
       checker   Sundays 10:00 to 12:59, the crime checker (while its story is still on the site)
  2. Otherwise the best story not yet tweeted: ANY story with its own page, biggest first (breaking, lead, front,
     weight, freshness), from the last 8 hours (3 hours for travel, weather and other time-sensitive items).
  3. One "Update:" for breaking news or the lead when its headline has changed.
  4. A second tweet, worded from the summary, for the lead or an Exclusive at least 6 hours after the first.
  Court, police and crime stories get ONE tweet with the plain headline and nothing more (replies cannot be
  turned off on X): no Update, no second tweet.
State: data/x-posted.json. Use --dry-run to see what would be posted without posting.
"""
import json, os, re, sys, urllib.request
from datetime import timedelta, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fbpage  # shared helpers: load, parse_t, uk_now, legal_story

ROOT = fbpage.ROOT
SITE = fbpage.SITE
API = "https://api.buffer.com"
STATE = os.path.join(ROOT, "data", "x-posted.json")
MAX_PER_DAY = 30
GAP_MIN = 25
WINDOW_H = 8
URGENT_H = 3
AGAIN_H = 6
LINK_LEN = 23   # X counts every link as 23 characters
LIMIT = 280
ROOM = LIMIT - LINK_LEN - 2
URGENT_RX = re.compile(r"\b(road|lane|closure|closed|crash|collision|delays?|queues?|traffic|rail|trains?|flood\w*|weather warning|yellow warning|amber warning|power cut|evacuat\w*)\b", re.I)
CHECKER_ID = "essex-recorded-crime-september-2026-police-data"

def clean(s):
    return " ".join(str(s or "").split()).replace("—", ",").replace("–", "-")

def fit(s, room=ROOM):
    s = clean(s)
    if len(s) <= room:
        return s
    return s[:room - 1].rsplit(" ", 1)[0].rstrip(",;:.") + "…"

def gql(key, query):
    body = json.dumps({"query": query}).encode()
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

def has_page(sid):
    return os.path.exists(os.path.join(ROOT, "story", sid, "index.html"))

def all_stories(ed):
    out = []
    for sec in ("stories", "official", "courts", "community"):
        out += [it for it in ed.get(sec) or [] if isinstance(it, dict) and it.get("id") and it.get("headline")]
    out += [it for it in (ed.get("sport") or {}).get("stories") or [] if isinstance(it, dict) and it.get("id") and it.get("headline")]
    seen, uniq = set(), []
    for it in out:
        if it["id"] not in seen:
            seen.add(it["id"]); uniq.append(it)
    return uniq

def story_time(it):
    ts = [t for t in (fbpage.parse_t(it.get("time")), fbpage.parse_t(it.get("updated")), fbpage.parse_t(it.get("headlineAt"))) if t]
    return max(ts) if ts else None

def link(sid):
    return f"{SITE}/story/{sid}/?ref=x"

# ---------- fixed daily and weekly tweets ----------
def fixed(ed, now, uk, done_today, stories):
    """(kind, text, link, id) for a fixed tweet that is due now and not yet sent today, or None."""
    hm = uk.hour * 60 + uk.minute
    today = uk.strftime("%Y-%m-%d")
    lead_id = (ed.get("lead") or {}).get("id")
    lead = next((s for s in stories if s["id"] == lead_id), None)
    if "morning" not in done_today and 6 * 60 + 30 <= hm < 9 * 60 and lead and has_page(lead["id"]):
        w = next((d for d in (ed.get("weather") or {}).get("days") or [] if d.get("date") == today), None)
        wx = f' Weather: {str(w.get("desc") or "").lower()}, high {w.get("hi")}C, low {w.get("lo")}C.' if w and w.get("desc") else ""
        head = clean(lead["headline"])
        text = f"Good morning Essex. Today's top story: {head}.{wx}"
        if len(text) > ROOM:
            text = f"Good morning Essex. {fit(head, ROOM - 20 - len(wx))}.{wx}"
        return "morning", fit(text), link(lead["id"]), lead["id"]
    weekend = uk.weekday() >= 5
    if "sport" not in done_today and hm >= ((17 * 60 + 30) if weekend else (21 * 60 + 45)):
        res = []
        for r in (ed.get("sport") or {}).get("results") or []:
            t = fbpage.parse_t(r.get("date"))
            if t and fbpage.uk_now(t).strftime("%Y-%m-%d") == today and str(r.get("status") or "").upper() in ("FT", "AET", "PENS", "RESULT") \
                    and r.get("hs") is not None and r.get("as") is not None:
                res.append(f'{clean(r["home"])} {r["hs"]}-{r["as"]} {clean(r["away"])}')
        if res:
            text = "Today's Essex results: "
            used = 0
            for i, r in enumerate(res):
                add = r + ("; " if i < len(res) - 1 else "")
                if len(text) + len(add) > ROOM - 12:
                    break
                text += add; used += 1
            text = text.rstrip("; ")
            if used < len(res):
                text += f" and {len(res) - used} more"
            return "sport", text, f"{SITE}/?ref=x#sport", ""
    if "events" not in done_today and uk.weekday() == 4 and 12 * 60 <= hm < 15 * 60:
        sat = (uk + timedelta(days=1)).date(); sun = (uk + timedelta(days=2)).date()
        names = []
        for e in ed.get("events") or []:
            s, en = fbpage.parse_t(e.get("start")), fbpage.parse_t(e.get("end") or e.get("start"))
            if s and en and s.date() <= sun and en.date() >= sat and (en - s) <= timedelta(days=4):
                names.append(clean(e.get("title")))
        if len(names) >= 2:
            text = "What's on in Essex this weekend: "
            used = 0
            for i, n in enumerate(names):
                add = n + "; "
                if len(text) + len(add) > ROOM - 12:
                    break
                text += add; used += 1
            text = text.rstrip("; ")
            if used < len(names):
                text += f" and {len(names) - used} more"
            if used:
                return "events", text, f"{SITE}/?ref=x#events", ""
    if "checker" not in done_today and uk.weekday() == 6 and 10 * 60 <= hm < 13 * 60 and has_page(CHECKER_ID) \
            and any(s["id"] == CHECKER_ID for s in stories):
        return "checker", "How does crime where you live compare with a year ago? Look up any of Essex's 56 police neighbourhoods, crime by crime, with The Seax crime checker.", \
               f"{SITE}/story/{CHECKER_ID}/?ref=x#check", CHECKER_ID
    return None

# ---------- stories ----------
def pick_story(ed, now, posts, stories):
    """(kind, text, link, id, headline) for the best story tweet now, or None."""
    lead_id = (ed.get("lead") or {}).get("id")
    front = set(ed.get("front") or [])
    done = {}
    for p in posts:
        if p.get("id"):
            done.setdefault(p["id"], []).append(p)
    fresh, later = [], []
    for it in stories:
        t = story_time(it)
        if not t or t > now + timedelta(minutes=10) or not has_page(it["id"]):
            continue
        head = clean(it["headline"])
        if re.search(r"\b(ends?|ended|lifted|cleared|expired?)\b", head, re.I) and re.search(r"\bwarning\b", head, re.I):
            continue
        age = now - t
        legal = fbpage.legal_story(it)
        lead, onfront, brk = it["id"] == lead_id, it["id"] in front, bool(it.get("breaking"))
        w = float(it.get("weight") or 0)
        score = (1000 if brk else 0) + (300 if lead else 0) + (120 if onfront else 0) + w * 20 - age.total_seconds() / 360
        prev = done.get(it["id"])
        urgent = bool(URGENT_RX.search(head)) or str(it.get("tag") or "").lower() in ("transport", "travel", "weather")
        if not prev:
            if age <= timedelta(hours=URGENT_H if urgent else WINDOW_H):
                fresh.append((score, "story", head, it))
            continue
        if legal:
            continue  # one plain tweet only
        kinds = {p.get("kind") or ("update" if p.get("update") else "story") for p in prev}
        since = now - (fbpage.parse_t(prev[-1]["at"]) or now)
        if "update" not in kinds and head != clean(prev[-1].get("headline")) and (brk or lead) and age <= timedelta(hours=WINDOW_H) \
                and since >= timedelta(hours=1):
            later.append((score + 50, "update", "Update: " + head, it))
        elif "again" not in kinds and (lead or it.get("exclusive")) and timedelta(hours=AGAIN_H) <= since and age <= timedelta(hours=36) \
                and clean(it.get("summary")) and clean(it.get("summary")) != head:
            later.append((score - 200, "again", clean(it["summary"]), it))
    pool = sorted(fresh + later, key=lambda x: -x[0])
    if not pool:
        return None
    _, kind, text, it = pool[0]
    return kind, fit(text), link(it["id"]), it["id"], clean(it["headline"])

def main():
    dry = "--dry-run" in sys.argv
    key = os.environ.get("BUFFER_API_KEY", "").strip()
    now = datetime.now(timezone.utc)
    uk = fbpage.uk_now(now)
    st = fbpage.load(STATE, {})
    posts = st.get("posts") or []
    ed = fbpage.load(os.path.join(ROOT, "edition.json"), {})
    today = uk.strftime("%Y-%m-%d")
    todays = [p for p in posts if fbpage.uk_now(fbpage.parse_t(p["at"]) or now).strftime("%Y-%m-%d") == today]
    if not dry:
        if uk.hour >= 23 or uk.hour < 6 or (uk.hour == 6 and uk.minute < 30):
            print(f"nothing posted: quiet hours ({uk:%H:%M} UK)"); return
        if len(todays) >= MAX_PER_DAY:
            print(f"nothing posted: {len(todays)} posts already today (cap {MAX_PER_DAY})"); return
        last = fbpage.parse_t(posts[-1]["at"]) if posts else None
        if last and now - last < timedelta(minutes=GAP_MIN):
            print(f"nothing posted: last post {int((now - last).total_seconds() // 60)} min ago"); return
    stories = all_stories(ed)
    done_today = {p.get("kind") for p in todays}
    f = fixed(ed, now, uk, done_today, stories)
    if f:
        kind, text, url, sid = f; headline = text
    else:
        s = pick_story(ed, now, posts, stories)
        if not s:
            print("nothing posted: nothing new to tweet"); return
        kind, text, url, sid, headline = s
    tweet = f"{text}\n\n{url}"
    if dry:
        print(f"would post ({kind}):\n{tweet}"); return
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
      } }""" % (json.dumps(tweet), json.dumps(st["channelId"]), json.dumps(due))
    res = (gql(key, q).get("createPost")) or {}
    post = res.get("post")
    if not post:
        print("Buffer did not accept the post:", res.get("__typename"), res.get("message")); sys.exit(1)
    posts.append({"id": sid, "kind": kind, "headline": headline, "at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "update": kind == "update", "buffer": post.get("id")})
    st["posts"] = posts[-800:]
    json.dump(st, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"sent to Buffer for X ({kind}):", text)

if __name__ == "__main__":
    main()
