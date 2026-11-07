#!/usr/bin/env python3
"""Council Watch desk helper. Keeps the AI part of each run small.

  python3 tools/councilwatch/desk.py prep  [--inbox DIR] [--max 18]   -> /tmp/cw_shortlist.json, printed compactly
  python3 tools/councilwatch/desk.py publish /tmp/cw_new.json          -> merges, validates and publishes

prep    reads the collector's inbox (councilwatch-data branch), drops anything already covered
        (by cwKey, from data/archive.json and the live edition), and lists the strongest agenda items
        with their decision text, report excerpts and document links.
publish takes the stories the desk wrote, fills the fixed fields from the shortlist (ids, council,
        meeting, documents, areas), keeps recent Council Watch stories, and runs tools/publish.py --councilwatch.
"""
import json, os, re, subprocess, sys, unicodedata
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NOW = datetime.now(timezone.utc)
SHORT = "/tmp/cw_shortlist.json"
KEEP_DAYS = 21
MAX_LIVE = 40
STAGES = {"decided", "upcoming", "proposed", "held", "update"}
AREA_KEYS = {"all", "chelmsford", "colchester", "southend", "south", "brentwood", "braintree", "maldon", "tendring", "uttlesford", "epping"}

def load(p, default=None):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return default

def slug(s, n=60):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:n].rstrip("-")

def covered_keys():
    keys = set()
    for rec in (load(os.path.join(ROOT, "data", "archive.json"), {}) or {}).values():
        if rec.get("cwKey"):
            keys.add(rec["cwKey"])
    for it in (load(os.path.join(ROOT, "edition.json"), {}) or {}).get("councilwatch", []) or []:
        if it.get("cwKey"):
            keys.add(it["cwKey"])
    return keys

def nice_date(iso):
    try:
        d = datetime.fromisoformat(iso)
        return d.strftime("%-d %b %Y")
    except Exception:
        return iso

def prep(inbox_dir, maximum):
    inbox = load(os.path.join(inbox_dir, "inbox.json"), {}) or {}
    status = (load(os.path.join(inbox_dir, "status.json"), {}) or {}).get("councils", {})
    done = covered_keys()
    rows = []
    for m in inbox.get("meetings", []):
        if m.get("cancelled"):
            continue
        for it in m.get("items", []):
            key = f'{m["council"]}:{m["key"].split(":", 1)[1]}:{it.get("num") or slug(it.get("title", ""), 20)}'
            if key in done or it.get("score", 0) < 6:
                continue
            rows.append({
                "cwKey": key, "score": it["score"] + (5 if m["stage"] == "decided" else 0) + (2 if m.get("changed") else 0),
                "council": m["council"], "councilName": m["councilName"], "area": m["area"],
                "meeting": f'{m["committee"]}, {nice_date(m["date"])}', "meetingDate": m["date"], "meetingUrl": m["url"], "stage": m["stage"],
                "item": f'{it.get("num", "")} {it.get("title", "")}'.strip(),
                "text": (it.get("text") or "")[:2500],
                "docs": [{"title": d["title"], "url": d["url"]} for d in it.get("docs", [])[:4]],
                "excerpt": (it.get("excerpt") or "")[:5000], "excerptOf": it.get("excerptOf", ""),
            })
    rows.sort(key=lambda r: -r["score"])
    seen_items, uniq = set(), []
    for r in rows:  # joint meetings list the same report twice
        k = (r["council"], re.sub(r"\W+", "", r["item"].split(" ", 1)[-1].lower())[:80], r["meetingDate"])
        if k not in seen_items:
            seen_items.add(k); uniq.append(r)
    rows = uniq
    # no more than 4 items from one council, so the whole county gets a look in
    per, out = {}, []
    for r in rows:
        if per.get(r["council"], 0) >= 4:
            continue
        per[r["council"]] = per.get(r["council"], 0) + 1
        out.append(r)
        if len(out) >= maximum:
            break
    manual = {cid: {"name": s.get("name"), "base": s.get("base"), "state": s.get("state"), "note": s.get("note")}
              for cid, s in status.items() if s.get("state") not in ("ok", "quiet")}
    json.dump({"at": NOW.isoformat(), "inboxAt": inbox.get("at"), "items": out, "searchCouncils": manual}, open(SHORT, "w"), ensure_ascii=False, indent=1)
    print(f"SHORTLIST {len(out)} items (inbox {inbox.get('at')}), {len(done)} already covered. Councils to check by search: "
          + ", ".join(f'{v["name"]} ({v["state"]})' for v in manual.values()))
    for i, r in enumerate(out, 1):
        print(f"\n### {i}. [{r['cwKey']}] score {r['score']} | {r['councilName']} | {r['meeting']} | stage {r['stage']}")
        print(f"ITEM: {r['item']}")
        if r["text"].strip():
            print("AGENDA/DECISION TEXT:\n" + r["text"].strip()[:2500])
        if r["excerpt"]:
            print(f"REPORT EXCERPT ({r['excerptOf']}):\n" + r["excerpt"][:5000])
        for d in r["docs"]:
            print(f"DOC: {d['title']} | {d['url']}")
        print(f"MEETING PAGE: {r['meetingUrl']}")

def publish(new_path):
    short = {r["cwKey"]: r for r in (load(SHORT, {}) or {}).get("items", [])}
    new = load(new_path, [])
    if isinstance(new, dict):
        new = new.get("councilwatch") or new.get("items") or []
    live = (load(os.path.join(ROOT, "edition.json"), {}) or {}).get("councilwatch", []) or []
    out, problems = [], []
    ids = {it.get("id") for it in live}
    for st in new:
        key = st.get("cwKey", "")
        src = short.get(key)
        if not src and not st.get("council"):
            problems.append(f"{key or st.get('headline','?')}: not in the shortlist and no council given; skipped")
            continue
        src = src or {}
        body = [p for p in (st.get("body") or []) if str(p).strip()]
        if not st.get("headline") or not st.get("summary") or len(body) < 2:
            problems.append(f"{key}: needs headline, summary and at least 2 body paragraphs; skipped")
            continue
        if re.search("—", json.dumps(st, ensure_ascii=False)):
            problems.append(f"{key}: contains an em dash; replaced with a comma")
            st = json.loads(json.dumps(st, ensure_ascii=False).replace(" — ", ", ").replace("—", ", "))
            body = [p for p in (st.get("body") or []) if str(p).strip()]
        council = st.get("council") or src.get("council")
        hs = slug(st["headline"], 70)
        for w in (council, slug(st.get("councilName") or src.get("councilName") or "", 30)):
            if w and hs.startswith(w + "-"):
                hs = hs[len(w) + 1:]
        hs = re.sub(r"^s-", "", hs)[:56].rstrip("-")
        sid = st.get("id") or f"cw-{council}-{hs}"
        while sid in ids:
            sid += "-2"
        ids.add(sid)
        docs = st.get("docs") or src.get("docs") or []
        docs = [d for d in docs if isinstance(d, dict) and str(d.get("url", "")).startswith("http")]
        area = src.get("area") or "all"
        areas = [a for a in (st.get("areas") or [area]) if a in AREA_KEYS] or ["all"]
        stage = st.get("stage") or src.get("stage") or "update"
        out.append({
            "id": sid, "cwKey": key or sid, "tag": "Council Watch", "icon": "council", "kind": "council",
            "council": council, "councilName": st.get("councilName") or src.get("councilName") or council,
            "meeting": st.get("meeting") or src.get("meeting") or "", "meetingUrl": st.get("meetingUrl") or src.get("meetingUrl") or "",
            "stage": stage if stage in STAGES else "update",
            "headline": st["headline"].strip(), "summary": st["summary"].strip(), "body": body[:4],
            "points": [p for p in (st.get("points") or []) if str(p).strip()][:5],
            "place": st.get("place") or src.get("councilName", "Essex"), "areas": areas,
            "docs": docs[:6], "url": (docs[0]["url"] if docs else st.get("meetingUrl") or src.get("meetingUrl") or ""),
            "source": st.get("councilName") or src.get("councilName") or "Essex council papers", "org": st.get("councilName") or src.get("councilName"),
            "weight": max(1, min(10, int(st.get("weight") or 5))), "time": st.get("time") or NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
        })
    cut = (NOW - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    keep = [it for it in live if (it.get("time") or "") >= cut and it.get("cwKey") not in {o["cwKey"] for o in out}]
    merged = sorted(out + keep, key=lambda x: x.get("time") or "", reverse=True)[:MAX_LIVE]
    for p in problems:
        print("NOTE", p)
    if not out:
        print("NOTHING NEW TO PUBLISH"); return
    json.dump(merged, open("/tmp/cw.json", "w"), ensure_ascii=False)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "publish.py"), "--councilwatch", "/tmp/cw.json"], capture_output=True, text=True,
                       env={**os.environ, "SEAX_NO_BRIEFING": "1"})
    print(r.stdout.strip()[-1500:], r.stderr.strip()[-800:])
    print(f"PUBLISHED {len(out)} new Council Watch stories ({len(merged)} live): " + ", ".join(o["id"] for o in out))
    sys.exit(r.returncode)

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("prep", "publish"):
        sys.exit(__doc__)
    if sys.argv[1] == "prep":
        a = sys.argv[2:]
        inbox = a[a.index("--inbox") + 1] if "--inbox" in a else "/tmp/cw-data"
        mx = int(a[a.index("--max") + 1]) if "--max" in a else 18
        prep(inbox, mx)
    else:
        publish(sys.argv[2])
