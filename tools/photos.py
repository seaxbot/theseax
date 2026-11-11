#!/usr/bin/env python3
"""Photos for stories: Wikimedia Commons file photos of the story's own subject, and stock photos for generic stories
from Openverse (all openly licensed; no API key needed).

Runs on GitHub Actions after each edition is published. For every story that asks for a photo,
either with a "photo" keyword in edition.json (set by the newsroom) or in data/photo-requests.json
(set by the owner: {"story-id": "keyword"}, or {"story-id": "File:<exact Wikimedia Commons file name>"} to pin one
Commons photo), it:
  1. refuses sensitive stories (crime, courts, deaths, crashes, health, tributes),
  2. searches Openverse for a wide, large image licensed for commercial use (CC0, public domain, CC BY, CC BY-SA),
  3. saves a 1200px copy to img/stock/<story-id>.jpg and the credit to data/photos.json.
Stories about one specific named place or thing (a landmark, building, bridge, pier, park, ship, train) carry a
"commons" phrase instead (set by the newsroom; owner's rule, Nov 2026: use Wikimedia Commons for pictures that relate
to the story). Those are searched on Wikimedia Commons first and shown as a credited "File photo" (kind "commons");
if Commons has nothing suitable, the story's "photo" phrase, if any, falls back to Openverse.
The website and story pages show the photo labelled "Stock photo" with the creator, licence and source.
Standard library plus Pillow (for resizing).
"""
import io, json, os, re, ssl, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = "TheSeaxPhotoDesk/1.0 (+https://theseax.com/about/; theseaxessex@gmail.com)"
API = "https://api.openverse.org/v1/images/"
SENSITIVE = re.compile(r"\b(police|court|crime|jail|jailed|sentenc|convict|charged|arrest|murder|kill|killed|stab|rape|assault|abuse|death|died|dies|dead|"
                       r"fatal|crash|collision|inquest|tribute|funeral|suicide|missing|(?<!wildlife )hospital|patient|cancer|disease|hit-and-run|appeal for witnesses)", re.I)
SKIP_TAGS = {"police", "court", "crime", "appeal", "tribute", "health", "fire", "ambulance"}
# Bus stories always show the owner's bus photo (img/topics/bus.jpg), so no stock photo is looked up for them (nor for pool stories).
# Same headline test as tools/build.py BUS_RX.
BUS_RX = re.compile(r"\bbus(es|ses)?\b|\bpark (and|&) ride\b|\bFirst (Essex|Bus)\b|\bEnsign ?bus\b", re.I)
# Swimming pool stories always show the owner's pool photo (img/topics/pool.jpg). Same headline test as tools/build.py POOL_RX.
POOL_RX = re.compile(r"\bswimming (pools?|baths?)\b|\blidos?\b|\b(leisure|school|public|council|indoor|outdoor|learner|teaching|training|community|hydrotherapy|main) pools?\b|\bpools?\b.{0,40}\bswim\w*|\bswim\w*\b.{0,40}\bpools?\b", re.I)
# Homeless stories always show the owner's homeless photo (img/topics/homeless.jpg). Same headline test as tools/build.py HOMELESS_RX.
HOMELESS_RX = re.compile(r"\bhomeless\w*\b|\brough[- ]sleep\w*\b|\bsleep\w* rough\b|\b(night|winter|homeless|emergency) shelters?\b|\bSWEP\b", re.I)
HOMELESS_HOUSING_RX = re.compile(r"\b(famil(y|ies)|children|kids|temporary (housing|accommodation)|B&Bs?|bed and breakfasts?|overspend\w*|budgets?|deficits?|council tax|housing (costs?|bill|pressures?|waiting list))\b", re.I)  # homeless families, temporary housing and budget stories can still get a stock photo
MAX_NEW = 12   # lookups per run
# Overseas photos are never used (owner's rule, 11 Nov 2026, after a "bus stop" search put a Moldovan village bus
# shelter on a Thurrock fares story). A photo whose title, tags, description or categories name another country, a US
# state, or a major overseas city or region is rejected, so a generic phrase only ever gets a photo that could pass
# for Essex. Words that are also everyday English (Turkey, Jordan, Chad, Georgia, Guinea, Victoria) are left out.
# The check runs on new lookups only; owner-pinned files (data/photo-requests.json "File:...") are never second-guessed.
ABROAD = re.compile(r"\b(" + "|".join([
    # countries and territories
    "afghanistan", "albania", "algeria", "andorra", "angola", "argentina", "armenia", "australia", "austria", "azerbaijan",
    "bahamas", "bahrain", "bangladesh", "barbados", "belarus", "belgium", "belize", "benin", "bhutan", "bolivia", "bosnia",
    "botswana", "brazil", "brasil", "brunei", "bulgaria", "burkina faso", "burundi", "cambodia", "cameroon", "canada",
    "cape verde", "chile", "china", "colombia", "comoros", "congo", "costa rica", "croatia", "cuba", "cyprus", "czechia",
    "czech republic", "denmark", "djibouti", "dominican republic", "ecuador", "egypt", "el salvador", "eritrea", "estonia",
    "eswatini", "ethiopia", "fiji", "finland", "france", "gabon", "gambia", "germany", "deutschland", "ghana", "greece",
    "guatemala", "guyana", "haiti", "honduras", "hungary", "iceland", "india", "indonesia", "iran", "iraq", "israel",
    "italy", "italia", "ivory coast", "jamaica", "japan", "kazakhstan", "kenya", "kosovo", "kuwait", "kyrgyzstan", "laos",
    "latvia", "lebanon", "lesotho", "liberia", "libya", "liechtenstein", "lithuania", "luxembourg", "madagascar", "malawi",
    "malaysia", "maldives", "mali", "malta", "mauritania", "mauritius", "mexico", "moldova", "monaco", "mongolia",
    "montenegro", "morocco", "mozambique", "myanmar", "burma", "namibia", "nepal", "netherlands", "nederland", "holland",
    "new zealand", "nicaragua", "nigeria", "north korea", "north macedonia", "macedonia", "norway", "oman", "pakistan",
    "palestine", "panama", "papua new guinea", "paraguay", "peru", "philippines", "poland", "polska", "portugal", "qatar",
    "romania", "russia", "rwanda", "san marino", "saudi arabia", "senegal", "serbia", "seychelles", "sierra leone",
    "singapore", "slovakia", "slovenia", "somalia", "south africa", "south korea", "korea", "south sudan", "spain",
    "espana", "españa", "sri lanka", "sudan", "suriname", "sweden", "switzerland", "syria", "taiwan", "tajikistan",
    "tanzania", "thailand", "timor", "togo", "trinidad", "tunisia", "türkiye", "turkmenistan", "uganda", "ukraine",
    "united arab emirates", "uae", "uruguay", "usa", "u\\.s\\.a", "united states", "uzbekistan", "vanuatu", "venezuela",
    "vietnam", "viet nam", "yemen", "zambia", "zimbabwe", "republica", "república", "republique", "république",
    # US states
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut", "delaware", "florida", "hawaii",
    "idaho", "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana", "maine", "maryland", "massachusetts",
    "michigan", "minnesota", "mississippi", "missouri", "montana", "nebraska", "nevada", "new hampshire", "new jersey",
    "new mexico", "new york", "north carolina", "north dakota", "ohio", "oklahoma", "oregon", "pennsylvania",
    "rhode island", "south carolina", "south dakota", "tennessee", "texas", "utah", "vermont", "virginia",
    "west virginia", "wisconsin", "wyoming", "washington,? d\\.?c", "washington state",
    # overseas regions and big cities
    "ontario", "quebec", "british columbia", "alberta", "toronto", "vancouver", "montreal", "ottawa", "new south wales",
    "queensland", "sydney", "melbourne", "brisbane", "perth, wa", "auckland", "wellington, nz", "paris", "berlin",
    "munich", "münchen", "hamburg", "frankfurt", "cologne", "köln", "rome", "roma", "milan", "milano", "venice", "naples",
    "madrid", "barcelona", "seville", "valencia", "lisbon", "porto", "amsterdam", "rotterdam", "brussels", "antwerp",
    "vienna", "wien", "prague", "praha", "budapest", "warsaw", "krakow", "kraków", "moscow", "st petersburg",
    "saint petersburg", "kyiv", "kiev", "chisinau", "chișinău", "bucharest", "belgrade", "zagreb", "athens", "istanbul",
    "ankara", "copenhagen", "stockholm", "oslo", "helsinki", "reykjavik", "zurich", "zürich", "geneva", "dubai",
    "abu dhabi", "doha", "tel aviv", "jerusalem", "cairo", "nairobi", "lagos", "johannesburg", "cape town", "mumbai",
    "delhi", "bangalore", "kolkata", "karachi", "lahore", "dhaka", "bangkok", "hanoi", "jakarta", "bali", "manila",
    "kuala lumpur", "hong kong", "beijing", "shanghai", "tokyo", "osaka", "kyoto", "seoul", "taipei", "los angeles",
    "san francisco", "chicago", "boston", "seattle", "las vegas", "miami", "new orleans", "manhattan", "brooklyn",
    "rio de janeiro", "sao paulo", "são paulo", "buenos aires", "mexico city", "havana", "europe", "asia", "africa",
    # nationalities that mark a photo as taken abroad ("Polish" and "Indian" are left out: everyday English and Essex
    # businesses)
    "american", "canadian", "mexican", "brazilian", "argentine", "australian", "french", "german", "italian", "spanish",
    "portuguese", "dutch", "belgian", "swiss", "austrian", "swedish", "norwegian", "danish", "finnish", "icelandic",
    "czech", "slovak", "hungarian", "romanian", "bulgarian", "croatian", "serbian", "greek", "turkish", "russian",
    "ukrainian", "moldovan", "chinese", "japanese", "korean", "thai", "vietnamese", "filipino", "indonesian",
    "malaysian", "israeli", "egyptian", "moroccan", "nigerian", "kenyan",
]) + r")\b", re.I)
COMMONS = "https://commons.wikimedia.org/w/api.php"
COMMONS_OK = re.compile(r"^(cc0|public domain|pd|cc by(-sa)? \d(\.\d)?( [a-z]+)?|cc by(-sa)?)$", re.I)  # no NC/ND, no fair use
SOURCES = {"flickr", "wikimedia", "stocksnap", "rawpixel", "nappy"}  # Openverse photo libraries we accept
# Flickr and Wikimedia photos are usually of a real place somewhere in the world, and a title can hide the country
# (a Japanese school pool came through titled only with its town). So a stock photo from those two libraries must
# show it was taken in the UK: a UK country, region, county, big city or geograph.org.uk in its title, tags or link
# (owner's rule, 11 Nov 2026). Studio stock libraries (StockSnap, rawpixel, nappy) are placeless and need no UK sign.
PLACED_SOURCES = {"flickr", "wikimedia"}
UK_RX = re.compile(r"\b(uk|u\.k|united kingdom|great britain|britain|british|england|english|scotland|scottish|wales|welsh|"
                   r"northern ireland|geograph|essex|london|kent|suffolk|norfolk|hertfordshire|herts|cambridgeshire|surrey|"
                   r"sussex|hampshire|berkshire|buckinghamshire|bedfordshire|oxfordshire|wiltshire|dorset|devon|cornwall|"
                   r"somerset|gloucestershire|worcestershire|warwickshire|shropshire|staffordshire|derbyshire|"
                   r"nottinghamshire|leicestershire|lincolnshire|northamptonshire|rutland|cheshire|lancashire|merseyside|"
                   r"yorkshire|cumbria|northumberland|durham|tyne|chelmsford|colchester|southend|basildon|harlow|braintree|"
                   r"brentwood|thurrock|grays|clacton|harwich|maldon|epping|saffron walden|rayleigh|billericay|witham|"
                   r"manchester|birmingham|liverpool|leeds|sheffield|bristol|newcastle|nottingham|leicester|cambridge|"
                   r"oxford|brighton|norwich|ipswich|edinburgh|glasgow|cardiff|belfast)\b", re.I)
CTX = ssl.create_default_context()

def get(url, binary=False, limit=80_000_000, tries=3):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json, image/*;q=0.9"})
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=40, context=CTX) as r:
                data = r.read(limit)
                return data if binary else json.loads(data.decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code != 429 or i == tries - 1:
                raise
            time.sleep(int(e.headers.get("Retry-After") or 0) or 5 * (i + 1))  # Wikimedia and Openverse rate limits

def load(p, d):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return d

def items(ed):
    for sec in ("stories", "community", "official", "features", "councilwatch"):
        for it in ed.get(sec) or []:
            if isinstance(it, dict) and it.get("id"):
                yield it
    for it in (ed.get("sport") or {}).get("stories") or []:
        pass  # sport stories always use the sport photo library

def sensitive(it):
    tag = str(it.get("tag") or "").lower()
    icon = str(it.get("icon") or "").lower()
    if tag in SKIP_TAGS or icon in SKIP_TAGS:
        return True
    return bool(SENSITIVE.search(f'{it.get("headline", "")} {it.get("summary", "")}'))

def search(kw):
    q = urllib.parse.urlencode({"q": kw, "license_type": "commercial", "license": "cc0,pdm,by,by-sa", "aspect_ratio": "wide",
                                "size": "large", "mature": "false", "page_size": 20})
    res = get(f"{API}?{q}").get("results") or []
    good = []
    for r in res:
        w, h = r.get("width") or 0, r.get("height") or 0
        title = f'{r.get("title") or ""} {" ".join(t.get("name", "") for t in (r.get("tags") or [])[:20])}'.lower()
        if w and w < 900:
            continue
        if re.search(r"\b(people|person|man|woman|girl|boy|child|portrait|selfie|face|crowd)\b", title):
            continue  # never put identifiable people beside a news story
        if re.search(r"\b(map|maps|chart|diagram|graph|infographic|logo|poster|screenshot|volunteers?|staff|employees?|workers?|students?|team)\b", title):
            continue  # no maps, charts or graphics, and no groups of people
        if str(r.get("source") or "").lower() not in SOURCES:
            continue  # photo libraries only: no museum objects, artworks or archive scans
        everything = f'{r.get("title") or ""} {" ".join(t.get("name", "") for t in (r.get("tags") or []))} {r.get("foreign_landing_url") or ""}'
        if ABROAD.search(everything.replace("_", " ")):
            continue  # taken abroad: never put an overseas scene beside an Essex story
        if str(r.get("source") or "").lower() in PLACED_SOURCES and not UK_RX.search(everything.replace("_", " ")):
            continue  # a real place with no sign it is in the UK: no photo is better than an overseas one
        words = [x for x in re.findall(r"[a-z]+", kw.lower()) if len(x) > 2]
        hits = sum(1 for x in words if x in title)
        if words and hits < len(words):
            continue  # every word of the phrase must match; no photo is better than a wrong one
        good.append((hits, (w * h) if w and h else 0, r))
    good.sort(key=lambda t: (-t[0], -t[1]))
    return [g[2] for g in good][:5]

def _plain(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", str(html or ""))).strip()

def commons_search(kw):
    """Wikimedia Commons photos that plainly show the named subject. Same safety filters as stock photos, plus:
    landscape photos only, free licences only (CC0, public domain, CC BY, CC BY-SA), no personality-rights files,
    no old archive scans, and every word of the phrase must appear in the file's title, description or categories."""
    q = urllib.parse.urlencode({"action": "query", "format": "json", "generator": "search", "gsrsearch": f"{kw} filetype:bitmap",
                                "gsrnamespace": 6, "gsrlimit": 30, "prop": "imageinfo|categories", "cllimit": "max", "clshow": "!hidden",
                                "iiprop": "url|size|mime|extmetadata", "iiurlwidth": 1200})
    pages = (get(f"{COMMONS}?{q}").get("query") or {}).get("pages") or {}
    words = [x for x in re.findall(r"[a-z0-9]+", kw.lower()) if len(x) > 2 or x.isdigit()]
    good = []
    for pg in pages.values():
        ii = (pg.get("imageinfo") or [{}])[0]
        md = ii.get("extmetadata") or {}
        meta = lambda k: _plain((md.get(k) or {}).get("value"))
        w, h = ii.get("width") or 0, ii.get("height") or 0
        if ii.get("mime") not in ("image/jpeg", "image/png", "image/webp") or w < 1000 or not h or w / h < 1.2:
            continue  # landscape photos big enough for the 1200px card
        lic = meta("LicenseShortName")
        if not COMMONS_OK.match(lic.strip()) or meta("Restrictions"):
            continue  # free licences only; skip personality-rights, trademark and other restricted files
        cats = " ".join(c.get("title", "") for c in pg.get("categories") or [])
        title = re.sub(r"^File:|\.[a-z]+$", "", pg.get("title") or "", flags=re.I).replace("_", " ")
        text = f"{title} {meta('ImageDescription')} {meta('ObjectName')} {cats}".lower()
        if re.search(r"\b(people|person|man|woman|girl|boy|child|children|portrait|selfie|face|crowd|mayor|councillor|mp)\b", text):
            continue  # never put identifiable people beside a news story
        if re.search(r"\b(map|maps|chart|diagram|graph|infographic|logo|poster|screenshot|plan|drawing|painting|engraving|lithograph|"
                     r"illustration|postcard|watercolou?r|sketch|print|scan|archive|museum|historic photograph)\b", text):
            continue  # photographs only: no maps, artworks or archive scans
        m = re.search(r"\b(1[89]\d\d|19[0-8]\d)\b", meta("DateTimeOriginal"))
        if m:
            continue  # nothing taken before 1990: the place must look as it does now
        if words and not all(x in text for x in words):
            continue  # every word of the phrase must match; no photo is better than a wrong one
        if ABROAD.search(text):
            continue  # taken abroad: never put an overseas scene beside an Essex story
        score = (2 if re.search(r"(quality|featured|valued) (images|pictures)", cats, re.I) else 0) + (1 if "geograph" in text else 0)
        yr = re.search(r"\b(20\d\d)\b", meta("DateTimeOriginal"))
        good.append((score, int(yr.group(1)) if yr else 2000, w * h, {
            "url": ii.get("thumburl") or ii.get("url"), "title": re.sub(r"\s*-\s*geograph\.org\.uk\s*-\s*\d+\s*$", "", meta("ObjectName") or title),
            "creator": meta("Artist") or "Wikimedia Commons contributor", "creator_url": "",
            "license": lic, "license_url": meta("LicenseUrl"), "foreign_landing_url": ii.get("descriptionurl") or "",
            "source": "Wikimedia Commons", "kind": "commons"}))
    good.sort(key=lambda t: (-t[0], -t[1], -t[2]))
    return [g[3] for g in good][:5]

def commons_file(name):
    """One exact Commons file the owner chose (data/photo-requests.json value "File:..."), with its credit and licence."""
    name = name if name.startswith("File:") else "File:" + name
    q = urllib.parse.urlencode({"action": "query", "format": "json", "titles": name, "prop": "imageinfo",
                                "iiprop": "url|size|mime|extmetadata", "iiurlwidth": 1200})
    for pg in ((get(f"{COMMONS}?{q}").get("query") or {}).get("pages") or {}).values():
        ii = (pg.get("imageinfo") or [{}])[0]
        md = ii.get("extmetadata") or {}
        meta = lambda k: _plain((md.get(k) or {}).get("value"))
        if not ii:
            continue
        title = re.sub(r"^File:|\.[a-z]+$", "", pg.get("title") or "", flags=re.I).replace("_", " ")
        return [{"url": ii.get("thumburl") or ii.get("url"),
                 "title": re.sub(r"\s*-\s*geograph\.org\.uk\s*-\s*\d+\s*$", "", meta("ObjectName") or title),
                 "creator": meta("Artist") or "Wikimedia Commons contributor", "creator_url": "",
                 "license": meta("LicenseShortName"), "license_url": meta("LicenseUrl"),
                 "foreign_landing_url": ii.get("descriptionurl") or "", "source": "Wikimedia Commons", "kind": "commons"}]
    return []

def save_image(url, path):
    from PIL import Image, ImageFile
    ImageFile.LOAD_TRUNCATED_IMAGES = True
    data = get(url, binary=True)
    im = Image.open(io.BytesIO(data)).convert("RGB")
    if im.width < 700:
        raise ValueError("too small")
    if im.width > 1200:
        im = im.resize((1200, round(im.height * 1200 / im.width)), Image.LANCZOS)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im.save(path, "JPEG", quality=80, optimize=True, progressive=True)
    return im.width, im.height

def main():
    ed = load(os.path.join(ROOT, "edition.json"), {})
    reqs = load(os.path.join(ROOT, "data", "photo-requests.json"), {})
    pj = os.path.join(ROOT, "data", "photos.json")
    photos = load(pj, {})
    live_ids = set()
    changed_rej = False
    want = {}
    for it in items(ed):
        live_ids.add(it["id"])
        if it.get("noPhoto"):  # the newsroom rejected this story's photo: remove it and never look again
            if it["id"] in photos:
                f = os.path.join(ROOT, "img", "stock", f"{it['id']}.jpg")
                if os.path.exists(f):
                    os.remove(f)
                photos.pop(it["id"]); changed_rej = True
                print(f"removed rejected photo: {it['id']}")
            continue
        if (BUS_RX.search(str(it.get("headline") or "")) or POOL_RX.search(str(it.get("headline") or "")) or (HOMELESS_RX.search(str(it.get("headline") or "")) and not HOMELESS_HOUSING_RX.search(str(it.get("headline") or "")))) and it["id"] not in reqs:
            if it["id"] in photos:  # bus stories use the owner's bus photo: drop any stock photo found earlier
                f = os.path.join(ROOT, "img", "stock", f"{it['id']}.jpg")
                if os.path.exists(f):
                    os.remove(f)
                photos.pop(it["id"]); changed_rej = True
                print(f"removed stock photo from bus, pool or homeless story: {it['id']}")
            continue
        kw = str(reqs.get(it["id"]) or it.get("photo") or "").strip()
        cm = str(it.get("commons") or "").strip() if it["id"] not in reqs else ""
        if (kw or cm) and it["id"] not in photos:
            if sensitive(it) and it["id"] not in reqs:
                print(f"skip (sensitive): {it['id']}")
                continue
            want[it["id"]] = (cm, kw)
    changed, n = bool(changed_rej), 0
    for sid, (cm, kw) in want.items():
        if n >= MAX_NEW:
            break
        n += 1
        cands = []
        if kw.startswith("File:"):  # the owner pinned one exact Wikimedia Commons file to this story
            try:
                cands = [dict(r, _kw=kw[5:]) for r in commons_file(kw)]
            except Exception as e:
                print(f"commons file failed for {sid} ({kw}): {e}")
            kw = ""
        if cm:
            try:
                cands = [dict(r, _kw=cm) for r in commons_search(cm)]
            except Exception as e:
                print(f"commons search failed for {sid} ({cm}): {e}")
            if not cands:
                print(f"no Commons photo for {sid} ({cm})" + (f"; trying stock ({kw})" if kw else ""))
            time.sleep(1.2)
        if not cands and kw:
            try:
                cands = [dict(r, _kw=kw) for r in search(kw)]
            except Exception as e:
                print(f"search failed for {sid} ({kw}): {e}"); time.sleep(2); continue
            time.sleep(1.2)
        for r in cands:
            try:
                w, h = save_image(r["url"], os.path.join(ROOT, "img", "stock", f"{sid}.jpg"))
            except Exception as e:
                print(f"  image failed {r.get('url', '')[:80]}: {e}"); continue
            lic = (r.get("license") or "").lower()
            label = {"cc0": "CC0", "pdm": "Public domain"}.get(lic, f"CC {lic.upper()} {r.get('license_version') or ''}".strip())
            if r.get("kind") == "commons":
                label = "Public domain" if r["license"].strip().lower() in ("public domain", "pd") else r["license"].strip()
            photos[sid] = {"file": f"/img/stock/{sid}.jpg", "w": w, "h": h, "keyword": r["_kw"], "kind": r.get("kind") or "stock", "title": re.sub(r"<[^>]+>", "", r.get("title") or "").strip()[:140],
                           "creator": (r.get("creator") if r.get("creator") and r.get("creator").lower() != "unknown" else (r.get("source") or r.get("provider") or "Openverse"))[:80], "creatorUrl": r.get("creator_url") or "",
                           "license": label, "licenseUrl": r.get("license_url") or "", "source": r.get("foreign_landing_url") or "",
                           "provider": r.get("source") or r.get("provider") or "", "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
            print(f"{photos[sid]['kind']} photo for {sid}: {r['_kw']} -> {photos[sid]['title'][:60]} by {photos[sid]['creator']} ({label})")
            changed = True
            break
        else:
            print(f"no suitable photo for {sid} ({cm or kw})")
    # forget photos for stories gone for more than 30 days from the archive and the edition
    arch = load(os.path.join(ROOT, "data", "archive.json"), {})
    for sid in list(photos):
        if sid not in live_ids and sid not in arch:
            p = os.path.join(ROOT, "img", "stock", f"{sid}.jpg")
            if os.path.exists(p):
                os.remove(p)
            photos.pop(sid); changed = True
    if changed:
        json.dump(photos, open(pj, "w", encoding="utf-8"), ensure_ascii=False, indent=0, sort_keys=True)
    print("CHANGED" if changed else "NO CHANGE")

if __name__ == "__main__":
    main()
