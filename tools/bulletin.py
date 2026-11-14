#!/usr/bin/env python3
"""The Seax daily audio bulletin (owner's request, 14 Nov 2026).

Turns a spoken script into the MP3 that the "Listen" player on the front page plays.
The script is written twice a day, at 07:00 and 17:00 UK time, by the bulletin desk (see ops/bulletin.md).
(Owner first asked for 09:00 on 14 Nov 2026, then the same day moved it to 07:00 and 17:00, with the Saturday evening one at 18:40 for the football scores.)

  python3 tools/bulletin.py --script /tmp/bulletin.txt --stories id1,id2,id3
  python3 tools/bulletin.py --script /tmp/bulletin.txt --dry-run     (render to /tmp only, change nothing)

Script format: plain text, one story per paragraph, paragraphs separated by a blank line.
The owner's house style for the audio:
  - voice: Kokoro "bm_george" (British male) at speed 1.12 (owner chose the male v3 voice, 14 Nov 2026)
  - exactly 1.5 seconds of silence between paragraphs (owner's choice)
  - a soft chime (assets/audio/chime.wav) at the start and the end
Writes:
  audio/bulletin-YYYY-MM-DD-am.mp3 or -pm.mp3   (older bulletins are deleted, so the repository does not keep piling up files)
  data/bulletin.json              what the player reads: date, slot (am/pm), file, duration, waveform peaks, story ids
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
    chunks, sr = [], 24000
    for i, p in enumerate(paras):
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
    when = f'{UKDAYS[d.weekday()]} {"morning" if meta["slot"] == "am" else "evening"}, {d.day} {d.strftime("%B")}'
    item = {
        "uid": "urn:uuid:" + str(uuid.uuid5(uuid.NAMESPACE_URL, SITE + meta["file"] + "#" + meta["madeAt"])),
        "updateDate": meta["madeAt"],
        "titleText": f"The Seax Essex News Bulletin, {when}",
        "mainText": "",
        "streamUrl": SITE + meta["file"],
        "redirectionUrl": SITE + "/",
    }
    with open(os.path.join(ROOT, "audio", "alexa.json"), "w", encoding="utf-8") as fh:
        json.dump([item], fh, ensure_ascii=False, indent=1)
    print("WROTE audio/alexa.json")


def main():
    ap = argparse.ArgumentParser()
    if "--alexa-only" in sys.argv:
        write_alexa(json.load(open(os.path.join(ROOT, "data", "bulletin.json"), encoding="utf-8")))
        return
    ap.add_argument("--script", required=True)
    ap.add_argument("--stories", default="", help="comma-separated ids of the stories read out, in order")
    ap.add_argument("--date", default="", help="UK date YYYY-MM-DD (default: today)")
    ap.add_argument("--slot", choices=["am", "pm", "auto"], default="auto", help="morning (07:00) or evening (17:00) bulletin; auto = by UK time now")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    now = datetime.now(timezone.utc)
    date = a.date or now.astimezone(UK).strftime("%Y-%m-%d")
    slot = a.slot if a.slot != "auto" else ("am" if now.astimezone(UK).hour < 12 else "pm")
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

    for f in os.listdir(os.path.join(ROOT, "audio")):
        if f.startswith("bulletin-") and f.endswith(".mp3") and f != os.path.basename(rel):
            os.remove(os.path.join(ROOT, "audio", f))
    meta = {
        "date": date,
        "slot": slot,
        "file": "/" + rel,
        "duration": round(dur, 1),
        "madeAt": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "title": "Essex News Bulletin, " + ("morning" if slot == "am" else "evening"),
        "voice": VOICE,
        "stories": [s.strip() for s in a.stories.split(",") if s.strip()],
        "peaks": peaks(ff, out),
    }
    with open(os.path.join(ROOT, "data", "bulletin.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=1)
    print("WROTE", rel, "and data/bulletin.json")
    write_alexa(meta)


if __name__ == "__main__":
    main()
