#!/usr/bin/env python3
"""Stock photos for generic stories, from Openverse (openly licensed images; no API key needed).

Runs on GitHub Actions after each edition is published. For every story that asks for a photo,
either with a "photo" keyword in edition.json (set by the newsroom) or in data/photo-requests.json
(set by the owner: {"story-id": "keyword"}), it:
  1. refuses sensitive stories (crime, courts, deaths, crashes, health, tributes),
  2. searches Openverse for a wide, large image licensed for commercial use (CC0, public domain, CC BY, CC BY-SA),
  3. saves a 1200px copy to img/stock/<story-id>.jpg and the credit to data/photos.json.
The website and story pages show the photo labelled "Stock photo" with the creator, licence and source.
Standard library plus Pillow (for resizing).
"""
import io, json, os, re, ssl, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = "TheSeaxPhotoDesk/1.0 (+https://theseax.com/about/; theseaxessex@gmail.com)"
API = "https://api.openverse.org/v1/images/"
SENSITIVE = re.compile(r"\b(police|court|crime|jail|jailed|sentenc|convict|charged|arrest|murder|kill|killed|stab|rape|assault|abuse|death|died|dies|dead|"
                       r"fatal|crash|collision|inquest|tribute|funeral|suicide|missing|(?<!wildlife )hospital|patient|cancer|disease|hit-and-run|appeal for witnesses)", re.I)
SKIP_TAGS = {"police", "court", "crime", "appeal", "tribute", "health", "fire", "ambulance"}
MAX_NEW = 12   # lookups per run
CTX = ssl.create_default_context()

def get(url, binary=False, limit=80_000_000):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json, image/*;q=0.9"})
    with urllib.request.urlopen(req, timeout=40, context=CTX) as r:
        data = r.read(limit)
        return data if binary else json.loads(data.decode("utf-8"))

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
        words = [x for x in re.findall(r"[a-z]+", kw.lower()) if len(x) > 2]
        hits = sum(1 for x in words if x in title)
        good.append((hits, (w * h) if w and h else 0, r))
    good.sort(key=lambda t: (-t[0], -t[1]))
    return [g[2] for g in good if g[0] > 0][:5]

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
    want = {}
    for it in items(ed):
        live_ids.add(it["id"])
        kw = str(reqs.get(it["id"]) or it.get("photo") or "").strip()
        if kw and it["id"] not in photos:
            if sensitive(it) and it["id"] not in reqs:
                print(f"skip (sensitive): {it['id']}")
                continue
            want[it["id"]] = kw
    changed, n = False, 0
    for sid, kw in want.items():
        if n >= MAX_NEW:
            break
        n += 1
        try:
            cands = search(kw)
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
            photos[sid] = {"file": f"/img/stock/{sid}.jpg", "w": w, "h": h, "keyword": kw, "title": (r.get("title") or "")[:140],
                           "creator": (r.get("creator") if r.get("creator") and r.get("creator").lower() != "unknown" else (r.get("source") or r.get("provider") or "Openverse"))[:80], "creatorUrl": r.get("creator_url") or "",
                           "license": label, "licenseUrl": r.get("license_url") or "", "source": r.get("foreign_landing_url") or "",
                           "provider": r.get("source") or r.get("provider") or "", "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
            print(f"photo for {sid}: {kw} -> {photos[sid]['title'][:60]} by {photos[sid]['creator']} ({label})")
            changed = True
            break
        else:
            print(f"no suitable photo for {sid} ({kw})")
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
