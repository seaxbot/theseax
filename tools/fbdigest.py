#!/usr/bin/env python3
"""Scheduled round-up posts for The Seax Facebook Page (owner's request, 12 Nov 2026).

Four slots a day, UK time (weekday / Saturday and Sunday):
  morning  07:15 / 08:00  top 5 stories to start the day
  lunch    12:30 / 12:00  the top story
  commute  17:00 / 17:30  top 3 stories for the journey home
  night    21:00 / 21:00  News at 9: the top 10 stories of the day you may have missed

Runs on GitHub Actions (.github/workflows/fb-digest.yml) with the Page access token in the repository secret
FB_PAGE_TOKEN, the same token tools/fbpage.py uses. Posts ONLY as The Seax Page: it asks Facebook who the token
belongs to and stops unless the answer is the Page named "The Seax" (owner's hard rule). Standard library only.

  python3 tools/fbdigest.py --slot auto       post whichever slot is due now (within 50 minutes of its time), once a day
  python3 tools/fbdigest.py --slot night --dry-run   print the post without posting
  python3 tools/fbdigest.py --slot lunch --choose    print JSON {message, link} for posting another way (e.g. the browser)
Every round-up leads with a different story and picture from the earlier ones that day (owner's rule, 15 Nov 2026).
State: data/fb-posted.json (shared with tools/fbpage.py, so the hourly poster waits after a round-up).
"""
import json, os, re, sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fbpage

ROOT, SITE = fbpage.ROOT, fbpage.SITE
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
SLOTS = {
    # "weekend" = Saturday and Sunday time (owner's choice, 13 Nov 2026: 08:00, 12:00, 17:30, 21:00)
    "morning": {"at": (7, 15), "weekend": (8, 0), "n": 5, "hours": 24},
    "lunch":   {"at": (12, 30), "weekend": (12, 0), "n": 1, "hours": 24},
    "commute": {"at": (17, 0), "weekend": (17, 30), "n": 3, "hours": 18},
    "night":   {"at": (21, 0), "weekend": (21, 0), "n": 10, "hours": 0},   # 0 = since midnight UK time today
}
NUM = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

def latest_t(it):
    ts = [t for t in (fbpage.parse_t(it.get("time")), fbpage.parse_t(it.get("updated")), fbpage.parse_t(it.get("headlineAt"))) if t]
    return max(ts) if ts else None

def pick(ed, now, slot, full=False):
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
    ranked = [it for _, it in out]
    return ranked if full else ranked[:cfg["n"]]

# ---------- a different lead every post (owner's rule, 15 Nov 2026) ----------
# Three round-ups on 15 Nov led with the same story and the same picture. Every round-up must now lead with a
# different story from the earlier round-ups that day (and from the one before it, so the morning post does not
# repeat last night's). The picture on the post must be different too. A story only keeps the lead twice when it
# is major breaking news (breaking, weight 9 or 10) or nothing else is available, and then the post goes out
# with the story's map instead of its photo.
def og_image_of(sid):
    try:
        m = re.search(r'property="og:image" content="([^"]+)"', open(os.path.join(ROOT, "story", sid, "index.html"), encoding="utf-8").read())
        return m.group(1).split("?")[0] if m else ""
    except OSError:
        return ""

def used_leads(posts, uk):
    """Lead story ids and pictures of today's round-ups, plus the round-up before this one whatever the day."""
    digests = [p for p in posts if str(p.get("id", "")).startswith("digest-")]
    mine = [p for p in digests if str(p.get("id", "")).endswith(f"{uk:%Y-%m-%d}")] + digests[-1:]
    return {p["lead"] for p in mine if p.get("lead")}, {p["image"] for p in mine if p.get("image") and p["image"] != "map"}

def major_breaking(it):
    try:
        return it.get("breaking") is True and float(it.get("weight") or 0) >= 9
    except (TypeError, ValueError):
        return False

# Owner's rule (20 Nov 2026): every Facebook post must carry a real picture, never just the static Seax topic card
# (the plain branded cards for News, Court, Environment and so on). A story whose only picture is one of those cards
# can still lead a round-up, but then the post is a photo post with the story's Essex map, as for a repeated lead.
STATIC_OG = {"default", "news", "community", "council", "court", "business", "education", "environment", "feature", "fire", "football",
             "health", "history", "police", "property", "racing", "cricket", "sport", "transport", "weather", "whatson", "briefing", "breaking"}

def real_picture(sid):
    img = og_image_of(sid)
    m = re.search(r"/img/og/([a-z0-9-]+)\.png$", img)
    return bool(img) and not (m and m.group(1) in STATIC_OG)

def order_for_lead(ranked, n, ids, imgs):
    """Returns (items, use_map). The first item is the post's lead and link."""
    if not ranked:
        return [], False
    top = ranked[0]
    ok = lambda it: it["id"] not in ids and og_image_of(it["id"]) not in imgs and real_picture(it["id"])
    if top["id"] in ids and major_breaking(top):
        return ranked[:n], True                       # a major story keeps the lead, with the map as its picture
    if ok(top):
        return ranked[:n], False                      # the top story has not led today and has a real picture
    # look a little way down for a story with its own picture, without promoting a minor story far above its rank
    fresh = next((it for it in ranked[:max(5, min(n, 8))] if ok(it)), None)
    if fresh:
        return ([fresh] + [it for it in ranked if it is not fresh])[:n], False
    other = next((it for it in ranked if it["id"] not in ids), None)
    if other:                                          # a different story with no fresh picture of its own: post its map
        return ([other] + [it for it in ranked if it is not other])[:n], True
    return ranked[:n], True                           # nothing else to lead with: same story, map picture

def map_png(it):
    """The story's Essex map (the same one its page draws) as a PNG for a photo post. None if it cannot be made."""
    import subprocess, shutil, tempfile
    try:
        import build
        svg = build.story_map_svg(it, "#c8102e", aspect=0.525)
        svg = svg.replace("<svg ", '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" ', 1)
        if not shutil.which("rsvg-convert"):          # GitHub's runners do not always have it
            subprocess.run("sudo apt-get install -y -qq librsvg2-bin >/dev/null 2>&1", shell=True, timeout=150)
        d = tempfile.mkdtemp()
        open(os.path.join(d, "m.svg"), "w", encoding="utf-8").write(svg)
        subprocess.run(["rsvg-convert", "-w", "1200", "-h", "630", "-o", os.path.join(d, "m.png"), os.path.join(d, "m.svg")], check=True, timeout=60)
        data = open(os.path.join(d, "m.png"), "rb").read()
        return data if len(data) > 5000 else None
    except Exception as e:
        print("map picture failed:", str(e)[:200])
        return None

def photo_post(page_id, token, msg, png):
    """A photo post on the Page: the picture with the round-up text as its caption."""
    import urllib.request, uuid
    b = uuid.uuid4().hex
    body = b""
    for k, v in (("caption", msg), ("access_token", token)):
        body += f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n'.encode() + v.encode("utf-8") + b"\r\n"
    body += f'--{b}\r\nContent-Disposition: form-data; name="source"; filename="essex-map.png"\r\nContent-Type: image/png\r\n\r\n'.encode() + png + f"\r\n--{b}--\r\n".encode()
    req = urllib.request.Request(f"{fbpage.GRAPH}/{page_id}/photos", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={b}", "User-Agent": "TheSeaxPagePoster/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())

def message(slot, items, now, ed=None):
    uk = fbpage.uk_now(now)
    day = DAYS[uk.weekday()]
    wkend = uk.weekday() >= 5   # wording suits the day (owner's request, 13 Nov 2026)
    one = lambda it: " ".join(str(it.get("headline") or "").split())
    url = lambda it: f"{SITE}/story/{it['id']}/"
    # Saturday fixtures round-up (owner's request, 14 Nov 2026): the 08:00 Saturday post links the sport desk's
    # "who's playing where" story on its own line, so it is not repeated in the numbered list
    fx = None
    if slot == "morning" and uk.weekday() == 5:
        fid = f"s-essex-fixtures-{uk:%Y-%m-%d}"
        fx = next((x for x in ((ed or {}).get("sport") or {}).get("stories") or [] if isinstance(x, dict) and x.get("id") == fid), None)
        if fx and not os.path.exists(os.path.join(ROOT, "story", fid, "index.html")):
            fx = None
        items = [it for it in items if it.get("id") != fid]
    if slot == "lunch":
        it = items[0]
        summ = " ".join(str(it.get("summary") or "").split())
        lines = [f"🥪 {day + ' lunchtime' if wkend else 'Lunchtime'} in Essex: the big story", "", one(it)] + (["", summ] if summ else []) + ["", f"Read more: {url(it)}"]
    else:
        top = {"morning": f"☀️ Morning Essex: {len(items)} stories to start your {day}",
               "commute": {4: f"🚆 Heading home for the weekend? {len(items)} Essex stories for the journey:",
                           5: f"🌆 Your Saturday evening catch-up: {len(items)} Essex stories from today",
                           6: f"🌆 Your Sunday evening catch-up: {len(items)} Essex stories before the week ahead"}.get(
                               uk.weekday(), f"🚆 Heading home? {len(items)} Essex stories for the journey:"),
               "night": f"🌙 News at 9: the {len(items)} Essex stories you may have missed {'this ' + day if wkend else 'today'}"}[slot]
        lines = [top, ""]
        if slot == "morning":
            # owner's wording, 12 Nov 2026: greeting and weather first, then the stories
            wx = weather_line(ed, uk)
            lines = ([f"Good morning Essex: weather today {wx[0]}"] + wx[1:] if wx else ["Good morning Essex!"]) + \
                    ["", {0: f"Here are {len(items)} stories to start the week across the county:",
                     4: f"Here are {len(items)} stories making news across the county this Friday morning:",
                     5: f"Here are {len(items)} stories to start your Saturday across the county:",
                     6: f"Here are {len(items)} stories for your Sunday morning across the county:"}.get(
                         uk.weekday(), f"Here are {len(items)} stories making news this morning across the county:"), ""]
        for i, it in enumerate(items):
            lines += [f"{NUM[i]} {one(it)}", url(it), ""]
        if fx:
            lines += ["⚽ Who's playing where today: every Essex fixture and kick-off time", url(fx), ""]
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
    out = [f"{WX_EMOJI.get(d.get('icon'), '') + ' ' if WX_EMOJI.get(d.get('icon')) else ''}{desc + ', ' if desc else ''}high of {d.get('hi')}C{rain}, "
           f"falling to {d.get('lo')}C tonight.{' 🥶' if isinstance(d.get('lo'), (int, float)) and d['lo'] < 2 else ''}"]
    for warn in (w.get("warnings") or [])[:1]:
        out.append(f"⚠️ {warn}")
    return out

def due_slot(now, posts):
    """The slot due now (up to 100 minutes late, as GitHub's scheduler can run late) and not yet posted today."""
    uk = fbpage.uk_now(now)
    for name, cfg in SLOTS.items():
        h, m = cfg["weekend"] if uk.weekday() >= 5 and "weekend" in cfg else cfg["at"]
        start = uk.replace(hour=h, minute=m, second=0, microsecond=0)
        if start <= uk < start + timedelta(minutes=100) and not posted_today(posts, name, uk):
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
    if slot == "check":  # confirm the token works and belongs to The Seax Page, without posting anything
        token = os.environ.get("FB_PAGE_TOKEN", "").strip()
        if not token:
            print("CHECK: FB_PAGE_TOKEN is not set"); sys.exit(1)
        who = fbpage.graph("me", {"fields": "id,name", "access_token": token})
        ok = who.get("name") == fbpage.PAGE_NAME
        print(f"CHECK: token belongs to {who.get('name')!r} ({'OK, The Seax Page' if ok else 'NOT The Seax Page'})")
        sys.exit(0 if ok else 1)
    if slot == "auto":
        slot = due_slot(now, posts)
        if not slot:
            print("no round-up due now"); return
    if slot not in SLOTS:
        print(f"unknown slot {slot}"); sys.exit(2)
    ed = fbpage.load(os.path.join(ROOT, "edition.json"), {})
    uk = fbpage.uk_now(now)
    ids, imgs = used_leads(posts, uk)
    items, use_map = order_for_lead(pick(ed, now, slot, full=True), SLOTS[slot]["n"], ids, imgs)
    if not items:
        print(json.dumps({"none": "no stories"}) if "--choose" in a else "no stories to post"); return
    msg, link = message(slot, items, now, ed), f"{SITE}/story/{items[0]['id']}/"
    if "--choose" in a:
        print(json.dumps({"slot": slot, "message": msg, "link": link, "ids": [x["id"] for x in items], "map": use_map}, ensure_ascii=False)); return
    if "--dry-run" in a:
        print(msg + "\n\n[" + ("map picture, story: " if use_map else "link card: ") + link + "]"); return
    if posted_today(posts, slot, uk):
        print(f"{slot} round-up already posted today"); return
    token = os.environ.get("FB_PAGE_TOKEN", "").strip()
    if not token:
        print("FB_PAGE_TOKEN is not set: nothing posted"); return
    who = fbpage.graph("me", {"fields": "id,name", "access_token": token})
    if who.get("name") != fbpage.PAGE_NAME:
        print(f"STOP: the token belongs to {who.get('name')!r}, not the {fbpage.PAGE_NAME} Page. Nothing posted."); sys.exit(1)
    res, image = None, og_image_of(items[0]["id"])
    if use_map:
        png = map_png(items[0])
        if png:
            try:
                res, image = photo_post(who["id"], token, msg, png), "map"
            except Exception as e:
                print("map photo post failed, posting the link instead:", str(e)[:200])
    if not res:
        res = fbpage.graph(f"{who['id']}/feed", data={"message": msg, "link": link, "access_token": token})
    fbpage.record(st, f"digest-{slot}-{uk:%Y-%m-%d}", msg.split("\n")[0], False, res.get("post_id") or res.get("id"), now)
    st["posts"][-1].update({"lead": items[0]["id"], "image": image})   # so later round-ups lead with something else
    json.dump(st, open(fbpage.STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("POSTED", slot, res.get("post_id") or res.get("id"), "lead:", items[0]["id"], "picture:", image)

if __name__ == "__main__":
    main()
