#!/usr/bin/env python3
"""One-off generator for The Seax share cards and app icons.

Run from the repository root:  python3 tools/make_images.py
Needs Pillow, rsvg-convert and the Inter font (system or tools/fonts).
Outputs img/og/<card>.png (1200x630) and icons/*.png.
"""
import os, subprocess, tempfile, glob
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_DIRS = [os.path.join(ROOT, "tools", "fonts"), "/usr/share/fonts/opentype/inter"]

def font(name, size):
    for d in FONT_DIRS:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    raise SystemExit("font not found: " + name)

NAVY, PAPER, RED, GOLD = "#0e1b30", "#f6f1e6", "#c8102e", "#d0a13a"

# card key: (label, colour)
CARDS = {
    "default":     ("Essex News, Sport, Life.", RED),
    "news":        ("News", "#3a3f4b"),
    "police":      ("Police", "#1d4e9e"),
    "court":       ("Courts", "#3c3a7a"),
    "council":     ("Politics & Councils", "#1b2a44"),
    "fire":        ("Fire & Rescue", "#b3122b"),
    "health":      ("Health", "#1d7448"),
    "business":    ("Business", "#8a6414"),
    "property":    ("Property & Planning", "#7a5228"),
    "transport":   ("Travel & Transport", "#344559"),
    "weather":     ("Weather", "#356f9f"),
    "community":   ("Community", "#1a6e6b"),
    "environment": ("Environment & Wildlife", "#2b6e60"),
    "whatson":     ("What's On", "#8f1546"),
    "history":     ("History", "#6b5638"),
    "education":   ("Education", "#3a4a8f"),
    "feature":     ("Features", "#6b5638"),
    "football":    ("Football", "#0f5b84"),
    "cricket":     ("Cricket", "#0f5b84"),
    "racing":      ("Racing", "#0f5b84"),
    "sport":       ("Sport", "#0f5b84"),
    "briefing":    ("Essex at 7: the morning briefing", RED),
}

def shield_png(height, bg=None):
    """Render favicon.svg (the arms of Essex) to a PNG of the given height."""
    out = tempfile.mktemp(suffix=".png")
    args = ["rsvg-convert", "-h", str(height)]
    if bg:
        args += ["-b", bg]
    subprocess.run(args + ["-o", out, os.path.join(ROOT, "favicon.svg")], check=True)
    im = Image.open(out).convert("RGBA")
    os.remove(out)
    return im

def card(key, label, colour):
    W, H = 1200, 630
    im = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(im)
    # paper panel on the right, colour band on the left
    d.rectangle([0, 0, 28, H], fill=colour)
    d.rectangle([28, H - 10, W, H], fill=GOLD)
    sh = shield_png(330)
    im.paste(sh, (110, (H - sh.height) // 2 - 10), sh)
    x = 110 + sh.width + 60
    d.text((x, 150), "The Seax", font=font("InterDisplay-Black.otf", 120), fill="#ffffff")
    d.text((x, 292), "ESSEX NEWS, SPORT, LIFE." if key != "default" else "LIVE, ALL DAY", font=font("Inter-Bold.otf", 30), fill=GOLD)
    # section label in a pill
    f = font("InterDisplay-Bold.otf", 52)
    words, lines, cur = label.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) > W - x - 70 and cur:
            lines.append(cur); cur = w
        else:
            cur = t
    lines.append(cur)
    y = 370
    for ln in lines[:2]:
        tw = d.textlength(ln, font=f)
        d.rounded_rectangle([x - 4, y, x + tw + 36, y + 76], radius=16, fill=colour if key not in ("default", "briefing") else RED)
        d.text((x + 16, y + 6), ln, font=f, fill="#ffffff")
        y += 92
    d.text((x, H - 70), "theseax.com", font=font("Inter-SemiBold.otf", 28), fill="#b9c4d8")
    os.makedirs(os.path.join(ROOT, "img", "og"), exist_ok=True)
    im.save(os.path.join(ROOT, "img", "og", key + ".png"), optimize=True)

def breaking():
    """Breaking News picture (owner approved, Nov 2026): shown only on a major breaking story (breaking, weight 9+)
    that has no suitable photo. Writes img/og/breaking.png (share card) and img/topics/breaking.png (page art)."""
    W, H = 1200, 630
    im = Image.new("RGB", (W, H), NAVY)
    stripe = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(stripe)
    for x in range(-H, W + H, 46):
        sd.polygon([(x, 0), (x + 18, 0), (x + 18 - H, H), (x - H, H)], fill=(255, 255, 255, 9))
    im.paste(stripe, (0, 0), stripe)
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 28, H], fill=RED)
    d.rectangle([28, H - 10, W, H], fill=GOLD)
    sh = shield_png(300)
    sx, sy = 100, (H - sh.height) // 2 - 6
    im.paste(sh, (sx, sy), sh)
    x = sx + sh.width + 56
    ky = 150
    d.ellipse([x, ky + 9, x + 18, ky + 27], fill=RED)
    d.ellipse([x - 5, ky + 4, x + 23, ky + 32], outline=RED, width=2)
    d.text((x + 36, ky), "THE SEAX  ·  ESSEX", font=font("Inter-Bold.otf", 30), fill=GOLD)
    bf = font("InterDisplay-Black.otf", 124)
    d.text((x - 4, 188), "BREAKING", font=bf, fill="#ffffff")
    nw = d.textlength("NEWS", font=bf)
    d.rectangle([x - 4, 336, x + nw + 40, 468], fill=RED)
    d.text((x + 16, 332), "NEWS", font=bf, fill="#ffffff")
    d.text((x, H - 76), "theseax.com", font=font("Inter-SemiBold.otf", 28), fill="#b9c4d8")
    for sub in ("og", "topics"):
        os.makedirs(os.path.join(ROOT, "img", sub), exist_ok=True)
        im.save(os.path.join(ROOT, "img", sub, "breaking.png"), optimize=True)
    # 4:3 version for the lead panel and other near-square spots (content kept inside the middle 780px of height,
    # so the panel's slight crop on phones never cuts it)
    PW, PH = 1200, 900
    pn = Image.new("RGB", (PW, PH), NAVY)
    stripe = Image.new("RGBA", (PW, PH), (0, 0, 0, 0))
    sd = ImageDraw.Draw(stripe)
    for x in range(-PH, PW + PH, 46):
        sd.polygon([(x, 0), (x + 18, 0), (x + 18 - PH, PH), (x - PH, PH)], fill=(255, 255, 255, 9))
    pn.paste(stripe, (0, 0), stripe)
    d = ImageDraw.Draw(pn)
    d.rectangle([0, PH - 12, PW, PH], fill=GOLD)
    sh = shield_png(250)
    pn.paste(sh, ((PW - sh.width) // 2, 80), sh)
    kf = font("Inter-Bold.otf", 34)
    kt = "THE SEAX  ·  ESSEX"
    kw = d.textlength(kt, font=kf) + 40
    kx, ky = (PW - kw) / 2, 362
    d.ellipse([kx, ky + 10, kx + 20, ky + 30], fill=RED)
    d.ellipse([kx - 5, ky + 5, kx + 25, ky + 35], outline=RED, width=2)
    d.text((kx + 40, ky), kt, font=kf, fill=GOLD)
    bf = font("InterDisplay-Black.otf", 140)
    bw = d.textlength("BREAKING", font=bf)
    d.text(((PW - bw) / 2, 408), "BREAKING", font=bf, fill="#ffffff")
    nw = d.textlength("NEWS", font=bf)
    nx = (PW - nw - 44) / 2
    d.rectangle([nx, 578, nx + nw + 44, 726], fill=RED)
    d.text((nx + 22, 574), "NEWS", font=bf, fill="#ffffff")
    tf = font("Inter-SemiBold.otf", 30)
    d.text(((PW - d.textlength("theseax.com", font=tf)) / 2, 770), "theseax.com", font=tf, fill="#b9c4d8")
    pn.save(os.path.join(ROOT, "img", "topics", "breaking-panel.png"), optimize=True)

def icons():
    os.makedirs(os.path.join(ROOT, "icons"), exist_ok=True)
    for size, name in [(180, "apple-touch-icon.png"), (192, "icon-192.png"), (512, "icon-512.png")]:
        im = Image.new("RGBA", (size, size), PAPER)
        sh = shield_png(int(size * 0.78))
        im.paste(sh, ((size - sh.width) // 2, (size - sh.height) // 2), sh)
        im.convert("RGB").save(os.path.join(ROOT, "icons", name), optimize=True)
    # maskable: more padding
    size = 512
    im = Image.new("RGBA", (size, size), PAPER)
    sh = shield_png(int(size * 0.6))
    im.paste(sh, ((size - sh.width) // 2, (size - sh.height) // 2), sh)
    im.convert("RGB").save(os.path.join(ROOT, "icons", "maskable-512.png"), optimize=True)

if __name__ == "__main__":
    for k, (label, colour) in CARDS.items():
        card(k, label, colour)
    icons()
    print("made", len(CARDS), "cards and icons")
