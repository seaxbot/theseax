#!/usr/bin/env python3
"""Build The Seax's static pages from edition.json.

Run from anywhere:  python3 tools/build.py   (options: --briefing-now, --out DIR)

Writes, inside the repository:
  story/<id>/index.html    one page per story, kept after the story leaves the edition
  data/archive.json        index of every story page ever built
  about/index.html         about, contact and corrections page
  briefing/<date>/         the daily "Essex at 7" briefing (made once a day, 06:30 to 12:00 UK)
  briefing/index.html      latest briefing
  briefing.xml             RSS feed of briefings (for RSS-to-email)
  feed.xml                 RSS feed of the latest stories
  sitemap.xml, news-sitemap.xml
  index.html               only the config block between <!--seax-config--> markers

Uses only the Python standard library. Never touches edition.json.
"""
import json, os, re, sys, html, shutil, argparse
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from email.utils import format_datetime
from urllib.parse import urlparse, quote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UK = ZoneInfo("Europe/London")
CFG = json.load(open(os.path.join(ROOT, "tools", "site.json"), encoding="utf-8"))
SITE = CFG["site"].rstrip("/")
NOW = datetime.now(timezone.utc)

E = lambda s: html.escape(str(s if s is not None else ""), quote=True)

# ---------- helpers ----------
ICON_COLOUR = {
    "news": "#3a3f4b", "police": "#1d4e9e", "court": "#3c3a7a", "crime": "#1d4e9e", "appeal": "#1d4e9e", "tribute": "#55596a",
    "council": "#1b2a44", "fire": "#b3122b", "ambulance": "#1d7448", "health": "#1d7448", "business": "#8a6414", "retail": "#8a6414",
    "halloween": "#a8501a", "history": "#6b5638", "football": "#0f5b84", "racing": "#0f5b84", "cricket": "#0f5b84", "sport": "#0f5b84",
    "community": "#1a6e6b", "charity": "#1a6e6b", "volunteering": "#1a6e6b", "wildlife": "#3a6b34", "environment": "#2b6e60",
    "transport": "#344559", "weather": "#356f9f", "whatson": "#8f1546", "property": "#7a5228", "education": "#3a4a8f",
}
CARD_FOR = {
    "police": "police", "crime": "police", "appeal": "police", "court": "court", "council": "council", "politics": "council",
    "fire": "fire", "ambulance": "health", "health": "health", "business": "business", "retail": "business", "property": "property",
    "transport": "transport", "weather": "weather", "community": "community", "charity": "community", "volunteering": "community",
    "tribute": "community", "wildlife": "environment", "environment": "environment", "whatson": "whatson", "halloween": "whatson",
    "history": "history", "education": "education", "football": "football", "cricket": "cricket", "racing": "racing", "sport": "sport",
}
TAG_ICON = {"police": "police", "crime": "police", "court": "court", "appeal": "appeal", "tribute": "tribute", "council": "council",
            "politics": "council", "environment": "environment", "business": "business", "health": "health", "transport": "transport",
            "property": "property", "education": "education", "history": "history", "what's on": "whatson", "halloween": "halloween",
            "community": "community", "charity": "charity", "volunteering": "volunteering", "wildlife": "wildlife", "fire": "fire",
            "ambulance": "ambulance", "football": "football", "cricket": "cricket", "racing": "racing", "sport": "sport",
            "ice hockey": "sport", "rugby": "sport"}
SECTION_LABEL = {"news": "News", "sport": "Sport", "official": "Public Services", "courts": "Courts",
                 "community": "Community", "features": "Features", "councilwatch": "Council Watch"}

def icon_of(it, sec):
    if sec == "councilwatch":
        return "council"
    ic = str(it.get("icon") or "").lower()
    if ic in ICON_COLOUR:
        return ic
    tag = str(it.get("tag") or "").lower()
    if tag in TAG_ICON:
        return TAG_ICON[tag]
    if sec == "sport":
        return "sport"
    return "news"

ROAD_OG = [("a130", re.compile(r"\bA130\b")), ("a127", re.compile(r"\bA127\b")),
           ("a13", re.compile(r"\bA13\b")), ("a12", re.compile(r"\bA12\b"))]  # stories about these roads share their road sign

def road_of(it):
    """The first road named in the headline, else the summary, else the place (same rule as the page)."""
    for t in (it.get("headline"), it.get("summary"), it.get("place")):
        hits = [(m.start(), key) for key, rx in ROAD_OG for m in [rx.search(str(t or ""))] if m]
        if hits:
            return min(hits)[1]
    return None

# hospital stories share the owner's hospital photo (img/topics/hospital.jpg; share card img/og/hospital.jpg).
# Same rule as the page: a health story that mentions a hospital or A&E, or any story (not police, crime,
# court, appeal, tribute or fire) with a hospital or A&E in its headline.
HOSPITAL_RX = re.compile(r"\bhospitals?\b|\bA&E\b", re.I)
HOSPITAL_SKIP = {"police", "crime", "court", "appeal", "tribute", "fire"}
# police, crime and appeal stories share the owner's blue lights photo (img/topics/bluelights.jpg; share card
# img/og/bluelights.jpg). Same rule as the page's isPoliceStory: icon police, crime or appeal, or tag Police unless
# the icon is court, tribute, fire or ambulance.
POLICE_ICONS = {"police", "crime", "appeal"}
POLICE_TAG_SKIP = {"court", "tribute", "fire", "ambulance"}
# stories about police policy and politics keep the map (same as the page's POLICE_POLICY_RX)
POLICE_POLICY_RX = re.compile(r"\b(commissioners?|PFCC|mergers?|mega[ -]force|budgets?|precept|council tax|HMICFRS|inspections?|inspectorate)\b", re.I)
POLICE_PHOTOS = ["bluelights", "bluelights-2"]  # img/topics/<name>.jpg and share cards img/og/<name>.jpg, rotated like the page
POLICE_PICK = {}
OG_JPG = {"hospital", "bluelights", "bluelights-2", "fireengine"}
LIBRARY_PHOTOS = POLICE_PHOTOS + ["fireengine"]  # owner's library photos shown on story pages

def og_path(card):
    return f"/img/og/{card}.jpg" if card in OG_JPG else f"/img/og/{card}.png"

def is_hospital(it, sec):
    if sec == "sport":
        return False
    ic = icon_of(it, sec)
    if ic in HOSPITAL_SKIP:
        return False
    head_ = str(it.get("headline") or "")
    both = head_ + " " + str(it.get("summary") or "")
    return bool(HOSPITAL_RX.search(head_) or (ic == "health" and HOSPITAL_RX.search(both)))

def is_police(it, sec):
    if sec == "sport":
        return False
    if POLICE_POLICY_RX.search(str(it.get("headline") or "")):
        return False
    ic = icon_of(it, sec)
    if ic in POLICE_ICONS:
        return True
    return str(it.get("tag") or "").lower() == "police" and ic not in POLICE_TAG_SKIP

def pick_police(ed):
    """Same rotation as the page's policePhotoSrc: newest first across stories and official items, a variant
    from the id's hash, never the same as the police story just before it."""
    POLICE_PICK.clear()
    def tm(x):
        ts = [t.timestamp() for t in (parse_t(x.get("updated")), parse_t(x.get("time"))) if t]
        return max(ts) if ts else 0
    items = [(("news" if i < len(ed.get("stories") or []) else "official"), x)
             for i, x in enumerate((ed.get("stories") or []) + (ed.get("official") or [])) if isinstance(x, dict) and x.get("id")]
    items.sort(key=lambda p: -tm(p[1]))
    n, prev = len(POLICE_PHOTOS), -1
    for sec, x in items:
        if not is_police(x, sec):
            continue
        h = 0
        for c in str(x["id"]):
            h = (h * 31 + ord(c)) & 0xFFFFFFFF
        v = h % n
        if v == prev:
            v = (v + 1) % n
        POLICE_PICK[x["id"]] = v
        prev = v

def police_photo(it):
    return POLICE_PHOTOS[POLICE_PICK.get(it.get("id"), 0) % len(POLICE_PHOTOS)]

def is_fire(it, sec):
    """Fire stories use the owner's fire engine photo (same rule as the page's isFireStory)."""
    if sec == "sport" or POLICE_POLICY_RX.search(str(it.get("headline") or "")):
        return False
    return icon_of(it, sec) == "fire" or str(it.get("tag") or "").lower() == "fire"

def card_of(it, sec):
    road = road_of(it)
    if sec != "sport" and road and os.path.exists(os.path.join(ROOT, "img", "og", road + ".png")):
        return road
    if is_hospital(it, sec) and os.path.exists(os.path.join(ROOT, "img", "og", "hospital.jpg")):
        return "hospital"
    if is_police(it, sec) and os.path.exists(os.path.join(ROOT, "img", "og", police_photo(it) + ".jpg")):
        return police_photo(it)
    if is_fire(it, sec) and os.path.exists(os.path.join(ROOT, "img", "og", "fireengine.jpg")):
        return "fireengine"
    if sec == "councilwatch":
        return "council"
    if sec == "features":
        return "feature"
    return CARD_FOR.get(icon_of(it, sec), "news")

def parse_t(s):
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None

def iso(d):
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if d else ""

def uk_long(d):
    if not d:
        return ""
    u = d.astimezone(UK)
    return f"{u.strftime('%A')} {u.day} {u.strftime('%B %Y')}, {u.strftime('%H:%M')}"

def uk_day(d):
    u = d.astimezone(UK)
    return f"{u.strftime('%A')} {u.day} {u.strftime('%B')}"

def host(u):
    try:
        h = urlparse(u).netloc.lower()
        return h[4:] if h.startswith("www.") else h
    except Exception:
        return ""

def safe_url(u):
    u = str(u or "")
    return u if re.match(r"^https?://", u, re.I) else ""

def slug_ok(i):
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,120}", str(i or "")))

def trunc(s, n):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"

def write(path, text):
    full = os.path.join(ROOT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    old = open(full, encoding="utf-8").read() if os.path.exists(full) else None
    if old != text:
        with open(full, "w", encoding="utf-8") as f:
            f.write(text)
        return True
    return False

# ---------- shared page chrome ----------
SHIELD = '<img class="shield" src="/favicon.svg" width="40" height="47" alt="">'

def analytics():
    code = CFG.get("goatcounter") or ""
    if not code:
        return ""
    return f'<script data-goatcounter="https://{E(code)}.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>'

def head(title, desc, canonical, og_image, og_type="website", extra=""):
    return f"""<!DOCTYPE html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(title)}</title>
<meta name="description" content="{E(desc)}">
<link rel="canonical" href="{E(canonical)}">
<meta property="og:site_name" content="The Seax">
<meta property="og:locale" content="en_GB">
<meta property="og:type" content="{og_type}">
<meta property="og:title" content="{E(title.replace(' · The Seax', ''))}">
<meta property="og:description" content="{E(desc)}">
<meta property="og:url" content="{E(canonical)}">
<meta property="og:image" content="{SITE}{og_image if og_image.startswith("/") else og_path(og_image)}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="The Seax, Essex News, Sport, Life.">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{E(title.replace(' · The Seax', ''))}">
<meta name="twitter:description" content="{E(desc)}">
<meta name="twitter:image" content="{SITE}{og_image if og_image.startswith("/") else og_path(og_image)}">
<meta name="theme-color" content="#c8102e">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/icons/apple-touch-icon.png">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="alternate" type="application/rss+xml" title="The Seax: latest Essex news" href="/feed.xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Schibsted+Grotesk:wght@500..900&family=Inter:opsz,wght@14..32,400..700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/assets/page.css">
{extra}{analytics()}
</head>
<body>
<header class="mast"><div class="wrap">
  <a class="brand" href="/" aria-label="The Seax front page">{SHIELD}<span><b>The <em>Seax</em></b><small>Essex News, Sport, Life.</small></span></a>
  <a class="home" href="/">Front page</a>
</div></header>
<nav class="sec"><div class="wrap">
  <a href="/#news">News</a><a href="/#sport">Sport</a><a href="/#desk">Public Services</a><a href="/council-watch/">Council Watch</a><a href="/#community">Community</a><a href="/#whatson">What's On</a><a href="/briefing/">Morning briefing</a><a href="/about/">About</a>
</div></nav>
"""

def newsletter_box():
    form = CFG.get("newsletterForm") or ""
    link = CFG.get("newsletterLink") or ""
    if link and not form:
        return f"""<section class="nl"><div><h3>{E(CFG.get('newsletterName','Essex at 7'))}</h3><p>The morning briefing: the lead, the stories that matter, weather, travel and last night's results, free in your inbox every morning.</p></div>
<div class="nl-go"><a href="{E(link)}" target="_blank" rel="noopener">Get it free by email</a></div></section>"""
    if not form:
        return ""
    field = CFG.get("newsletterField") or "email"
    return f"""<section class="nl"><div><h3>{E(CFG.get('newsletterName','Essex at 7'))}</h3><p>The morning briefing: the lead, the stories that matter, weather, travel and last night's results, in your inbox before 7.</p></div>
<form action="{E(form)}" method="post" target="_blank"><label class="sr" for="nlE">Email address</label><input id="nlE" type="email" name="{E(field)}" placeholder="Your email address" required><button>Sign me up</button></form></section>"""

def foot():
    mail = CFG["contactEmail"]
    social = []
    if CFG.get("whatsappChannel"):
        social.append(f'<a href="{E(CFG["whatsappChannel"])}">WhatsApp channel</a>')
    if CFG.get("facebookPage"):
        social.append(f'<a href="{E(CFG["facebookPage"])}">Facebook</a>')
    return f"""<footer class="foot"><div class="wrap">
  <p><b>The Seax</b> brings together Essex news, sport and life from trusted local and national sources. Every story links to the original reporting.</p>
  <p><a href="/about/">About The Seax</a> · <a href="/about/#corrections">Corrections</a> · <a href="mailto:{E(mail)}">{E(mail)}</a> · <a href="/briefing/">Morning briefing</a> · <a href="/feed.xml">RSS</a>{' · ' + ' · '.join(social) if social else ''}</p>
</div></footer>
"""

SHARE_JS = """<script>
document.addEventListener("click",function(e){
  var b=e.target.closest("[data-share]"); if(!b) return;
  var url=b.getAttribute("data-url"), title=b.getAttribute("data-title");
  if(b.dataset.share==="native"){ if(navigator.share){ navigator.share({title:title,url:url}).catch(function(){}); e.preventDefault(); } }
  else if(b.dataset.share==="copy"){ e.preventDefault(); try{ navigator.clipboard.writeText(url).then(function(){ b.textContent="Link copied"; setTimeout(function(){ b.textContent="Copy link"; },2500); }); }catch(_){ b.textContent=url; } }
});
if(!navigator.share){ var n=document.querySelector('[data-share="native"]'); if(n) n.style.display="none"; }
</script>"""

def share_bar(url, title):
    t = quote(title + " " + url)
    return f"""<div class="share">
  <button data-share="native" data-url="{E(url)}" data-title="{E(title)}">Share</button>
  <a class="wa" href="https://wa.me/?text={t}" target="_blank" rel="noopener">WhatsApp</a>
  <a href="https://www.facebook.com/sharer/sharer.php?u={quote(url, safe='')}" target="_blank" rel="noopener">Facebook</a>
  <a href="https://x.com/intent/post?url={quote(url, safe='')}&amp;text={quote(title)}" target="_blank" rel="noopener">X</a>
  <button data-share="copy" data-url="{E(url)}" data-title="{E(title)}">Copy link</button>
</div>"""

# ---------- stock photos (tools/photos.py) ----------
try:
    PHOTOS = json.load(open(os.path.join(ROOT, "data", "photos.json"), encoding="utf-8"))
except Exception:
    PHOTOS = {}

def stock_figure(it, sec):
    p = PHOTOS.get(it.get("id")) if sec != "sport" and not it.get("noPhoto") else None
    if not p:
        return ""
    who = f'<a href="{E(p["creatorUrl"])}" target="_blank" rel="noopener">{E(p["creator"])}</a>' if safe_url(p.get("creatorUrl")) else E(p.get("creator"))
    lic = f'<a href="{E(p["licenseUrl"])}" target="_blank" rel="noopener">{E(p["license"])}</a>' if safe_url(p.get("licenseUrl")) else E(p.get("license"))
    src = f' via <a href="{E(p["source"])}" target="_blank" rel="noopener">{E(p.get("provider") or "source")}</a>' if safe_url(p.get("source")) else ""
    return (f'<figure class="stock"><img src="{E(p["file"])}" width="{E(p.get("w") or 1200)}" height="{E(p.get("h") or 800)}" alt="{E("Stock photo: " + (p.get("title") or p.get("keyword") or ""))}" loading="eager">'
            f'<figcaption><b>Stock photo</b>, not the scene of this story. {E(p.get("title") or "")}{" · " if p.get("title") else ""}{who}, {lic}{src}</figcaption></figure>')

# ---------- story pages ----------
def collect(ed):
    out = []
    for sec, items in [("news", ed.get("stories", [])), ("sport", (ed.get("sport") or {}).get("stories", [])),
                       ("official", ed.get("official", [])), ("courts", ed.get("courts", [])),
                       ("community", ed.get("community", [])), ("features", ed.get("features", [])),
                       ("councilwatch", ed.get("councilwatch", []))]:
        for it in items or []:
            if isinstance(it, dict) and slug_ok(it.get("id")) and it.get("headline"):
                out.append((sec, it))
    return out

def story_page(sec, it, more):
    sid = it["id"]
    url = f"{SITE}/story/{sid}/"
    title = str(it["headline"]).strip()
    summary = str(it.get("summary") or "").strip()
    desc = trunc(summary or title, 200)
    icon = icon_of(it, sec)
    colour = ICON_COLOUR.get(icon, "#3a3f4b")
    card = card_of(it, sec)
    t = parse_t(it.get("time"))
    up = parse_t(it.get("updated"))
    place = it.get("place") or "Essex"
    src = it.get("source") or ""
    surl = safe_url(it.get("url"))
    also = [a for a in (it.get("also") or []) if isinstance(a, dict) and safe_url(a.get("url"))]
    kicker = "Feature" if sec == "features" else "Council Watch" if sec == "councilwatch" else (it.get("tag") or SECTION_LABEL.get(sec, "News"))
    ld = {
        "@context": "https://schema.org", "@type": "NewsArticle",
        "headline": trunc(title, 110), "description": desc,
        "mainEntityOfPage": url, "url": url,
        "image": [SITE + og_path(card)],
        "articleSection": SECTION_LABEL.get(sec, "News"),
        "author": {"@type": "Organization", "name": "The Seax", "url": SITE + "/"},
        "publisher": {"@type": "Organization", "name": "The Seax", "url": SITE + "/",
                      "logo": {"@type": "ImageObject", "url": f"{SITE}/icons/icon-512.png", "width": 512, "height": 512}},
        "contentLocation": {"@type": "Place", "name": f"{place}, Essex"},
    }
    if t:
        ld["datePublished"] = iso(t)
        ld["dateModified"] = iso(up or t)
    if surl:
        ld["isBasedOn"] = surl
    extra = f'<meta property="article:section" content="{E(SECTION_LABEL.get(sec, "News"))}">\n'
    if t:
        extra += f'<meta property="article:published_time" content="{iso(t)}">\n<meta property="article:modified_time" content="{iso(up or t)}">\n'
    extra += '<script type="application/ld+json">' + json.dumps(ld, ensure_ascii=False).replace("</", "<\\/") + "</script>\n"
    body = it.get("body") if isinstance(it.get("body"), list) else []
    points = it.get("points") if isinstance(it.get("points"), list) else []
    meta = [f"<b>{E(place)}</b>"]
    if t:
        meta.append(f'<time datetime="{iso(t)}">{E(uk_long(t))}</time>')
    if up and t and up > t + timedelta(minutes=5):
        meta.append(f'<span>Updated <time datetime="{iso(up)}">{E(uk_long(up))}</time></span>')
    if src and sec != "councilwatch":
        meta.append(f"<span>Reported by {E(src)}</span>")
    if sec == "councilwatch":
        meta.append("<span>Original reporting from council papers</span>")
    org = ""
    if it.get("org") and sec in ("official", "courts", "community"):
        org = f'<div class="org">{E(SECTION_LABEL[sec])} · {E(it["org"])}</div>'
    readfull = ""
    if surl:
        readfull = f"""<div class="readfull"><div><div class="k">Read the full story</div><div class="src">{E(src or host(surl))}</div></div>
<a class="go" href="{E(surl)}" target="_blank" rel="noopener">Open at {E(host(surl) or src)} ↗</a></div>"""
    if sec == "councilwatch":
        readfull = cw_record_box(it)
    also_html = ""
    if also:
        also_html = '<h2>Also reported by</h2><ul class="also">' + "".join(
            f'<li><a href="{E(a["url"])}" target="_blank" rel="noopener"><b>{E(a.get("name") or host(a["url"]))}</b> <span>{E(host(a["url"]))} ↗</span></a></li>' for a in also) + "</ul>"
    mail = CFG["contactEmail"]
    corr = f'mailto:{mail}?subject={quote("Correction: " + title)}&body={quote("Page: " + url)}'
    more_html = "".join(
        f'<a class="rel" href="/story/{E(m["id"])}/" style="--c:{ICON_COLOUR.get(icon_of(m, s), "#3a3f4b")}"><i></i><b>{E(m["headline"])}</b><span>{E(m.get("place") or "Essex")}</span></a>'
        for s, m in more)
    fig = stock_figure(it, sec)
    if not fig and card in LIBRARY_PHOTOS:
        fig = (f'<figure class="stock"><img src="/img/topics/{card}.jpg?v=1" width="1200" height="655" '
               f'alt="Library photo: {"a fire engine" if card == "fireengine" else "police car blue lights"}" loading="eager">'
               '<figcaption><b>Library image</b>, not the scene of this story.</figcaption></figure>')
    og_img = PHOTOS[sid]["file"] if fig and card not in [k for k, _ in ROAD_OG] + ["hospital"] + LIBRARY_PHOTOS else card
    if fig:
        ld["image"] = [SITE + og_img if og_img.startswith("/") else ld["image"][0]]
        extra = extra.replace(SITE + og_path(card), ld["image"][0])
    return head(f"{title} · The Seax", desc, url, og_img, "article", extra) + f"""<main class="wrap story">
<article style="--c:{colour}">
  <div class="kick"><span>{E(kicker)}</span><span>{E(place)}</span></div>
  {org}{cw_badge(it) if sec == "councilwatch" else ""}
  <h1>{E(title)}</h1>
  {f'<p class="standfirst">{E(summary)}</p>' if summary else ''}
  <div class="meta">{' <span class="dot">·</span> '.join(meta)}</div>
  {share_bar(url, title)}
  {fig}
  {''.join(f'<p>{E(p)}</p>' for p in body if str(p).strip())}
  {('<h2>Key points</h2><ul class="points">' + ''.join(f'<li>{E(p)}</li>' for p in points) + '</ul>') if points else ''}
  {readfull}
  {also_html}
  {cw_note(corr) if sec == "councilwatch" else f'<p class="note">This is a summary written by The Seax. The original reporting, quotes and images belong to {E(src or "the outlet named above")}{" and the other outlets listed" if also else ""}. <a href="{E(corr)}">Spotted a mistake? Tell us</a>.</p>'}
</article>
<aside>
  <h3>More from Essex</h3>
  {more_html}
  <a class="front" href="/">Go to the front page →</a>
</aside>
</main>
{newsletter_box()}
{foot()}{SHARE_JS}
</body></html>
"""


# ---------- Council Watch ----------
CW_STAGE = {"decided": "Decided", "upcoming": "Coming up", "proposed": "Proposed", "held": "Discussed", "update": "Update"}

def cw_badge(it):
    stage = CW_STAGE.get(str(it.get("stage") or "").lower(), "")
    bits = [f'<a href="/council-watch/{E(it.get("council") or "")}/">{E(it.get("councilName") or "Essex council")}</a>' if it.get("council") else E(it.get("councilName") or "")]
    if it.get("meeting"):
        bits.append(E(it["meeting"]))
    return (f'<div class="org cw"><b>Council Watch</b> · {" · ".join(b for b in bits if b)}'
            + (f' <span class="cw-stage cw-{E(str(it.get("stage")).lower())}">{E(stage)}</span>' if stage else "") + "</div>")

def cw_record_box(it):
    docs = [d for d in (it.get("docs") or []) if isinstance(d, dict) and safe_url(d.get("url"))]
    murl = safe_url(it.get("meetingUrl"))
    if not docs and not murl:
        return ""
    rows = "".join(
        f'<li><a href="{E(d["url"])}" target="_blank" rel="noopener"><b>{E(d.get("title") or "Council document")}</b>'
        f'<span>{("page " + E(d["page"]) + " · ") if d.get("page") else ""}{E(host(d["url"]))} ↗</span></a></li>' for d in docs)
    meet = (f'<li><a href="{E(murl)}" target="_blank" rel="noopener"><b>Meeting page: {E(it.get("meeting") or "agenda and minutes")}</b>'
            f'<span>{E(host(murl))} ↗</span></a></li>') if murl else ""
    return f'<h2>From the public record</h2><ul class="also cw-docs">{rows}{meet}</ul>'

def cw_note(corr):
    return ('<p class="note">Council Watch is original reporting by The Seax from public council papers: agendas, reports, decisions and minutes. '
            'It is written with the help of AI from the documents linked above, and every fact comes from them. Councils sometimes change '
            'decisions after a meeting, so check the minutes for the final word. '
            f'<a href="{E(corr)}">Spotted a mistake? Tell us</a>. <a href="/council-watch/">How Council Watch works</a>.</p>')

def cw_load(name):
    p = os.path.join(ROOT, "data", "councilwatch", name)
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}

def cw_councils(ed):
    names = {}
    for cid, rec in (cw_load("status.json").get("councils") or {}).items():
        names[cid] = rec.get("name") or cid
    for it in ed.get("councilwatch") or []:
        if it.get("council"):
            names.setdefault(it["council"], it.get("councilName") or it["council"])
    return names

def cw_card(sid, rec):
    t = parse_t(rec.get("t"))
    return (f'<a class="cw-row" href="/story/{E(sid)}/"><span class="cw-c">{E(rec.get("councilName") or "")}</span>'
            f'<b>{E(rec["h"])}</b><span class="cw-m">{E(rec.get("place") or "")}{(" · " + E(uk_day(t))) if t else ""}</span></a>')

def cw_meet_rows(meets):
    out = []
    for m in meets:
        d = parse_t(m.get("date") + "T12:00:00Z") if m.get("date") else None
        items = "".join(f"<li>{E(x)}</li>" for x in (m.get("items") or [])[:4])
        out.append(f'<li class="cw-meet"><a href="{E(safe_url(m.get("url")) or "#")}" target="_blank" rel="noopener">'
                   f'<span class="cw-d">{E(uk_day(d)) if d else ""}{(" · " + E(m["time"])) if m.get("time") else ""}</span>'
                   f'<b>{E(m.get("councilName") or "")}: {E(m.get("committee") or "")}</b></a>{("<ul>" + items + "</ul>") if items else ""}</li>')
    return "".join(out)

def cw_pages(ed, archive):
    """/council-watch/ hub and one page per council. Returns the list of (url, lastmod)."""
    names = cw_councils(ed)
    cal = (cw_load("calendar.json").get("meetings") or [])
    status = cw_load("status.json").get("councils") or {}
    live = {it["id"]: it for it in (ed.get("councilwatch") or []) if isinstance(it, dict) and it.get("id")}
    recs = sorted([(sid, r) for sid, r in archive.items() if r.get("sec") == "councilwatch"],
                  key=lambda kv: kv[1].get("t") or kv[1].get("first") or "", reverse=True)
    for sid, r in recs:
        if sid in live:
            r["councilName"] = live[sid].get("councilName") or r.get("councilName")
    pages = []
    upcoming = [m for m in cal if m.get("date", "") >= NOW.astimezone(UK).date().isoformat()]
    cover = []
    for cid, nm in sorted(names.items(), key=lambda kv: kv[1]):
        st = (status.get(cid) or {}).get("state", "")
        how = {"ok": "papers read automatically", "quiet": "papers read automatically", "blocked": "checked by our desk (site limits automated reading)",
               "unreachable": "checked by our desk", "manual": "checked by our desk", "refused": "checked by our desk (site asks automated readers to stay away)"}.get(st, "")
        n = sum(1 for _, r in recs if r.get("council") == cid)
        cover.append(f'<li><a href="/council-watch/{E(cid)}/">{E(nm)}</a><span>{E(how)}{(" · " + str(n) + (" story" if n == 1 else " stories")) if n else ""}</span></li>')
    url = f"{SITE}/council-watch/"
    desc = "Original reporting from every Essex council's public papers: what was decided, what is coming up, and what it means for you."
    body = f"""<main class="wrap prose cw-hub">
<div class="kick"><span>Council Watch</span><span>Essex</span></div>
<h1>Council Watch</h1>
<p class="standfirst">{E(desc)}</p>
<h2>Latest from Council Watch</h2>
<div class="cw-list">{"".join(cw_card(sid, r) for sid, r in recs[:40]) or '<p>The first Council Watch stories are on their way.</p>'}</div>
<h2>Coming up at your councils</h2>
<ul class="cw-meets">{cw_meet_rows(upcoming[:30]) or '<li>No upcoming meetings found yet.</li>'}</ul>
<h2>Councils we watch</h2>
<ul class="cw-cover">{"".join(cover)}</ul>
<h2 id="how">How Council Watch works</h2>
<p>Essex has fifteen principal councils: Essex County Council, Southend, Thurrock and twelve district, borough and city councils. Each publishes agendas, reports, decisions and minutes that few people have time to read. Council Watch reads them for you.</p>
<p>Twice a day an automated collector visits each council's public meetings website, politely and within the rules each site publishes, and lists the meetings, agenda items and reports. It ranks items by how much they are likely to matter to residents: money, services, homes, planning, closures, consultations and decisions. Our desk then writes short stories from the most important papers, with the help of AI, and links every story to the exact documents and pages it comes from.</p>
<p>Council Watch only reports what the council papers say. It does not report private or exempt business, and it does not name members of the public who appear in council papers. Where a council's website limits automated reading, our desk checks it by hand instead.</p>
<p>Spotted a mistake, or work for an Essex council and want to point us at something? Email <a href="mailto:{E(CFG['contactEmail'])}">{E(CFG['contactEmail'])}</a>.</p>
</main>"""
    changed = write("council-watch/index.html", head("Council Watch: what Essex councils are deciding · The Seax", desc, url, "council") + body + newsletter_box() + foot() + "</body></html>\n")
    pages.append((url, NOW.date().isoformat()))
    for cid, nm in names.items():
        mine = [(sid, r) for sid, r in recs if r.get("council") == cid]
        meets = [m for m in upcoming if m.get("council") == cid]
        u = f"{SITE}/council-watch/{cid}/"
        d2 = f"What {nm} is deciding: Council Watch stories from its public papers, and its upcoming meetings."
        page = f"""<main class="wrap prose cw-hub">
<div class="kick"><span><a href="/council-watch/">Council Watch</a></span><span>{E(nm)}</span></div>
<h1>{E(nm)}</h1>
<p class="standfirst">{E(d2)}</p>
<h2>Latest</h2>
<div class="cw-list">{"".join(cw_card(sid, r) for sid, r in mine[:40]) or '<p>No Council Watch stories for this council yet.</p>'}</div>
<h2>Coming up</h2>
<ul class="cw-meets">{cw_meet_rows(meets[:20]) or '<li>No upcoming meetings found.</li>'}</ul>
<p><a href="/council-watch/#how">How Council Watch works</a></p>
</main>"""
        changed += write(f"council-watch/{cid}/index.html", head(f"{nm}: Council Watch · The Seax", d2, u, "council") + page + newsletter_box() + foot() + "</body></html>\n")
        pages.append((u, (mine[0][1].get("t") or NOW.isoformat())[:10] if mine else None))
    return pages, changed

# ---------- about ----------
def photo_credits():
    """Credits for the town photographs in img/places (all from Wikimedia Commons)."""
    try:
        cr = json.load(open(os.path.join(ROOT, "img", "places", "credits.json"), encoding="utf-8"))
    except Exception:
        return ""
    rows = []
    for k in sorted(cr, key=lambda k: cr[k]["what"]):
        c = cr[k]
        lic = c["license"]
        lic_html = f'<a href="{E(c["licenseUrl"])}" rel="license noopener">{E(lic)}</a>' if c.get("licenseUrl") else E(lic)
        rows.append(f'<li>{E(c["what"])}: photo by {E(c["by"])}, {lic_html}, via <a href="{E(c["source"])}" rel="noopener">Wikimedia Commons</a></li>')
    return ('<h2 id="photo-credits">Photo credits</h2>\n<p>Town photographs on The Seax come from Wikimedia Commons and are used under the licences shown. '
            'They have been resized for the web and are shared under the same terms. Our map artwork is our own.</p>\n<ul class="credits">' + "".join(rows) + "</ul>\n")


def about_page():
    mail = CFG["contactEmail"]
    url = f"{SITE}/about/"
    return head("About The Seax · The Seax", "How The Seax works, who it is for, how to contact us and how we correct mistakes.", url, "default") + f"""<main class="wrap prose">
<h1>About The Seax</h1>
<p class="standfirst">The Seax is a free, independent website for the people of Essex: the county's news, sport, weather, public services, community life and what's on, in one place and updated through the day.</p>

<h2>How The Seax works</h2>
<p>We watch hundreds of trusted sources across Essex and beyond: local newspapers and radio, hyperlocal and independent newsrooms, Essex Police, the fire and ambulance services, councils, the NHS, courts, charities, clubs and venues, plus national and specialist outlets when they report on Essex.</p>
<p>The Seax is produced with the help of AI. Automated research tools gather the latest reports each hour, and AI writes our headlines, summaries and short story pages in our own words, following our editorial rules. Every story names the outlet that reported it and links directly to the original, so you can always read the full report and support the journalists who did the work.</p>
<p>We do not copy articles, take photographs from other publishers, or publish anything that is not reported by a named source or set out in a public document.</p>
<h2 id="council-watch">Council Watch</h2>
<p><a href="/council-watch/">Council Watch</a> is The Seax's own reporting. Twice a day we read the public meeting papers of Essex's councils (agendas, reports, decisions and minutes), politely and within each website's published rules, and write short stories about the decisions that matter to residents. Every Council Watch story links to the council documents, and the pages, it is based on. It is written with the help of AI from those documents only.</p>

<h2>Our editorial rules</h2>
<ul>
<li>Facts only as the source states them. No invented quotes, figures, scores or details.</li>
<li>Crime and court reporting is limited to what police and courts have said. People who have been arrested or charged are presumed innocent, and we do not report anything that could prejudice a trial.</li>
<li>We never name victims of sexual offences or identify children involved in criminal cases.</li>
<li>We do not report suicide or self-harm, or individual inquests.</li>
<li>Advertising is always clearly labelled and never affects what we report.</li>
</ul>

<h2 id="corrections">Corrections and complaints</h2>
<p>We work hard to be accurate, but if we get something wrong we want to put it right quickly. Email <a href="mailto:{E(mail)}?subject=Correction">{E(mail)}</a> with a link to the page and what is wrong. We aim to review every correction request within 24 hours and will correct, clarify or remove content where it is inaccurate, unfair or should not have been published. Significant corrections are noted on the page.</p>
<p>If a story concerns you personally and you would like it reviewed or removed, contact us at the same address.</p>

<h2>Contact</h2>
<p>News tips, corrections, partnership ideas and advertising: <a href="mailto:{E(mail)}">{E(mail)}</a>.</p>
<p>If you run an Essex newsroom, magazine or community site and would like to be featured, or would prefer we did not summarise your work, please get in touch and we will respond promptly.</p>

<h2>Advertising</h2>
<p>The Seax offers Essex businesses brand-safe space alongside local news, sport and what's on, from county-wide takeovers to sponsorship of a single town or section. Email <a href="mailto:{E(mail)}?subject=Advertising%20with%20The%20Seax">{E(mail)}</a> for rates.</p>

<h2>Privacy</h2>
<p>The Seax does not use advertising cookies or track you across other websites. {"We count visits with GoatCounter, a privacy-friendly service that uses no cookies and collects no personal data." if CFG.get("goatcounter") else "We may count visits with a privacy-friendly service that uses no cookies and collects no personal data."} Advertising enquiries sent through our form are delivered to our inbox by FormSubmit and used only to reply to you. Our free morning newsletter is delivered by follow.it; if you sign up, your email address is used only to send it, and every email includes an unsubscribe link.</p>

{photo_credits()}
<h2>Why "The Seax"?</h2>
<p>The seax is the short sword of the Saxons, and three seaxes appear on the arms of Essex: gules, three seaxes fesswise in pale argent, pommels and hilts or. Our badge follows that blazon.</p>
</main>
{newsletter_box()}
{foot()}
</body></html>
"""

# ---------- briefing ----------
def briefing(ed, when):
    day = when.astimezone(UK).date()
    stories = {s["id"]: s for s in ed.get("stories", []) if isinstance(s, dict) and s.get("id")}
    lead = stories.get((ed.get("lead") or {}).get("id"))
    picked = [lead] if lead else []
    for fid in ed.get("front", []) or []:
        if fid in stories and stories[fid] not in picked:
            picked.append(stories[fid])
    cutoff = when - timedelta(hours=30)
    rest = sorted([s for s in stories.values() if s not in picked and (parse_t(s.get("time")) or when) >= cutoff],
                  key=lambda s: (-(s.get("weight") or 0), -(parse_t(s.get("time")) or when).timestamp()))
    picked += rest[: max(0, 8 - len(picked))]
    picked = [p for p in picked if p]
    w = ed.get("weather") or {}
    today = next((d for d in (w.get("days") or []) if d.get("date") == day.isoformat()), None)
    travel = [t for t in (ed.get("travel") or []) if t.get("level") in ("red", "amber")][:4]
    res = []
    for r in (ed.get("sport") or {}).get("results", []) or []:
        rt = parse_t(r.get("date"))
        if rt and rt >= when - timedelta(hours=40) and r.get("hs") is not None and r.get("as") is not None:
            res.append(r)
    res.sort(key=lambda r: r.get("date") or "", reverse=True)
    whats = []
    for ev in (ed.get("events") or []) + (ed.get("culture") or []):
        s, e = parse_t(ev.get("start")), parse_t(ev.get("end"))
        if not s:
            continue
        sd, ed_ = s.astimezone(UK).date(), (e.astimezone(UK).date() if e else s.astimezone(UK).date())
        if sd == day or (e and sd <= day <= ed_ and (ed_ - sd).days <= 3):
            whats.append(ev)
    whats = whats[:5]
    cw = sorted([c for c in (ed.get("councilwatch") or []) if isinstance(c, dict) and c.get("id") and c.get("headline")
                 and (parse_t(c.get("time")) or when - timedelta(days=9)) >= when - timedelta(hours=40)],
                key=lambda c: (-(c.get("weight") or 0), c.get("time") or ""))[:3]
    return {"date": day.isoformat(), "label": uk_day(when), "lead": lead, "stories": picked, "weather": today,
            "warnings": w.get("warnings") or [], "travel": travel, "results": res[:8], "whats": whats, "council": cw}

def briefing_html_inner(b, email=False):
    """The briefing body. email=True gives inline-styled markup for RSS-to-email."""
    S = (lambda css: f' style="{css}"') if email else (lambda css: "")
    out = []
    if b["weather"] or b["warnings"]:
        wx = b["weather"]
        line = f"{E(wx.get('desc', ''))}, high {E(wx.get('hi'))}°C, low {E(wx.get('lo'))}°C" if wx else ""
        if wx and wx.get("rain") is not None:
            line += f", {E(wx.get('rain'))}% chance of rain"
        out.append(f'<h2{S("font:700 18px Arial,sans-serif;margin:22px 0 6px")}>Weather</h2><p{S("margin:0 0 6px")}>{line}.</p>' if line else "")
        for wn in b["warnings"][:3]:
            out.append(f'<p{S("margin:0 0 6px;color:#960a21;font-weight:bold")}>⚠ {E(wn)}</p>')
    if b["stories"]:
        out.append(f'<h2{S("font:700 18px Arial,sans-serif;margin:22px 0 6px")}>The stories that matter</h2>')
        for i, s in enumerate(b["stories"]):
            u = f"{SITE}/story/{s['id']}/"
            big = i == 0
            out.append(
                f'<div class="bs{" lead" if big else ""}"{S("margin:0 0 14px")}><a href="{u}"{S("color:#15161b;text-decoration:none;font:" + ("800 22px" if big else "700 17px") + " Arial,sans-serif")}>{E(s["headline"])}</a>'
                f'<p{S("margin:4px 0 0;color:#3a3a40")}>{E(s.get("place") or "Essex")} · {E(trunc(s.get("summary"), 220))}</p></div>')
    if b.get("council"):
        out.append(f'<h2{S("font:700 18px Arial,sans-serif;margin:22px 0 6px")}>From Council Watch</h2>')
        for c in b["council"]:
            out.append(f'<div class="bs"{S("margin:0 0 12px")}><a href="{SITE}/story/{E(c["id"])}/"{S("color:#15161b;text-decoration:none;font:700 17px Arial,sans-serif")}>{E(c["headline"])}</a>'
                       f'<p{S("margin:4px 0 0;color:#3a3a40")}>{E(c.get("councilName") or "")} · {E(trunc(c.get("summary"), 200))}</p></div>')
    if b["travel"]:
        out.append(f'<h2{S("font:700 18px Arial,sans-serif;margin:22px 0 6px")}>Travel</h2><ul>' + "".join(
            f'<li><a href="{E(safe_url(t.get("url")) or SITE + "/")}">{E(t.get("text"))}</a></li>' for t in b["travel"]) + "</ul>")
    if b["results"]:
        out.append(f'<h2{S("font:700 18px Arial,sans-serif;margin:22px 0 6px")}>Results</h2><ul>' + "".join(
            f'<li>{E(r.get("home"))} {E(r.get("hs"))}-{E(r.get("as"))} {E(r.get("away"))} <span{S("color:#6d675c")}>({E(r.get("comp"))})</span></li>' for r in b["results"]) + "</ul>")
    if b["whats"]:
        out.append(f'<h2{S("font:700 18px Arial,sans-serif;margin:22px 0 6px")}>On today</h2><ul>' + "".join(
            f'<li><a href="{E(safe_url(ev.get("url")) or SITE + "/#whatson")}">{E(ev.get("title"))}</a>, {E(ev.get("where") or ev.get("venue") or "")}{(" · " + E(ev.get("price"))) if ev.get("price") else ""}</li>' for ev in b["whats"]) + "</ul>")
    out.append(f'<p{S("margin:22px 0 0;color:#6d675c;font-size:13px")}>Every story links to the original reporting. More all day at <a href="{SITE}/">theseax.com</a>.</p>')
    return "\n".join(x for x in out if x)

def whatsapp_text(b):
    lines = [f"*Essex at 7* · {b['label']}", ""]
    for s in b["stories"][:6]:
        lines.append(f"• {s['headline']}\n{SITE}/story/{s['id']}/")
    if b["weather"]:
        wx = b["weather"]
        lines += ["", f"Weather: {wx.get('desc', '')}, high {wx.get('hi')}°C"]
    for t in b["travel"][:2]:
        lines.append(f"Travel: {t.get('text')}")
    lines += ["", f"More: {SITE}/"]
    return "\n".join(lines)

def briefing_page(b):
    url = f"{SITE}/briefing/{b['date']}/"
    lead = b["lead"] or (b["stories"][0] if b["stories"] else None)
    title = f"Essex at 7, {b['label']}" + (f": {lead['headline']}" if lead else "")
    desc = "The Seax morning briefing: the Essex stories that matter, weather, travel and results."
    wa = whatsapp_text(b)
    return head(f"{trunc(title, 120)} · The Seax", desc, url, "briefing") + f"""<main class="wrap prose briefing">
<div class="kick" style="--c:#c8102e"><span>Morning briefing</span><span>{E(b['label'])}</span></div>
<h1>Essex at 7</h1>
<p class="standfirst">Good morning. Here is what matters in Essex today.</p>
{share_bar(url, 'Essex at 7, ' + b['label'])}
{briefing_html_inner(b)}
<details class="wa-copy"><summary>Copy this briefing for WhatsApp</summary><textarea readonly rows="14">{E(wa)}</textarea></details>
</main>
{newsletter_box()}
{foot()}{SHARE_JS}
</body></html>
"""

def rss(title, link, desc, self_url, items):
    out = [f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel>
<title>{E(title)}</title>
<link>{E(link)}</link>
<description>{E(desc)}</description>
<language>en-gb</language>
<lastBuildDate>{format_datetime(NOW)}</lastBuildDate>
<atom:link href="{E(self_url)}" rel="self" type="application/rss+xml"/>
<image><url>{SITE}/icons/icon-192.png</url><title>{E(title)}</title><link>{E(link)}</link></image>"""]
    for it in items:
        out.append("<item>" + "".join([
            f"<title>{E(it['title'])}</title>", f"<link>{E(it['link'])}</link>",
            f'<guid isPermaLink="true">{E(it["link"])}</guid>',
            f"<pubDate>{format_datetime(it['date'])}</pubDate>" if it.get("date") else "",
            f"<category>{E(it['cat'])}</category>" if it.get("cat") else "",
            f"<description>{E(it['desc'])}</description>",
            f"<content:encoded><![CDATA[{it['html'].replace(']]>', ']]&gt;')}]]></content:encoded>" if it.get("html") else "",
        ]) + "</item>")
    out.append("</channel>\n</rss>\n")
    return "\n".join(out)

# ---------- index.html config block ----------
def patch_index(latest_briefing):
    p = os.path.join(ROOT, "index.html")
    s = open(p, encoding="utf-8").read()
    conf = {k: CFG.get(k, "") for k in ("site", "contactEmail", "goatcounter", "newsletterForm", "newsletterField", "newsletterLink", "newsletterName", "whatsappChannel", "facebookPage")}
    conf["latestBriefing"] = latest_briefing or ""
    block = "<!--seax-config--><script>window.SEAX_CONFIG = " + json.dumps(conf, ensure_ascii=False) + ";</script>"
    if conf["goatcounter"]:
        block += analytics()
    block += "<!--/seax-config-->"
    new = re.sub(r"<!--seax-config-->.*?<!--/seax-config-->", lambda m: block, s, count=1, flags=re.S)
    if new != s:
        open(p, "w", encoding="utf-8").write(new)
        return True
    return False

# ---------- main ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--briefing-now", action="store_true", help="make today's briefing even outside 06:30-12:00 UK")
    ap.add_argument("--preview-briefing", metavar="FILE", help="write a briefing preview to FILE and change nothing else")
    a = ap.parse_args()

    ed = json.load(open(os.path.join(ROOT, "edition.json"), encoding="utf-8"))
    if a.preview_briefing:
        b = briefing(ed, NOW)
        open(a.preview_briefing, "w", encoding="utf-8").write(briefing_page(b).replace('href="/assets/page.css"', f'href="file://{ROOT}/assets/page.css"'))
        print("preview written"); return

    changed = 0
    arch_path = os.path.join(ROOT, "data", "archive.json")
    archive = json.load(open(arch_path, encoding="utf-8")) if os.path.exists(arch_path) else {}

    # takedowns: ids listed in tools/takedown.txt are removed everywhere
    tk = os.path.join(ROOT, "tools", "takedown.txt")
    takedown = set()
    if os.path.exists(tk):
        takedown = {l.strip() for l in open(tk, encoding="utf-8") if l.strip() and not l.startswith("#")}
    for sid in takedown:
        d = os.path.join(ROOT, "story", sid)
        if os.path.isdir(d):
            shutil.rmtree(d); changed += 1
        archive.pop(sid, None)

    pick_police(ed)
    items = [(s, it) for s, it in collect(ed) if it["id"] not in takedown]
    seen = set()
    top = sorted([(s, it) for s, it in items if s in ("news", "sport")],
                 key=lambda x: (-(x[1].get("weight") or 3), -((parse_t(x[1].get("time")) or NOW).timestamp())))
    for sec, it in items:
        if it["id"] in seen:
            continue
        seen.add(it["id"])
        rel = [x for x in top if x[1]["id"] != it["id"] and set(x[1].get("areas") or []) & (set(it.get("areas") or []) - {"all"})][:3]
        more = rel + [x for x in top if x[1]["id"] != it["id"] and x not in rel][: 6 - len(rel)]
        if sec == "councilwatch":  # other council stories first, and never lead with crime beside a council story
            cws = [x for x in items if x[0] == "councilwatch" and x[1]["id"] != it["id"]][:4]
            calm = [x for x in top if x[1]["id"] != it["id"] and str(x[1].get("tag") or "").lower() not in ("police", "court", "crime")]
            more = cws + calm[: 6 - len(cws)]
        if write(f"story/{it['id']}/index.html", story_page(sec, it, more)):
            changed += 1
        t = parse_t(it.get("time"))
        prev = archive.get(it["id"], {})
        archive[it["id"]] = {
            "h": it["headline"], "sec": sec, "card": card_of(it, sec), "place": it.get("place") or "",
            "t": iso(t) if t else prev.get("t", ""), "u": iso(parse_t(it.get("updated"))) if it.get("updated") else prev.get("u", ""),
            "first": prev.get("first") or iso(NOW), "last": iso(NOW),
        }
        if sec == "councilwatch":
            archive[it["id"]].update({"council": it.get("council") or "", "councilName": it.get("councilName") or "", "cwKey": it.get("cwKey") or ""})

    # about page
    if write("about/index.html", about_page()):
        changed += 1

    # daily briefing
    uk_now = NOW.astimezone(UK)
    day = uk_now.date().isoformat()
    mins = uk_now.hour * 60 + uk_now.minute
    no_brief = os.environ.get("SEAX_NO_BRIEFING") == "1"  # desks other than the newsroom never make the day's briefing
    if not no_brief and (a.briefing_now or 390 <= mins < 720) and not os.path.exists(os.path.join(ROOT, "briefing", day, "index.html")):
        b = briefing(ed, NOW)
        write(f"briefing/{day}/index.html", briefing_page(b))
        bj_path = os.path.join(ROOT, "data", "briefings.json")
        bj = json.load(open(bj_path, encoding="utf-8")) if os.path.exists(bj_path) else []
        lead = b["lead"] or (b["stories"][0] if b["stories"] else None)
        bj = [x for x in bj if x["date"] != day]
        bj.insert(0, {"date": day, "label": b["label"], "made": iso(NOW), "headline": lead["headline"] if lead else "",
                      "html": briefing_html_inner(b, email=True)})
        write("data/briefings.json", json.dumps(bj[:14], ensure_ascii=False, indent=0))
        changed += 1
    bj_path = os.path.join(ROOT, "data", "briefings.json")
    briefs = json.load(open(bj_path, encoding="utf-8")) if os.path.exists(bj_path) else []
    latest = briefs[0]["date"] if briefs else ""
    if latest:
        page = open(os.path.join(ROOT, "briefing", latest, "index.html"), encoding="utf-8").read()
        changed += write("briefing/index.html", page)
    else:
        changed += write("briefing/index.html", head("Essex at 7 · The Seax", "The Seax morning briefing.", f"{SITE}/briefing/", "briefing") +
                         '<main class="wrap prose"><h1>Essex at 7</h1><p class="standfirst">The Seax morning briefing arrives here at about 7am every day: the Essex stories that matter, weather, travel and results.</p><p><a href="/">Read the latest on the front page</a>.</p></main>' + foot() + "</body></html>\n")
    changed += write("briefing.xml", rss("Essex at 7: The Seax morning briefing", f"{SITE}/briefing/",
                                         "The Essex stories that matter, weather, travel and results, every morning.", f"{SITE}/briefing.xml",
                                         [{"title": f"Essex at 7, {x['label']}" + (f": {x['headline']}" if x.get("headline") else ""),
                                           "link": f"{SITE}/briefing/{x['date']}/", "date": parse_t(x["made"]),
                                           "desc": f"The Seax morning briefing for {x['label']}.", "html": x["html"]} for x in briefs]))

    # archive file
    changed += write("data/archive.json", json.dumps(archive, ensure_ascii=False, sort_keys=True, indent=0))

    # Council Watch hub and council pages
    cw_urls, cw_changed = cw_pages(ed, archive)
    changed += cw_changed

    # RSS of latest stories
    feed_items = []
    for sec, it in sorted([x for x in items if x[0] in ("news", "sport", "courts", "official", "community", "features", "councilwatch")],
                          key=lambda x: (parse_t(x[1].get("time")) or NOW - timedelta(days=30)), reverse=True)[:60]:
        u = f"{SITE}/story/{it['id']}/"
        feed_items.append({"title": it["headline"], "link": u, "date": parse_t(it.get("time")),
                           "cat": SECTION_LABEL.get(sec), "desc": it.get("summary") or it["headline"]})
    changed += write("feed.xml", rss("The Seax: Essex news, sport and life", SITE + "/",
                                     "The latest Essex news, sport and life, updated through the day.", f"{SITE}/feed.xml", feed_items))

    # sitemaps
    def lastmod(rec):
        return (rec.get("u") or rec.get("t") or rec.get("last") or iso(NOW))[:10]
    urls = [(SITE + "/", NOW.date().isoformat(), "hourly", "1.0"), (SITE + "/about/", None, "monthly", "0.4"),
            (SITE + "/briefing/", latest or None, "daily", "0.7")]
    for sid, rec in sorted(archive.items(), key=lambda kv: kv[1].get("t") or kv[1].get("first") or "", reverse=True):
        urls.append((f"{SITE}/story/{sid}/", lastmod(rec), None, None))
    for x in briefs:
        urls.append((f"{SITE}/briefing/{x['date']}/", x["date"], None, None))
    for u, lm in cw_urls:
        urls.append((u, lm, "daily" if u.endswith("/council-watch/") else None, "0.7" if u.endswith("/council-watch/") else None))
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, lm, cf, pr in urls:
        sm.append("<url><loc>" + E(loc) + "</loc>" + (f"<lastmod>{lm}</lastmod>" if lm else "") +
                  (f"<changefreq>{cf}</changefreq>" if cf else "") + (f"<priority>{pr}</priority>" if pr else "") + "</url>")
    sm.append("</urlset>\n")
    changed += write("sitemap.xml", "\n".join(sm))
    ns = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">']
    for sid, rec in archive.items():
        t = parse_t(rec.get("t"))
        if t and t >= NOW - timedelta(hours=48) and rec.get("sec") != "features":
            ns.append(f"<url><loc>{SITE}/story/{sid}/</loc><news:news><news:publication><news:name>The Seax</news:name>"
                      f"<news:language>en</news:language></news:publication><news:publication_date>{iso(t)}</news:publication_date>"
                      f"<news:title>{E(rec['h'])}</news:title></news:news></url>")
    ns.append("</urlset>\n")
    changed += write("news-sitemap.xml", "\n".join(ns))

    changed += bool(patch_index(latest))
    print(f"build: {len(seen)} story pages from this edition, {len(archive)} in archive, {len(briefs)} briefings, {changed} files changed")

if __name__ == "__main__":
    main()
