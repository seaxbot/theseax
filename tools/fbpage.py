#!/usr/bin/env python3
"""Post The Seax's most significant story to The Seax Facebook Page, at most once an hour (owner's request, Nov 2026).

Runs on GitHub Actions every hour (.github/workflows/fb-page.yml). Uses the Facebook Graph API with a Page access
token stored as the repository secret FB_PAGE_TOKEN. Standard library only.

Rules:
  - Posts ONLY as The Seax Page. Before posting it asks Facebook who the token belongs to and stops unless the
    answer is the Page named "The Seax" (owner's hard rule: never post from James's personal account).
  - At most one post per run and never within 50 minutes of the last post.
  - Quiet hours 23:00 to 06:30 UK time: nothing is posted.
  - Picks from stories changed in the last 3 hours that have a story page on the site: breaking first, then the
    lead, then the front-page picks, then weight and freshness. Stories below weight 5 are only posted if they
    are breaking, the lead or on the front.
  - Never posts the same story twice, except as an "Update:" when its headline has changed and it still
    qualifies (weight 6 or more, breaking or the lead), and then only once more.
  - The post is the headline, the summary and the story link; Facebook shows the story's picture from the link.
State: data/fb-posted.json. Use --dry-run to see what would be posted without posting.
"""
import json, os, sys, urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = "https://theseax.com"
GRAPH = "https://graph.facebook.com/v21.0"
STATE = os.path.join(ROOT, "data", "fb-posted.json")
PAGE_NAME = "The Seax"
WINDOW_H = 3
GAP_MIN = 50

def load(p, d):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return d

def parse_t(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None

def uk_now(now):
    # UK time without extra libraries: BST from the last Sunday of March 01:00 UTC to the last Sunday of October 01:00 UTC
    y = now.year
    def last_sunday(m):
        d = datetime(y, m + 1, 1, tzinfo=timezone.utc) - timedelta(days=1) if m < 12 else datetime(y, 12, 31, tzinfo=timezone.utc)
        return d - timedelta(days=(d.weekday() + 1) % 7)
    start = last_sunday(3).replace(hour=1)
    end = last_sunday(10).replace(hour=1)
    return now + timedelta(hours=1) if start <= now < end else now

def candidates(ed, now):
    lead_id = (ed.get("lead") or {}).get("id")
    front = set(ed.get("front") or [])
    pool = []
    for sec in ("stories", "official", "courts", "community"):
        for it in ed.get(sec) or []:
            if isinstance(it, dict) and it.get("id") and it.get("headline"):
                pool.append(it)
    for it in (ed.get("sport") or {}).get("stories") or []:
        if isinstance(it, dict) and it.get("id") and it.get("headline"):
            pool.append(it)
    out = []
    for it in pool:
        ts = [t for t in (parse_t(it.get("time")), parse_t(it.get("updated")), parse_t(it.get("headlineAt"))) if t]
        if not ts:
            continue
        t = max(ts)
        if now - t > timedelta(hours=WINDOW_H) or t > now + timedelta(minutes=10):
            continue
        if not os.path.exists(os.path.join(ROOT, "story", it["id"], "index.html")):
            continue
        w = float(it.get("weight") or 0)
        lead, onfront, brk = it["id"] == lead_id, it["id"] in front, bool(it.get("breaking"))
        if w < 5 and not (lead or onfront or brk):
            continue
        score = (1000 if brk else 0) + (300 if lead else 0) + (120 if onfront else 0) + w * 20 - (now - t).total_seconds() / 360
        out.append((score, it, lead, brk))
    out.sort(key=lambda x: -x[0])
    return out

def message(it, update):
    head = " ".join(str(it.get("headline") or "").split())
    summ = " ".join(str(it.get("summary") or "").split())
    place = str(it.get("place") or "").strip()
    first = ("Update: " if update else "") + head
    lines = [first]
    if summ:
        lines += ["", summ]
    if place:
        lines += ["", f"📍 {place}"]
    return "\n".join(lines).replace("—", ",")  # house style: no em dashes

def graph(path, params=None, data=None):
    url = f"{GRAPH}/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers={"User-Agent": "TheSeaxPagePoster/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def choose(now, posts, ed, ignore_clock=False):
    """The story to post now, or (None, reason)."""
    uk = uk_now(now)
    if not ignore_clock and (uk.hour >= 23 or uk.hour < 6 or (uk.hour == 6 and uk.minute < 30)):
        return None, f"quiet hours ({uk:%H:%M} UK)"
    last = parse_t(posts[-1]["at"]) if posts else None
    if not ignore_clock and last and now - last < timedelta(minutes=GAP_MIN):
        return None, f"last post {int((now - last).total_seconds() // 60)} min ago"
    done = {}
    for p in posts:
        done.setdefault(p["id"], []).append(p)
    for score, it, lead, brk in candidates(ed, now):
        prev = done.get(it["id"])
        if not prev:
            return (it, False), ""
        head = " ".join(str(it.get("headline") or "").split())
        if len(prev) < 2 and head != prev[-1]["headline"] and (float(it.get("weight") or 0) >= 6 or lead or brk):
            return (it, True), ""
    return None, "nothing new and significant"

def record(st, it_id, headline, update, fb_id, now):
    posts = st.get("posts") or []
    posts.append({"id": it_id, "headline": " ".join(str(headline or "").split()), "at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "update": bool(update), "fb": fb_id})
    st["posts"] = posts[-500:]
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(st, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def main():
    # Browser route (owner's choice, 9 Nov 2026): Claude posts through Chrome as The Seax.
    #   --choose            print JSON {"id","message","link","update","headline"} or {"none": reason}
    #   --record ID [--update]   note that ID was posted now
    if "--choose" in sys.argv:
        now = datetime.now(timezone.utc)
        st = load(STATE, {"posts": []})
        pick, why = choose(now, st.get("posts") or [], load(os.path.join(ROOT, "edition.json"), {}))
        if not pick:
            print(json.dumps({"none": why})); return
        it, update = pick
        print(json.dumps({"id": it["id"], "headline": " ".join(str(it.get("headline") or "").split()), "update": update,
                          "message": message(it, update), "link": f"{SITE}/story/{it['id']}/"}, ensure_ascii=False)); return
    if "--record" in sys.argv:
        i = sys.argv.index("--record")
        sid = sys.argv[i + 1]
        ed = load(os.path.join(ROOT, "edition.json"), {})
        head = next((x.get("headline") for sec in ("stories", "official", "courts", "community") for x in ed.get(sec) or [] if isinstance(x, dict) and x.get("id") == sid),
                    next((x.get("headline") for x in (ed.get("sport") or {}).get("stories") or [] if x.get("id") == sid), ""))
        st = load(STATE, {"posts": []})
        record(st, sid, head, "--update" in sys.argv, "browser", datetime.now(timezone.utc))
        print("recorded", sid); return
    dry = "--dry-run" in sys.argv
    now = datetime.now(timezone.utc)
    st = load(STATE, {"posts": []})
    posts = st.get("posts") or []
    uk = uk_now(now)
    if not dry and (uk.hour >= 23 or uk.hour < 6 or (uk.hour == 6 and uk.minute < 30)):
        print(f"quiet hours ({uk:%H:%M} UK): nothing posted"); return
    last = parse_t(posts[-1]["at"]) if posts else None
    if not dry and last and now - last < timedelta(minutes=GAP_MIN):
        print(f"last post {int((now - last).total_seconds() // 60)} min ago: waiting"); return
    ed = load(os.path.join(ROOT, "edition.json"), {})
    done = {}
    for p in posts:
        done.setdefault(p["id"], []).append(p)
    pick = None
    for score, it, lead, brk in candidates(ed, now):
        prev = done.get(it["id"])
        if not prev:
            pick = (it, False); break
        head = " ".join(str(it.get("headline") or "").split())
        if len(prev) < 2 and head != prev[-1]["headline"] and (float(it.get("weight") or 0) >= 6 or lead or brk):
            pick = (it, True); break
    if not pick:
        print("nothing new and significant to post"); return
    it, update = pick
    link = f"{SITE}/story/{it['id']}/"
    msg = message(it, update)
    print(("DRY RUN, would post:\n" if dry else "posting:\n") + msg + "\n" + link)
    if dry:
        return
    token = os.environ.get("FB_PAGE_TOKEN", "").strip()
    if not token:
        print("FB_PAGE_TOKEN is not set: nothing posted"); return
    who = graph("me", {"fields": "id,name", "access_token": token})
    if who.get("name") != PAGE_NAME:
        print(f"STOP: the token belongs to {who.get('name')!r}, not the {PAGE_NAME} Page. Nothing posted."); sys.exit(1)
    res = graph(f"{who['id']}/feed", data={"message": msg, "link": link, "access_token": token})
    posts.append({"id": it["id"], "headline": " ".join(str(it.get("headline") or "").split()), "at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "update": update, "fb": res.get("id")})
    st["posts"] = posts[-500:]
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(st, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("POSTED", res.get("id"))

if __name__ == "__main__":
    main()
