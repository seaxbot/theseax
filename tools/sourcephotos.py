#!/usr/bin/env python3
"""Official bodies' own pictures for their stories (owner's request, 14 Nov 2026: "use pics as necessary with credit").

The newsroom and inbox desks cannot download pictures (their network refuses most sites), but GitHub Actions can.
A desk that wants a source's own picture on a story adds a request to data/source-photos.json:

  {"<story-id>": {"url": "<image URL from the source's own page>", "creator": "NHS Essex",
                  "name": "<short caption of what the picture shows>", "source": "<the source's article URL>",
                  "anchor": "top" | "centre"}}

This script (run by .github/workflows/photos.yml) downloads each new request from an allowed official host, makes
img/people/<story-id>-wide.jpg (1200x655) and img/people/<story-id>-og.jpg (1200x630), and adds an entry to
data/portraits.json that names the story by id ("ids"), labelled "Picture" and credited to the source, so the card,
story page, share card and Facebook post all show it with the credit, whatever the headline becomes.
"anchor" "top" (the default for NHS Essex, whose web images carry its logo bars in the bottom-left corner) crops from
near the top; "centre" crops from the middle. A request whose value is {"remove": true} deletes the picture again
(for example when a missing person is found). Standard library plus Pillow (cairosvg for SVG logos).

CHARITY LOGOS (owner's rule, 22 Nov 2026: "If it's charity stories, always use the charity logo rather than a random
place"). A request marked "logo": true asks for the charity's own logo from its own website:

  {"<story-id>": {"logo": true, "creator": "Havens Hospices", "site": "https://www.havenshospices.org.uk/",
                  "url": "<optional: the logo image URL, if the desk saw it>", "match": "<optional regex>"}}

With no "url", the desk reads the charity's home page and finds the logo itself (an <img> marked logo in the page
header, the site's schema.org logo, then its touch icon). The image must come from the charity's own domain or its
website builder's image host. The logo is set, whole and uncropped, on a white card (img/people/logo-<charity>-*.jpg)
and kept as ONE entry per charity in data/portraits.json labelled "Logo" and credited to the charity, so every later
story about that charity reuses it: by id, and by the charity's name in the headline ("match", which defaults to the
charity's name when that is distinctive; "match": false turns it off). Headlines about deaths, crashes, crimes and
court cases never pick a logo up by name ("notMatch"), only by id.
"""
import glob, io, json, os, re, ssl, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = "TheSeaxPhotoDesk/1.0 (+https://theseax.com/about/; info@theseax.com)"
# Official sources only. Add hosts here when the owner approves a new source of pictures.
ALLOWED = ("essex.icb.nhs.uk", "nhs.uk", "essex.police.uk", "essex-fire.gov.uk", "gov.uk",
           "essex.ac.uk",   # University of Essex: owner approved, 17 Nov 2026 ("I expected the pics to be already uploaded with credit")
           "colchester.gov.uk",   # Colchester City Council: owner approved, 21 Nov 2026 (Leisure World story: "use pic on that site")
           "img.youtube.com", "i.ytimg.com")   # stills of videos the owner asks to embed (owner, 18 Nov 2026: Harlow Council's GTA video)
# Mailing services that host the pictures inside press-release and newsletter emails. Accepted only for requests
# marked "via": "email" (owner's rule, 20 Nov 2026: "When you're getting stories from emails please do use their pics").
MAIL_HOSTS = ("content.govdelivery.com", "govdelivery.com", "mcusercontent.com", "gallery.mailchimp.com",
              "list-manage.com", "createsend1.com", "createsend.com", "ctctcdn.com", "constantcontact.com",
              "sendgrid.net", "dotdigital.com", "dmtrk.net", "mailerlite.com", "mlcdn.com", "sendinblue.com",
              "brevo.com", "hubspotusercontent-eu1.net", "hubspotusercontent-na1.net", "hubspot.net",
              "beehiiv.com", "substackcdn.com", "squarespace-cdn.com", "wixstatic.com", "wp.com")
REQ = os.path.join(ROOT, "data", "source-photos.json")
POR = os.path.join(ROOT, "data", "portraits.json")
MISS = os.path.join(ROOT, "data", "logo-misses.json")   # logo requests that found nothing: retried after a day
SIZES = {"wide": (1200, 655), "og": (1200, 630)}
# Website builders and CDNs that host charities' own logos (the charity's own domain is always accepted).
LOGO_HOSTS = ("wixstatic.com", "squarespace-cdn.com", "wp.com", "wordpress.com", "cloudfront.net", "ctfassets.net",
              "imgix.net", "cloudinary.com", "amazonaws.com", "googleusercontent.com", "webflow.com",
              "website-files.com", "jimcdn.com", "weebly.com", "editmysite.com", "shopify.com", "hubspotusercontent-eu1.net",
              "hubspotusercontent-na1.net", "storyblok.com", "prismic.io", "sanity.io", "azureedge.net", "b-cdn.net")
# Headlines that never pick up a charity logo by name (read case-insensitively by build.py, fbpage.py and the page) (they keep the normal picture rules unless the desk pins it by id).
LOGO_NOT = (r"\b(dies|died|death|dead|killed|fatal|crash|collision|stabb|shot|murder|manslaughter|jailed|sentenced|"
            r"court|charged|guilty|arrest|police|fraud|theft|stole|inquest|coroner|abuse|assault)")
GENERIC = {"mind", "age uk", "shelter", "crisis", "home-start", "the trust", "foundation", "hospice", "the hospice",
           "food bank", "foodbank", "the charity", "cvs", "rotary", "lions", "scouts", "guides"}


def allowed(url, r=None):
    try:
        u = urllib.parse.urlparse(url)
    except Exception:
        return False
    h = (u.hostname or "").lower()
    ok = ALLOWED
    if r and r.get("via") == "email":
        # a sender's own site (the domain of the address it emailed from) or its mailing service
        sd = str(r.get("senderDomain") or "").lower().strip(".")
        ok = ALLOWED + MAIL_HOSTS + ((sd,) if re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", sd) else ())
    return u.scheme == "https" and any(h == a or h.endswith("." + a) for a in ok)


# www.essex.ac.uk uses Let's Encrypt's newer "Y" chain, not yet trusted by the runner: trust the intermediates kept in
# tools/feeds/certs/ as anchors (hostname and expiry are still checked), as the feed collector does.
CTX = ssl.create_default_context()
for _pem in sorted(glob.glob(os.path.join(ROOT, "tools", "feeds", "certs", "*.pem"))):
    CTX.load_verify_locations(_pem)
CTX.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "image/*"})
    with urllib.request.urlopen(req, timeout=40, context=CTX) as r:
        return r.read(25_000_000)


def site_host(site):
    try:
        h = (urllib.parse.urlparse(site).hostname or "").lower()
    except Exception:
        return ""
    return h[4:] if h.startswith("www.") else h


def logo_allowed(url, site):
    try:
        u = urllib.parse.urlparse(url)
    except Exception:
        return False
    h, sh = (u.hostname or "").lower(), site_host(site)
    if u.scheme != "https" or not sh or "." not in sh:
        return False
    base = ".".join(sh.split(".")[-3:]) if re.search(r"\.(org|co|ac|gov|nhs|ltd|me|net)\.uk$", sh) else ".".join(sh.split(".")[-2:])
    return any(h == a or h.endswith("." + a) for a in (sh, base) + LOGO_HOSTS)


FINAL = [""]


def find_logo(site):
    """The charity's logo from its home page: header <img> marked logo, then schema.org logo, then the touch icon."""
    req = urllib.request.Request(site, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
        html = r.read(3_000_000).decode("utf-8", "replace")
        site = r.geturl() or site  # a charity's site that redirects to its new domain (HARP: harphomeless.org)
    FINAL[0] = site
    found = []
    for m in re.finditer(r"<img\b[^>]*>", html, re.I):
        tag = m.group(0)
        if not re.search(r"logo", tag, re.I) or re.search(r"(sponsor|partner|funder|footer|award|lottery|fundraising-regulator|charity-commission|social|facebook|twitter|instagram)", tag, re.I):
            continue
        src = re.search(r"""\b(?:data-src|src)\s*=\s*["']([^"']+)["']""", tag, re.I)
        if src and not src.group(1).startswith("data:"):
            found.append(src.group(1))
    for m in re.finditer(r'"logo"\s*:\s*(?:\{[^}]*?"url"\s*:\s*)?"([^"]+)"', html):
        found.append(m.group(1).replace("\\/", "/"))
    for m in re.finditer(r"<link\b[^>]*rel=[\"'][^\"']*apple-touch-icon[^\"']*[\"'][^>]*>", html, re.I):
        h = re.search(r"""href\s*=\s*["']([^"']+)["']""", m.group(0), re.I)
        if h:
            found.append(h.group(1))
    return [urllib.parse.urljoin(site, f.strip()) for f in found]


def open_image(data, url):
    from PIL import Image
    if url.lower().split("?")[0].endswith(".svg") or data[:400].lstrip().startswith((b"<svg", b"<?xml")):
        import cairosvg
        data = cairosvg.svg2png(bytestring=data, output_width=1400)
    return Image.open(io.BytesIO(data))


def logo_card(im, size):
    """The whole logo, uncropped, centred on white, sized to stay clear of the card crops (2.4:1 to 4:3)."""
    from PIL import Image
    im = im.convert("RGBA")
    # a white logo (made for a dark website header) goes on a dark card so it can be seen
    px = [(r, g, b) for r, g, b, a in im.resize((80, 80)).getdata() if a > 128]
    light = px and sum(0.3 * r + 0.59 * g + 0.11 * b for r, g, b in px) / len(px) > 225 and any(a < 128 for *_, a in im.resize((80, 80)).getdata())
    paper = (24, 32, 48) if light else (255, 255, 255)
    bg = Image.new("RGBA", im.size, paper + (255,))
    im = Image.alpha_composite(bg, im).convert("RGB")
    W, H = size
    bw, bh = int(W * 0.6), int(H * 0.5)
    k = min(bw / im.size[0], bh / im.size[1], 4.0)
    im = im.resize((max(1, round(im.size[0] * k)), max(1, round(im.size[1] * k))), Image.LANCZOS)
    card = Image.new("RGB", size, paper)
    card.paste(im, ((W - im.size[0]) // 2, (H - im.size[1]) // 2))
    return card


try:
    MISSES = json.load(open(MISS, encoding="utf-8"))
except Exception:
    MISSES = {}


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60]


def do_logo(sid, r, por):
    """Returns (por, changed)."""
    creator = str(r.get("creator") or "").strip()[:60]
    site = str(r.get("site") or "").strip()
    if not creator or not site.startswith("https://"):
        print("logo request needs creator and an https site", sid)
        return por, False
    if time.time() - MISSES.get(sid, 0) < 86400:
        return por, False
    key = slug(creator)
    same = [p for p in por if p.get("charity") == key]
    if same and os.path.exists(ROOT + str(same[0].get("wide") or "")):
        p = same[0]
        if sid in (p.get("ids") or []):
            return por, False
        p["ids"] = (p.get("ids") or []) + [sid]
        print("logo reused", sid, creator)
        return por, True
    cands = [str(r["url"])] if r.get("url") else []
    FINAL[0] = ""
    try:
        cands += find_logo(site)
    except Exception as e:
        print("logo page failed", sid, site, e)
    im = None
    for url in dict.fromkeys(cands):
        if not (logo_allowed(url, site) or (FINAL[0] and logo_allowed(url, FINAL[0]))):
            print("logo refused host", sid, url[:80])
            continue
        try:
            im = open_image(fetch(url), url)
        except Exception as e:
            print("logo failed", sid, url[:80], e)
            continue
        if im.size[0] >= 120 or im.size[1] >= 120:
            break
        print("logo too small", sid, im.size)
        im = None
    if im is None:
        print("no logo found", sid, creator)
        MISSES[sid] = int(time.time())
        return por, False
    wide, og = f"/img/people/logo-{key}-wide.jpg", f"/img/people/logo-{key}-og.jpg"
    for k, f in (("wide", wide), ("og", og)):
        logo_card(im, SIZES[k]).save(ROOT + f, quality=90)
    m = r.get("match")
    if m is None:
        m = r"\b" + re.escape(creator).replace("\\ ", r"[\s-]").replace("'", "['’]") + r"\b" if creator.lower() not in GENERIC and len(creator) >= 5 else ""
    por = [p for p in por if p.get("charity") != key]
    ent = {"charity": key, "ids": sorted(set(sum(((p.get("ids") or []) for p in same), [])) | {sid}),
           "name": creator, "label": "Logo", "wide": wide, "og": og, "creator": creator, "provider": creator,
           "license": "", "licenseUrl": "", "source": site[:300], "notMatch": LOGO_NOT,
           "addedBy": f"photo desk {datetime.now(timezone.utc):%d %b %Y} (owner's rule, 22 Nov 2026: charity stories always use the charity's logo)"}
    if m:
        ent["match"] = str(m)
    por.append(ent)
    print("logo added", sid, creator, im.size)
    return por, True


def crop(im, size, anchor):
    from PIL import Image
    W, H = im.size
    tw, th = size
    want = tw / th
    if W / H > want:  # too wide: trim the sides evenly
        nw = round(H * want)
        box = ((W - nw) // 2, 0, (W - nw) // 2 + nw, H)
    else:  # too tall: trim top and bottom
        nh = round(W / want)
        top = round(H * 0.035) if anchor == "top" else (H - nh) // 2
        top = max(0, min(top, H - nh))
        box = (0, top, W, top + nh)
    return im.crop(box).resize(size, Image.LANCZOS)


def main():
    try:
        reqs = json.load(open(REQ, encoding="utf-8"))
    except Exception:
        return 0
    try:
        por = json.load(open(POR, encoding="utf-8"))
    except Exception:
        por = []
    from PIL import Image
    changed = False
    for sid, r in reqs.items():
        if not re.fullmatch(r"[a-z0-9-]{3,120}", sid) or not isinstance(r, dict):
            continue
        wide, og = f"/img/people/{sid}-wide.jpg", f"/img/people/{sid}-og.jpg"
        mine = [p for p in por if sid in (p.get("ids") or [])]
        if r.get("remove"):
            shared = [p for p in mine if p.get("charity") and len(p.get("ids") or []) > 1]
            if shared:  # a charity logo used by other stories too: unpin this story only
                for p in shared:
                    p["ids"] = [i for i in p["ids"] if i != sid]
                mine = [p for p in mine if p not in shared]
                changed = True
            if mine:
                por = [p for p in por if p not in mine]
                for f in {wide, og} | {str(p.get(k) or "") for p in mine for k in ("wide", "og")} - {""}:
                    try:
                        os.remove(ROOT + f)
                    except FileNotFoundError:
                        pass
                changed = True
                print("removed", sid)
            continue
        if r.get("logo"):
            por, ch = do_logo(sid, r, por)
            changed = changed or ch
            continue
        # a story's own picture replaces a charity logo for that story only; the shared logo entry stays for the others
        for p in por:
            if p.get("charity") and sid in (p.get("ids") or []):
                p["ids"] = [i for i in p["ids"] if i != sid]
                changed = True
        mine = [p for p in mine if not p.get("charity")]
        if mine and all(os.path.exists(ROOT + str(p.get("wide") or "")) for p in mine):
            continue  # already done (an owner-made picture for the same story counts)
        url = str(r.get("url") or "")
        if not allowed(url, r):
            print("refused host", sid, url[:80])
            continue
        try:
            im = Image.open(io.BytesIO(fetch(url))).convert("RGB")
        except Exception as e:
            print("failed", sid, e)
            continue
        if im.size[0] < 500:
            print("too small", sid, im.size)
            continue
        anchor = r.get("anchor") or ("top" if "essex.icb.nhs.uk" in url else "centre")
        for k, f in (("wide", wide), ("og", og)):
            crop(im, SIZES[k], anchor).save(ROOT + f, quality=86)
        creator = str(r.get("creator") or "").strip()[:60] or "Source"
        por = [p for p in por if p not in mine]
        por.append({"ids": [sid], "name": str(r.get("name") or "").strip()[:160] or creator, "label": "Picture",
                    "wide": wide, "og": og, "creator": creator, "provider": creator, "license": "", "licenseUrl": "",
                    "source": str(r.get("source") or "")[:300],
                    "addedBy": f"photo desk {datetime.now(timezone.utc):%d %b %Y} (owner's rule: official bodies' own pictures, credited)"})
        changed = True
        print("added", sid, im.size)
    if changed:
        json.dump(por, open(POR, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if MISSES:
        json.dump({k: v for k, v in MISSES.items() if time.time() - v < 7 * 86400}, open(MISS, "w"), indent=0)
    return 0


def local(argv):
    """Inbox desk: an email attachment already downloaded. Crops it and pins it to the story by id, at once.
    python3 tools/sourcephotos.py --file PATH --id STORY_ID --creator "Body name" --name "caption"
                                  [--source URL] [--anchor top|centre]"""
    import argparse
    from PIL import Image, ImageOps
    a = argparse.ArgumentParser()
    for k in ("--file", "--id", "--creator", "--name"):
        a.add_argument(k, required=True)
    a.add_argument("--source", default="")
    a.add_argument("--anchor", default="centre", choices=("top", "centre"))
    o = a.parse_args(argv)
    if not re.fullmatch(r"[a-z0-9-]{3,120}", o.id):
        sys.exit("bad story id")
    im = ImageOps.exif_transpose(Image.open(o.file)).convert("RGB")
    if im.size[0] < 500:
        sys.exit(f"too small {im.size}: not used")
    wide, og = f"/img/people/{o.id}-wide.jpg", f"/img/people/{o.id}-og.jpg"
    for k, f in (("wide", wide), ("og", og)):
        crop(im, SIZES[k], o.anchor).save(ROOT + f, quality=86)
    try:
        por = json.load(open(POR, encoding="utf-8"))
    except Exception:
        por = []
    por = [p for p in por if o.id not in (p.get("ids") or [])]
    creator = o.creator.strip()[:60]
    por.append({"ids": [o.id], "name": o.name.strip()[:160] or creator, "label": "Picture", "wide": wide, "og": og,
                "creator": creator, "provider": creator, "license": "", "licenseUrl": "", "source": o.source[:300],
                "addedBy": f"inbox desk {datetime.now(timezone.utc):%d %b %Y} (owner's rule, 20 Nov 2026: use the pictures emailed with stories, credited)"})
    json.dump(por, open(POR, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("added", o.id, im.size, wide, og)
    return 0


if __name__ == "__main__":
    sys.exit(local(sys.argv[1:]) if "--file" in sys.argv else main())
