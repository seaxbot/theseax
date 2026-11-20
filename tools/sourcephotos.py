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
(for example when a missing person is found). Standard library plus Pillow.
"""
import glob, io, json, os, re, ssl, sys, urllib.parse, urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = "TheSeaxPhotoDesk/1.0 (+https://theseax.com/about/; info@theseax.com)"
# Official sources only. Add hosts here when the owner approves a new source of pictures.
ALLOWED = ("essex.icb.nhs.uk", "nhs.uk", "essex.police.uk", "essex-fire.gov.uk", "gov.uk",
           "essex.ac.uk",   # University of Essex: owner approved, 17 Nov 2026 ("I expected the pics to be already uploaded with credit")
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
SIZES = {"wide": (1200, 655), "og": (1200, 630)}


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
