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
                 "community": "Community", "features": "Features"}

def icon_of(it, sec):
    ic = str(it.get("icon") or "").lower()
    if ic in ICON_COLOUR:
        return ic
    tag = str(it.get("tag") or "").lower()
    if tag in TAG_ICON:
        return TAG_ICON[tag]
    if sec == "sport":
        return "sport"
    return "news"

def card_of(it, sec):
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
<meta property="og:image" content="{SITE}/img/og/{og_image}.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="The Seax, Essex News, Sport, Life.">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{E(title.replace(' · The Seax', ''))}">
<meta name="twitter:description" content="{E(desc)}">
<meta name="twitter:image" content="{SITE}/img/og/{og_image}.png">
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
  <a href="/#news">News</a><a href="/#sport">Sport</a><a href="/#desk">Public Services</a><a href="/#community">Community</a><a href="/#whatson">What's On</a><a href="/briefing/">Morning briefing</a><a href="/about/">About</a>
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

# ---------- story pages ----------
def collect(ed):
    out = []
    for sec, items in [("news", ed.get("stories", [])), ("sport", (ed.get("sport") or {}).get("stories", [])),
                       ("official", ed.get("official", [])), ("courts", ed.get("courts", [])),
                       ("community", ed.get("community", [])), ("features", ed.get("features", []))]:
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
    kicker = "Feature" if sec == "features" else (it.get("tag") or SECTION_LABEL.get(sec, "News"))
    ld = {
        "@context": "https://schema.org", "@type": "NewsArticle",
        "headline": trunc(title, 110), "description": desc,
        "mainEntityOfPage": url, "url": url,
        "image": [f"{SITE}/img/og/{card}.png"],
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
    if src:
        meta.append(f"<span>Reported by {E(src)}</span>")
    org = ""
    if it.get("org") and sec in ("official", "courts", "community"):
        org = f'<div class="org">{E(SECTION_LABEL[sec])} · {E(it["org"])}</div>'
    readfull = ""
    if surl:
        readfull = f"""<div class="readfull"><div><div class="k">Read the full story</div><div class="src">{E(src or host(surl))}</div></div>
<a class="go" href="{E(surl)}" target="_blank" rel="noopener">Open at {E(host(surl) or src)} ↗</a></div>"""
    also_html = ""
    if also:
        also_html = '<h2>Also reported by</h2><ul class="also">' + "".join(
            f'<li><a href="{E(a["url"])}" target="_blank" rel="noopener"><b>{E(a.get("name") or host(a["url"]))}</b> <span>{E(host(a["url"]))} ↗</span></a></li>' for a in also) + "</ul>"
    mail = CFG["contactEmail"]
    corr = f'mailto:{mail}?subject={quote("Correction: " + title)}&body={quote("Page: " + url)}'
    more_html = "".join(
        f'<a class="rel" href="/story/{E(m["id"])}/" style="--c:{ICON_COLOUR.get(icon_of(m, s), "#3a3f4b")}"><i></i><b>{E(m["headline"])}</b><span>{E(m.get("place") or "Essex")}</span></a>'
        for s, m in more)
    return head(f"{title} · The Seax", desc, url, card, "article", extra) + f"""<main class="wrap story">
<article style="--c:{colour}">
  <div class="kick"><span>{E(kicker)}</span><span>{E(place)}</span></div>
  {org}
  <h1>{E(title)}</h1>
  {f'<p class="standfirst">{E(summary)}</p>' if summary else ''}
  <div class="meta">{' <span class="dot">·</span> '.join(meta)}</div>
  {share_bar(url, title)}
  {''.join(f'<p>{E(p)}</p>' for p in body if str(p).strip())}
  {('<h2>Key points</h2><ul class="points">' + ''.join(f'<li>{E(p)}</li>' for p in points) + '</ul>') if points else ''}
  {readfull}
  {also_html}
  <p class="note">This is a summary written by The Seax. The original reporting, quotes and images belong to {E(src or 'the outlet named above')}{' and the other outlets listed' if also else ''}. <a href="{E(corr)}">Spotted a mistake? Tell us</a>.</p>
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

# ---------- about ----------
def about_page():
    mail = CFG["contactEmail"]
    url = f"{SITE}/about/"
    return head("About The Seax · The Seax", "How The Seax works, who it is for, how to contact us and how we correct mistakes.", url, "default") + f"""<main class="wrap prose">
<h1>About The Seax</h1>
<p class="standfirst">The Seax is a free, independent website for the people of Essex: the county's news, sport, weather, public services, community life and what's on, in one place and updated through the day.</p>

<h2>How The Seax works</h2>
<p>We watch hundreds of trusted sources across Essex and beyond: local newspapers and radio, hyperlocal and independent newsrooms, Essex Police, the fire and ambulance services, councils, the NHS, courts, charities, clubs and venues, plus national and specialist outlets when they report on Essex.</p>
<p>The Seax is produced with the help of AI. Automated research tools gather the latest reports each hour, and AI writes our headlines, summaries and short story pages in our own words, following our editorial rules. Every story names the outlet that reported it and links directly to the original, so you can always read the full report and support the journalists who did the work.</p>
<p>We do not copy articles, take photographs from other publishers, or publish anything we have not seen reported by a named source.</p>

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
    return {"date": day.isoformat(), "label": uk_day(when), "lead": lead, "stories": picked, "weather": today,
            "warnings": w.get("warnings") or [], "travel": travel, "results": res[:8], "whats": whats}

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
        if write(f"story/{it['id']}/index.html", story_page(sec, it, more)):
            changed += 1
        t = parse_t(it.get("time"))
        prev = archive.get(it["id"], {})
        archive[it["id"]] = {
            "h": it["headline"], "sec": sec, "card": card_of(it, sec), "place": it.get("place") or "",
            "t": iso(t) if t else prev.get("t", ""), "u": iso(parse_t(it.get("updated"))) if it.get("updated") else prev.get("u", ""),
            "first": prev.get("first") or iso(NOW), "last": iso(NOW),
        }

    # about page
    if write("about/index.html", about_page()):
        changed += 1

    # daily briefing
    uk_now = NOW.astimezone(UK)
    day = uk_now.date().isoformat()
    mins = uk_now.hour * 60 + uk_now.minute
    if (a.briefing_now or 390 <= mins < 720) and not os.path.exists(os.path.join(ROOT, "briefing", day, "index.html")):
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

    # RSS of latest stories
    feed_items = []
    for sec, it in sorted([x for x in items if x[0] in ("news", "sport", "courts", "official", "community", "features")],
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
