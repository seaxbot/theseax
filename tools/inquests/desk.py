#!/usr/bin/env python3
"""Inquest desk helper (owner's request, 13 Nov 2026). Run from the repository checkout.

  python3 tools/inquests/desk.py prep /tmp/inq-data     print the day's shortlist from the collector's inquests.json

The shortlist has three parts:
  TODAY AND NEXT 7 DAYS   inquest hearings, pre-inquest reviews and openings coming up (preview / on-the-day stories)
  RECENT OUTCOMES         inquest hearings held in the last 10 days with a conclusion on the list (follow-up stories)
  ALREADY COVERED         inquest desk ids already in edition.json or data/archive.json
Cases whose listed conclusion is suicide are never shown (owner's rule: no suicide or self-harm stories).
"""
import json, os, re, sys
from datetime import datetime, timezone, timedelta, date
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UK = ZoneInfo("Europe/London")
SUICIDE_RX = re.compile(r"suicid|self[- ]?harm|took (his|her|their) own life", re.I)
ESSEX_RX = re.compile(r"\b(essex|southend|thurrock)\b", re.I)


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def desk_id(c):
    sur = c["listedName"].split()[0] if c["listedName"].split() and c["listedName"].split()[0].isupper() else c["name"].split()[-1]
    d = (c.get("deathDate") or "").replace("-", "") or slug(c.get("deathRaw") or "")
    return f"ct-inq-{slug(sur)}-{d}"


def age_flag(age):
    a = (age or "").lower()
    if not a:
        return "age not listed"
    if any(w in a for w in ("day", "week", "month", "less than", "hour")):
        return "CHILD (infant)"
    m = re.search(r"\d+", a)
    if m and int(m.group(0)) < 18:
        return "CHILD (under 18)"
    return ""


def covered_ids():
    ids = set()
    try:
        ed = json.load(open(os.path.join(ROOT, "edition.json")))
        for k in ("stories", "courts", "official", "community"):
            ids |= {x.get("id", "") for x in ed.get(k) or []}
    except Exception:
        pass
    try:
        ids |= set(json.load(open(os.path.join(ROOT, "data", "archive.json"))).keys())
    except Exception:
        pass
    return {i for i in ids if i.startswith("ct-inq-")}


def line(c, today, now, cov):
    i = desk_id(c)
    flags = []
    af = age_flag(c.get("age"))
    if af:
        flags.append(af)
    if not ESSEX_RX.search(c.get("place") or ""):
        flags.append("DEATH OUTSIDE ESSEX (confirm an Essex link)")
    if c.get("hearingDays", 0) > 1:
        flags.append(f"{c['hearingDays']}-day hearing")
    if any("pre inquest" in t.lower() for t in c.get("types", [])):
        flags.append("pre-inquest review (complex case)")
    try:
        if datetime.fromisoformat(c["firstSeen"].replace("Z", "+00:00")) > now - timedelta(hours=30):
            flags.append("NEW on the list")
    except Exception:
        pass
    if i in cov:
        flags.append("ALREADY COVERED")
    hs = "; ".join(f"{h['date']} {h['time']} {h['type']} ({h['room']}, {h['venue']})" for h in c["hearings"])
    con = f" | conclusion listed: {c['conclusion']}" if c.get("conclusion") else ""
    return (f"[{i}] {c['name']} (listed as {c['listedName']}), {c.get('age') or '?'}, died {c.get('deathRaw') or '?'} "
            f"at {c.get('place') or '?'}{con}\n      url: {c.get('caseUrl') or ''}\n      hearings: {hs}" + (f"\n      flags: {', '.join(flags)}" if flags else ""))


def prep(data_dir):
    d = json.load(open(os.path.join(data_dir, "inquests.json")))
    now = datetime.now(timezone.utc)
    today = now.astimezone(UK).date()
    t0, t7, back10 = today.isoformat(), (today + timedelta(days=7)).isoformat(), (today - timedelta(days=10)).isoformat()
    cov = covered_ids()
    cases = d.get("cases") or []
    skipped = [c for c in cases if SUICIDE_RX.search(c.get("conclusion") or "")]
    cases = [c for c in cases if c not in skipped]
    print(f"Essex Coroner list collected {d.get('generated')} ({d.get('pagesRead')} pages, {len(d.get('rows') or [])} rows). "
          f"Source page: {d.get('source')}")
    print(f"UK date today: {t0}. Cases skipped because the listed conclusion is suicide: {len(skipped)}")
    up = [c for c in cases if any(t0 <= h["date"] <= t7 and not h["type"].lower().startswith("documentary") for h in c["hearings"])]
    up.sort(key=lambda c: min(h["date"] for h in c["hearings"] if h["date"] >= t0))
    hearings = [c for c in up if any(not h["type"].lower().startswith("opening") for h in c["hearings"] if h["date"] >= t0)]
    openings = [c for c in up if c not in hearings]
    print(f"\n== TODAY AND NEXT 7 DAYS: inquest hearings and pre-inquest reviews ({len(hearings)}) ==")
    for c in hearings:
        print(line(c, today, now, cov))
    print(f"\n== TODAY AND NEXT 7 DAYS: openings ({len(openings)}) ==")
    for c in openings:
        print(line(c, today, now, cov))
    out = [c for c in cases if c.get("conclusion") and any(back10 <= h["date"] < t0 and h["type"].lower().startswith("inquest hearing") for h in c["hearings"])]
    print(f"\n== RECENT OUTCOMES: hearings in the last 10 days with a conclusion listed ({len(out)}) ==")
    for c in out:
        print(line(c, today, now, cov))
    print(f"\n== ALREADY COVERED ({len(cov)}) ==\n" + ", ".join(sorted(cov)))


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "prep":
        prep(sys.argv[2])
    else:
        sys.exit(__doc__)
