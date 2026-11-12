#!/usr/bin/env python3
"""Scheduled round-up posts for The Seax Facebook Page (owner's request, 12 Nov 2026).

Four slots a day, UK time:
  morning  07:15  top 5 stories to start the day
  lunch    12:30  the top story
  commute  17:00  top 3 stories for the journey home
  night    21:00  News at 9: the top 10 stories of the day you may have missed

Runs on GitHub Actions (.github/workflows/fb-digest.yml) with the Page access token in the repository secret
FB_PAGE_TOKEN, the same token tools/fbpage.py uses. Posts ONLY as The Seax Page: it asks Facebook who the token
belongs to and stops unless the answer is the Page named "The Seax" (owner's hard rule). Standard library only.

  python3 tools/fbdigest.py --slot auto       post whichever slot is due now (within 50 minutes of its time), once a day
  python3 tools/fbdigest.py --slot night --dry-run   print the post without posting
  python3 tools/fbdigest.py --slot lunch --choose    print JSON {message, link} for posting another way (e.g. the browser)
State: data/fb-posted.json (shared with tools/fbpage.py, so the hourly poster waits after a round-up).
"""
import json, os, re, sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fbpage

ROOT, SITE = fbpage.ROOT, fbpage.SITE
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
SLOTS = {
    "morning": {"at": (7, 15), "n": 5, "hours": 24},
    "lunch":   {"at": (12, 30), "n": 1, "hours": 24},
    "commute": {"at": (17, 0), "n": 3, "hours": 18},
    "night":   {"at": (21, 0), "n": 10, "hours": 0},   # 0 = since midnight UK time today
}
NUM = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

def latest_t(it):
    ts = [t for t in (fbpage.parse_t(it.get("time")), fbpage.parse_t(it.get("updated")), fbpage.parse_t(it.get("headlineAt"))) if t]
    return max(ts) if ts else None

def pick(ed, now, slot):
    """Top stories for the slot: the lead, then the front-page picks, then the rest by weight and freshness."""
    cfg = SLOTS[slot]
    uk = fbpage.uk_now(now)
    since = now - timedelta(hours=cfg["hours"]) if cfg["hours"] else now - (uk - uk.replace(hour=0, minute=0, second=0, microsecond=0))
    lead = (ed.get("lead") or {}).get("id")
    front = list(ed.get("front") or [])
    pool = []
    for sec in ("stories", "official", "courts", "community"):
        pool += [x for x in ed.get(sec) or [] if isinstance(x, dict)]
    pool += [x for x in (ed.get("sport") or {}).get("stories") or [] if isinstance(x, dict)]
    seen, out = set(), []
    for it in pool:
        if not it.get("id") or it["id"] in seen or not it.get("headline"):
            continue
        seen.add(it["id"])
        # News at 9 counts only stories first published or genuinely updated today, not reworded headlines
        t = latest_t(it) if cfg["hours"] else max([x for x in (fbpage.parse_t(it.get("time")), fbpage.parse_t(it.get("updated"))) if x] or [None], default=None)
        if not t or t < since or t > now + timedelta(minutes=10):
            continue
        if it.get("summaryOnly") or it.get("linkOnly"):
            continue  # link-only outlets: never promoted on social media
        if not os.path.exists(os.path.join(ROOT, "story", it["id"], "index.html")):
            continue
        w = float(it.get("weight") or 3)
        rank = (1000 if it["id"] == lead else 0) + (500 - front.index(it["id"]) * 10 if it["id"] in front else 0) \
               + (200 if it.get("breaking") else 0) + w * 20 - (now - t).total_seconds() / 1800
        out.append((rank, it))
    out.sort(key=lambda x: -x[0])
    return [it for _, it in out[:cfg["n"]]]

def message(slot, items, now, ed=None):
    uk = fbpage.uk_now(now)
    day = DAYS[uk.weekday()]
    one = lambda it: " ".join(str(it.get("headline") or "").split())
    url = lambda it: f"{SITE}/story/{it['id']}/"
    if slot == "lunch":
        it = items[0]
        summ = " ".join(str(it.get("summary") or "").split())
        lines = ["🥪 Lunchtime in Essex: the big story", "", one(it)] + (["", summ] if summ else []) + ["", f"Read more: {url(it)}"]
    else:
        top = {"morning": f"☀️ Morning Essex: {len(items)} stories to start your {day}",
               "commute": f"🚆 Heading home? {len(items)} Essex stories for the journey:",
               "night": f"🌙 News at 9: the {len(items)} Essex stories you may have missed today"}[slot]
        lines = [top, ""]
        if slot == "morning":
            # owner's wording, 12 Nov 2026: greeting and weather first, then the stories
            wx = weather_line(ed, uk)
            lines = ([f"☀️ Good morning Essex: weather today {wx[0]}"] + wx[1:] if wx else ["☀️ Good morning Essex!"]) + \
                    ["", f"Here are {len(items)} stories making news this morning across the county:", ""]
        for i, it in enumerate(items):
            lines += [f"{NUM[i]} {one(it)}", url(it), ""]
        lines += ["Every story, all day: theseax.com"]
    return "\n".join(lines).replace("—", ",")

WX_EMOJI = {"sun": "☀️", "partly": "⛅", "cloud": "☁️", "rain": "🌧️", "shower": "🌦️", "fog": "🌫️", "wind": "💨", "storm": "⛈️"}

def weather_line(ed, uk):
    """Morning Essex opens with the weather today and tonight (owner's choice, 12 Nov 2026), from the edition's Met Office forecast."""
    w = (ed or {}).get("weather") or {}
    d = next((x for x in w.get("days") or [] if x.get("date") == f"{uk:%Y-%m-%d}"), None)
    if not d:
        return []
    desc = str(d.get("desc") or "").strip().lower()
    rain = f", {d.get('rain')}% chance of rain" if str(d.get("rain", "")).isdigit() and int(d["rain"]) >= 20 else ""
    out = [f"{desc + ', ' if desc else ''}high of {d.get('hi')}C{rain}, "
           f"falling to {d.get('lo')}C tonight.{' 🥶' if isinstance(d.get('lo'), (int, float)) and d['lo'] < 2 else ''}"]
    for warn in (w.get("warnings") or [])[:1]:
        out.append(f"⚠️ {warn}")
    return out

def due_slot(now, posts):
    """The slot due now (up to 50 minutes late, as GitHub's scheduler can run late) and not yet posted today."""
    uk = fbpage.uk_now(now)
    for name, cfg in SLOTS.items():
        h, m = cfg["at"]
        start = uk.replace(hour=h, minute=m, second=0, microsecond=0)
        if start <= uk < start + timedelta(minutes=50) and not posted_today(posts, name, uk):
            return name
    return None

def posted_today(posts, slot, uk):
    return any(p.get("id") == f"digest-{slot}-{uk:%Y-%m-%d}" for p in posts)

def main():
    a = sys.argv
    slot = a[a.index("--slot") + 1] if "--slot" in a else "auto"
    now = datetime.now(timezone.utc)
    st = fbpage.load(fbpage.STATE, {"posts": []})
    posts = st.get("posts") or []
    if slot == "auto":
        slot = due_slot(now, posts)
        if not slot:
            print("no round-up due now"); return
    if slot not in SLOTS:
        print(f"unknown slot {slot}"); sys.exit(2)
    ed = fbpage.load(os.path.join(ROOT, "edition.json"), {})
    items = pick(ed, now, slot)
    if not items:
        print(json.dumps({"none": "no stories"}) if "--choose" in a else "no stories to post"); return
    msg, link = message(slot, items, now, ed), f"{SITE}/story/{items[0]['id']}/"
    if "--choose" in a:
        print(json.dumps({"slot": slot, "message": msg, "link": link, "ids": [x["id"] for x in items]}, ensure_ascii=False)); return
    if "--dry-run" in a:
        print(msg + "\n\n[link card: " + link + "]"); return
    uk = fbpage.uk_now(now)
    if posted_today(posts, slot, uk):
        print(f"{slot} round-up already posted today"); return
    token = os.environ.get("FB_PAGE_TOKEN", "").strip()
    if not token:
        print("FB_PAGE_TOKEN is not set: nothing posted"); return
    who = fbpage.graph("me", {"fields": "id,name", "access_token": token})
    if who.get("name") != fbpage.PAGE_NAME:
        print(f"STOP: the token belongs to {who.get('name')!r}, not the {fbpage.PAGE_NAME} Page. Nothing posted."); sys.exit(1)
    res = fbpage.graph(f"{who['id']}/feed", data={"message": msg, "link": link, "access_token": token})
    fbpage.record(st, f"digest-{slot}-{uk:%Y-%m-%d}", msg.split("\n")[0], False, res.get("id"), now)
    print("POSTED", slot, res.get("id"))

if __name__ == "__main__":
    main()
