#!/usr/bin/env python3
"""The Seax daily audio bulletin (owner's request, 14 Nov 2026).

Turns a spoken script into the MP3 that the "Listen" player on the front page plays.
The script is written three times a day, at 07:00, 12:30 and 17:00 UK time, by the bulletin desk (see ops/bulletin.md).
(Owner added the 12:30 midday bulletin on 16 Nov 2026, slot "mid", and the 23:00 overnight bulletin on 17 Nov 2026, slot "night".)
(Owner first asked for 09:00 on 14 Nov 2026, then the same day moved it to 07:00 and 17:00, with the Saturday evening one at 18:40 for the football scores.)

  python3 tools/bulletin.py --script /tmp/bulletin.txt --stories id1,id2,id3
  python3 tools/bulletin.py --script /tmp/bulletin.txt --dry-run     (render to /tmp only, change nothing)
  python3 tools/bulletin.py --check-names /tmp/bulletin.txt           (print how the script will be voiced, no audio)

Script format: plain text, one story per paragraph, paragraphs separated by a blank line.
The owner's house style for the audio:
  - voice: Kokoro "bm_george" (British male) at speed 1.12 (owner chose the male v3 voice, 14 Nov 2026)
  - exactly 1.5 seconds of silence between paragraphs (owner's choice)
  - a news sting in the "headlines" style: synth pulse, drums, rising bleeps and a final hit (assets/audio/chime.wav, made by tools/make_sting.py), at the start and the end (owner chose it, 14 Nov 2026)
Writes:
  audio/bulletin-YYYY-MM-DD-am/-mid/-pm.mp3  (older bulletins are deleted, so the repository does not keep piling up files)
  data/bulletin.json              what the player reads: date, slot (am/mid/pm/night), file, duration, waveform peaks, story ids
  audio/alexa.json                the Alexa Flash Briefing feed (owner's request, 14 Nov 2026): the latest bulletin as one
                                  audio item, in Amazon's JSON feed format. The owner's Flash Briefing skill points at
                                  https://theseax.com/audio/alexa.json . Loudness is set to Amazon's spec (-14 LUFS, true peak under -2 dB).
  python3 tools/bulletin.py --alexa-only     (rewrite audio/alexa.json from data/bulletin.json, no new recording)
Needs: pip packages kokoro-onnx and soundfile (installed automatically if missing), ffmpeg (or imageio-ffmpeg),
and the Kokoro model files, downloaded once from GitHub into ~/.cache/seax-tts.
"""
import argparse, json, os, re, subprocess, sys, shutil, urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UK = ZoneInfo("Europe/London")
VOICE, SPEED, GAP = "bm_george", 1.12, 1.5
CACHE = os.path.expanduser("~/.cache/seax-tts")
MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
MODEL_FILES = {"kokoro-v1.0.onnx": 300_000_000, "voices-v1.0.bin": 25_000_000}
CHIME = os.path.join(ROOT, "assets", "audio", "chime.wav")
# Words the voice gets wrong. The site's name is said "See-Ax" (owner, 14 Nov 2026), never "seeks".
# Essex place names it gets wrong are fixed by sound, from tools/pronounce.json (owner, 17 Nov 2026).
SAY = [(r"\bthe\s+seax\.com\b", "the See-Ax dot com"), (r"\btheseax\.com\b", "the See-Ax dot com"), (r"\bSeax\b", "See-Ax")]


def need(pkg, mod=None):
    try:
        return __import__(mod or pkg)
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--break-system-packages", pkg], check=False)
        return __import__(mod or pkg)


def model_files():
    os.makedirs(CACHE, exist_ok=True)
    for name, minsize in MODEL_FILES.items():
        p = os.path.join(CACHE, name)
        if os.path.exists(p) and os.path.getsize(p) >= minsize:
            continue
        print("downloading", name, flush=True)
        tmp = p + ".part"
        for attempt in range(3):
            try:
                subprocess.run(["curl", "-sSL", "--retry", "3", "-o", tmp, MODEL_URL + name], check=True, timeout=600)
                break
            except Exception:
                try:
                    urllib.request.urlretrieve(MODEL_URL + name, tmp)
                    break
                except Exception as e:
                    if attempt == 2:
                        raise SystemExit(f"could not download {name}: {e}")
        if os.path.getsize(tmp) < minsize:
            raise SystemExit(f"{name} download looks incomplete")
        os.replace(tmp, p)
    return os.path.join(CACHE, "kokoro-v1.0.onnx"), os.path.join(CACHE, "voices-v1.0.bin")


def ffmpeg_bin():
    b = shutil.which("ffmpeg")
    if b:
        return b
    need("imageio-ffmpeg", "imageio_ffmpeg")
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def load_lexicon():
    """Essex place names the voice gets wrong (tools/pronounce.json, owner's request 17 Nov 2026): name -> sounds."""
    try:
        d = json.load(open(os.path.join(ROOT, "tools", "pronounce.json"), encoding="utf-8"))
        return {k: v["ipa"] for k, v in d.get("names", {}).items()}
    except Exception as e:
        print("WARNING: could not read tools/pronounce.json:", e, flush=True)
        return {}


def to_phonemes(tok, text, lex):
    """The paragraph as voice sounds, with every dictionary place name swapped for its correct sounds.
    Returns None when the paragraph has no dictionary name (the voice then reads the text as before).
    The whole paragraph is voiced first, so the rhythm of the sentence stays natural, then the voice's own
    (wrong) sounds for each name are replaced. If a name cannot be found that way, the text is voiced
    in pieces around the names instead."""
    if not lex:
        return None
    names = sorted(lex, key=len, reverse=True)
    rx = re.compile(r"\b(" + "|".join(re.escape(n) for n in names) + r")('s|’s)?\b", re.I)
    found = [(m.group(1), bool(m.group(2))) for m in rx.finditer(text)]
    if not found:
        return None
    low = {n.lower(): n for n in names}
    ph = tok.phonemize(text, "en-gb")
    ok = True
    for name, poss in sorted(set(found), key=lambda x: -len(x[0])):
        good = lex[low[name.lower()]] + ("z" if poss else "")
        bad = tok.phonemize(name + ("'s" if poss else ""), "en-gb")
        hit = re.compile(r"(?<![^\s,.;:!?])" + re.escape(bad) + r"(?![^\s,.;:!?])")
        if hit.search(ph):
            ph = hit.sub(good, ph)
        else:
            ok = False
    if ok:
        return ph
    out, pos = [], 0
    for m in rx.finditer(text):
        chunk = text[pos:m.start()]
        if chunk.strip():
            out.append(tok.phonemize(chunk, "en-gb"))
        out.append(lex[low[m.group(1).lower()]] + ("z" if m.group(2) else ""))
        pos = m.end()
    if text[pos:].strip():
        out.append(tok.phonemize(text[pos:], "en-gb"))
    return re.sub(r"\s+([,.;:!?])", r"\1", " ".join(p for p in out if p))


def paragraphs(text):
    text = text.replace("—", ", ").replace("–", " to ")
    for pat, rep in SAY:
        text = re.sub(pat, rep, text, flags=re.I)
    return [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def render(paras, out_wav):
    np = need("numpy")
    sf = need("soundfile")
    need("kokoro-onnx", "kokoro_onnx")
    from kokoro_onnx import Kokoro
    m, v = model_files()
    k = Kokoro(m, v)
    lex = load_lexicon()
    chunks, sr = [], 24000
    for i, p in enumerate(paras):
        ph = to_phonemes(k.tokenizer, p, lex)
        if ph:
            s, sr = k.create(ph, voice=VOICE, speed=SPEED, lang="en-gb", is_phonemes=True)
        else:
            s, sr = k.create(p, voice=VOICE, speed=SPEED, lang="en-gb")
        idx = np.where(np.abs(s) > 0.01)[0]
        if len(idx):   # trim the model's own lead-in and tail so every gap is exactly GAP seconds
            s = s[max(idx[0] - int(0.03 * sr), 0): idx[-1] + int(0.08 * sr)]
        chunks.append(s)
        if i < len(paras) - 1:
            chunks.append(np.zeros(int(sr * GAP), dtype=s.dtype))
        print(f"  para {i+1}/{len(paras)} done", flush=True)
    sf.write(out_wav, np.concatenate(chunks), sr)


def peaks(ff, mp3, n=72):
    """Loudness of n slices of the finished file, 0..1, for the player's waveform."""
    raw = subprocess.run([ff, "-v", "error", "-i", mp3, "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    import array
    a = array.array("h"); a.frombytes(raw)
    if not a:
        return []
    step = max(1, len(a) // n)
    vals = []
    for i in range(n):
        seg = a[i * step:(i + 1) * step]
        vals.append((sum(x * x for x in seg[::4]) / max(1, len(seg[::4]))) ** 0.5 if seg else 0)
    top = max(vals) or 1
    return [round(max(0.08, (x / top) ** 0.7), 2) for x in vals]


SITE = "https://theseax.com"
UKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def write_alexa(meta):
    """Alexa Flash Briefing feed: one audio item for the latest bulletin (Amazon ignores items over 7 days old)."""
    import uuid
    d = datetime.strptime(meta["date"], "%Y-%m-%d")
    when = f'{UKDAYS[d.weekday()]} {d.day} {d.strftime("%B")}'
    # owner's names (17 Nov 2026): morning, afternoon, evening and overnight; the overnight one carries no date
    name = {"am": "morning update", "mid": "afternoon update", "pm": "evening update"}.get(meta.get("slot"))
    title = f"The Seax overnight bulletin" if meta.get("slot") == "night" else f"The Seax {name or 'latest bulletin'}, {when}"
    item = {
        "uid": "urn:uuid:" + str(uuid.uuid5(uuid.NAMESPACE_URL, SITE + meta["file"] + "#" + meta["madeAt"])),
        "updateDate": meta["madeAt"],
        "titleText": title,
        "mainText": "",
        "streamUrl": SITE + meta["file"],
        "redirectionUrl": SITE + "/",
    }
    with open(os.path.join(ROOT, "audio", "alexa.json"), "w", encoding="utf-8") as fh:
        json.dump([item], fh, ensure_ascii=False, indent=1)
    print("WROTE audio/alexa.json")


def write_podcast(meta):
    """Podcast feed (podcast.xml) for Apple Podcasts, Spotify and other apps: the bulletins still on the site, newest first."""
    from email.utils import format_datetime
    from xml.sax.saxutils import escape as X
    lp = os.path.join(ROOT, "data", "podcast.json")
    eps = json.load(open(lp, encoding="utf-8")) if os.path.exists(lp) else []
    d = datetime.strptime(meta["date"], "%Y-%m-%d")
    when = f'{UKDAYS[d.weekday()]} {d.day} {d.strftime("%B %Y")}'
    name = {"am": "Morning update", "mid": "Afternoon update", "pm": "Evening update", "night": "Overnight bulletin"}.get(meta.get("slot"), "Latest bulletin")
    fp = os.path.join(ROOT, meta["file"].lstrip("/"))
    eps = [e for e in eps if e.get("file") != meta["file"]]
    eps.insert(0, {"file": meta["file"], "title": f"{name}: {when}", "madeAt": meta["madeAt"], "duration": int(round(meta.get("duration") or 0)),
                   "bytes": os.path.getsize(fp) if os.path.exists(fp) else 0})
    eps = [e for e in eps if os.path.exists(os.path.join(ROOT, e["file"].lstrip("/")))][:8]
    with open(lp, "w", encoding="utf-8") as fh:
        json.dump(eps, fh, ensure_ascii=False, indent=1)
    desc = "Essex news in two minutes from The Seax: the county's main stories, sport and weather, four times a day. Produced with AI from the reporting on theseax.com."
    out = [f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel>
<title>The Seax: Essex News Bulletin</title>
<link>{SITE}/</link>
<atom:link href="{SITE}/podcast.xml" rel="self" type="application/rss+xml"/>
<language>en-gb</language>
<description>{X(desc)}</description>
<itunes:summary>{X(desc)}</itunes:summary>
<itunes:author>The Seax</itunes:author>
<itunes:owner><itunes:name>The Seax</itunes:name><itunes:email>info@theseax.com</itunes:email></itunes:owner>
<itunes:image href="{SITE}/img/podcast-cover.jpg"/>
<image><url>{SITE}/img/podcast-cover.jpg</url><title>The Seax: Essex News Bulletin</title><link>{SITE}/</link></image>
<itunes:category text="News"><itunes:category text="Daily News"/></itunes:category>
<itunes:explicit>false</itunes:explicit>
<itunes:type>episodic</itunes:type>
<copyright>The Seax</copyright>"""]
    for e in eps:
        t = datetime.strptime(e["madeAt"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        out.append(f"""<item>
<title>{X(e["title"])}</title>
<description>{X("The latest Essex news bulletin from The Seax. Full stories at theseax.com.")}</description>
<link>{SITE}/</link>
<guid isPermaLink="false">{X(SITE + e["file"] + "#" + e["madeAt"])}</guid>
<pubDate>{format_datetime(t)}</pubDate>
<enclosure url="{SITE}{e["file"]}" length="{e["bytes"]}" type="audio/mpeg"/>
<itunes:duration>{e["duration"]}</itunes:duration>
<itunes:explicit>false</itunes:explicit>
</item>""")
    out.append("</channel>\n</rss>\n")
    with open(os.path.join(ROOT, "podcast.xml"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))


def main():
    ap = argparse.ArgumentParser()
    if "--check-names" in sys.argv:
        # print how each paragraph will be voiced, marking the dictionary names (no audio made)
        need("kokoro-onnx", "kokoro_onnx")
        from kokoro_onnx.tokenizer import Tokenizer
        tok, lex = Tokenizer(), load_lexicon()
        src = sys.argv[sys.argv.index("--check-names") + 1]
        for p in paragraphs(open(src, encoding="utf-8").read()):
            print(to_phonemes(tok, p, lex) or tok.phonemize(p, "en-gb"), "\n")
        return
    if "--alexa-only" in sys.argv:
        write_alexa(json.load(open(os.path.join(ROOT, "data", "bulletin.json"), encoding="utf-8")))
        return
    ap.add_argument("--script", required=True)
    ap.add_argument("--stories", default="", help="comma-separated ids of the stories read out, in order")
    ap.add_argument("--date", default="", help="UK date YYYY-MM-DD (default: today)")
    ap.add_argument("--slot", choices=["am", "mid", "pm", "night", "auto"], default="auto", help="morning (07:00), afternoon (12:30), evening (17:00, Sat 18:40) or overnight (23:00) bulletin; auto = by UK time now")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    now = datetime.now(timezone.utc)
    date = a.date or now.astimezone(UK).strftime("%Y-%m-%d")
    uk_h = now.astimezone(UK).hour
    slot = a.slot if a.slot != "auto" else ("am" if 4 <= uk_h < 11 else "mid" if 11 <= uk_h < 15 else "pm" if 15 <= uk_h < 21 else "night")
    paras = paragraphs(open(a.script, encoding="utf-8").read())
    if len(paras) < 3:
        raise SystemExit("script too short: need the welcome, some stories and a sign-off, separated by blank lines")
    words = sum(len(p.split()) for p in paras)
    print(f"{len(paras)} paragraphs, {words} words", flush=True)

    ff = ffmpeg_bin()
    tmp_wav = "/tmp/seax-bulletin-voice.wav"
    render(paras, tmp_wav)
    rel = f"audio/bulletin-{date}-{slot}.mp3"
    out = "/tmp/" + os.path.basename(rel) if a.dry_run else os.path.join(ROOT, rel)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    chime = ["-i", CHIME] if os.path.exists(CHIME) else []
    if chime:
        fc = "[1]loudnorm=I=-14:TP=-2.5,aresample=24000,apad=pad_dur=0.6[v];[0]aresample=24000[c0];[2]aresample=24000[c1];[c0][v][c1]concat=n=3:v=0:a=1,loudnorm=I=-14:TP=-3.5[a]"
        cmd = [ff, "-y", "-v", "error", *chime, "-i", tmp_wav, *chime, "-filter_complex", fc, "-map", "[a]"]
    else:
        cmd = [ff, "-y", "-v", "error", "-i", tmp_wav, "-af", "loudnorm=I=-14:TP=-3.5"]
    # 256 kbps mono, 44.1 kHz: Amazon's Alexa Flash Briefing spec (owner's choice, 14 Nov 2026; about 4.5 MB a bulletin)
    subprocess.run(cmd + ["-ar", "44100", "-ac", "1", "-b:a", "256k", out], check=True)
    probe = shutil.which("ffprobe")
    if probe:
        dur = float(subprocess.run([probe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", out],
                                   capture_output=True, text=True, check=True).stdout.strip())
    else:
        info = subprocess.run([ff, "-i", out], capture_output=True, text=True).stderr
        h, mnt, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", info).groups()
        dur = int(h) * 3600 + int(mnt) * 60 + float(s)
    print(f"duration {int(dur//60)}:{int(dur%60):02d}", flush=True)
    if not 75 <= dur <= 200:
        print("WARNING: bulletin is outside the 1:15 to 3:20 range; check the script length", flush=True)
    if a.dry_run:
        print("DRY RUN, wrote", out)
        return

    # keep the newest 8 bulletins (two days) so the podcast feed has recent episodes; older ones are deleted so the
    # repository does not keep piling up files (podcast feed added 20 Nov 2026)
    olds = sorted([f for f in os.listdir(os.path.join(ROOT, "audio")) if f.startswith("bulletin-") and f.endswith(".mp3") and f != os.path.basename(rel)],
                  key=lambda f: os.path.getmtime(os.path.join(ROOT, "audio", f)), reverse=True)
    for f in olds[7:]:
        os.remove(os.path.join(ROOT, "audio", f))
    meta = {
        "date": date,
        "slot": slot,
        "file": "/" + rel,
        "duration": round(dur, 1),
        "madeAt": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "title": "Latest Essex News Bulletin",
        "voice": VOICE,
        "stories": [s.strip() for s in a.stories.split(",") if s.strip()],
        "peaks": peaks(ff, out),
    }
    with open(os.path.join(ROOT, "data", "bulletin.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=1)
    print("WROTE", rel, "and data/bulletin.json")
    write_alexa(meta)
    try:
        write_podcast(meta)
    except Exception as e:  # the podcast feed must never stop a bulletin
        print("podcast feed not written:", type(e).__name__, e, flush=True)


if __name__ == "__main__":
    main()
