#!/usr/bin/env python3
"""The Seax source and copyright policy (owner's rule, Nov 2026).

Applied to every edition by tools/publish.py before it goes live, and again by tools/build.py
before story pages are built, so the rules hold even if a desk forgets them:

  1. Features are switched off: the edition's "features" list is always empty.
  2. Excluded outlets (tools/sources-policy.json "exclude"): items whose main url is from one of
     these outlets are dropped, and their links are removed from every "also" list.
  3. Link-only outlets ("linkOnly"): when every source of an item is a link-only outlet, the item
     keeps only our own headline and a one-sentence summary that links to the original. No body,
     no key points.
  4. Single-source cap: when an item's only source is one news outlet (not an official body and
     with no second outlet in "also"), or its main source is a link-only outlet, its body is cut
     to at most MAX_WORDS words in total (whole paragraphs and sentences, from the top) and at
     most 3 key points, so it never retells the original article.

Council Watch items are our own reporting from public council papers and are left alone.
Run directly to check a file:  python3 tools/policy.py edition.json
"""
import json, os, re, sys
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POLICY_FILE = os.path.join(ROOT, "tools", "sources-policy.json")
MAX_WORDS = 100

# Official bodies publish to inform the public; summarising their releases in full is fine.
OFFICIAL_SUFFIXES = (".gov.uk", ".police.uk", ".nhs.uk", ".ac.uk", ".sch.uk", ".mod.uk", ".gov")
OFFICIAL_HOSTS = {"parliament.uk", "judiciary.uk", "nationalhighways.co.uk", "essexhighways.org",
                  "travelessex.co.uk", "greateranglia.co.uk", "c2c-online.co.uk", "firstbus.co.uk",
                  "essexpoliceuk.substack.com", "content.govdelivery.com", "metoffice.gov.uk",
                  "essexprepared.co.uk", "essex-fire.gov.uk"}


def load_policy():
    try:
        with open(POLICY_FILE, encoding="utf-8") as f:
            p = json.load(f)
    except Exception:
        p = {}
    norm = lambda xs: sorted({str(x).lower().strip().lstrip(".").removeprefix("www.") for x in (xs or []) if str(x).strip()})
    return {"linkOnly": norm(p.get("linkOnly")), "exclude": norm(p.get("exclude"))}


def host(u):
    try:
        h = (urlparse(str(u or "")).hostname or "").lower()
    except Exception:
        return ""
    return h[4:] if h.startswith("www.") else h


def on(h, domains):
    return bool(h) and any(h == d or h.endswith("." + d) for d in domains)


def official(h):
    return bool(h) and (h in OFFICIAL_HOSTS or any(h.endswith(s) for s in OFFICIAL_SUFFIXES)
                        or any(h.endswith("." + o) for o in OFFICIAL_HOSTS))


def cap_words(text, n=MAX_WORDS):
    """Keep whole sentences up to about n words."""
    words = str(text).split()
    if len(words) <= n:
        return str(text).strip()
    out = []
    for s in re.split(r"(?<=[.!?])\s+", str(text).strip()):
        if out and len(" ".join(out + [s]).split()) > n:
            break
        out.append(s)
    res = " ".join(out)
    if len(res.split()) > n:  # one very long sentence: cut at a word boundary
        res = " ".join(words[:n]).rstrip(",;:") + "."
    return res


def cap_body(paras, n=MAX_WORDS):
    """Whole paragraphs from the top while they fit in n words; the paragraph that overflows is cut by sentence."""
    out, used = [], 0
    for p in paras:
        w = len(p.split())
        if used + w <= n:
            out.append(p); used += w; continue
        rest = n - used
        if rest >= 25 or not out:
            cut = cap_words(p, max(rest, 25))
            if cut:
                out.append(cut)
        break
    return out


def apply(ed, pol=None):
    """Apply the policy to an edition in place. Returns a small report dict."""
    pol = pol or load_policy()
    rep = {"featuresRemoved": len(ed.get("features") or []), "excluded": [], "linkOnly": [], "capped": []}
    ed["features"] = []
    sport = ed.get("sport") if isinstance(ed.get("sport"), dict) else {}
    sections = [("stories", ed), ("official", ed), ("courts", ed), ("community", ed), ("stories", sport)]
    for key, holder in sections:
        items = holder.get(key)
        if not isinstance(items, list):
            continue
        kept = []
        for it in items:
            if not isinstance(it, dict):
                kept.append(it); continue
            main = host(it.get("url"))
            if on(main, pol["exclude"]):
                rep["excluded"].append(it.get("id")); continue
            also = [a for a in (it.get("also") or []) if isinstance(a, dict)]
            also = [a for a in also if not on(host(a.get("url")), pol["exclude"])]
            if "also" in it:
                it["also"] = also
            hosts = {h for h in [main] + [host(a.get("url")) for a in also] if h}
            if hosts and all(on(h, pol["linkOnly"]) for h in hosts):
                if it.get("body") or it.get("points") or not it.get("linkOnly"):
                    rep["linkOnly"].append(it.get("id"))
                it.pop("body", None)
                it["points"] = []
                if it.get("summary"):
                    it["summary"] = cap_words(re.split(r"(?<=[.!?])\s+", str(it["summary"]).strip())[0], 40)
                it["linkOnly"] = True
            elif (len(hosts) <= 1 and not official(main)) or on(main, pol["linkOnly"]):
                body = [str(p).strip() for p in (it.get("body") if isinstance(it.get("body"), list) else []) if str(p).strip()]
                pts = it.get("points") if isinstance(it.get("points"), list) else []
                new = cap_body(body)
                if new != body or len(pts) > 3:
                    rep["capped"].append(it.get("id"))
                if body:
                    it["body"] = new
                it["points"] = pts[:3]
                it["singleSource"] = True
            else:
                it.pop("singleSource", None)
            kept.append(it)
        holder[key] = kept
    # front and lead must still point at stories that exist
    ids = {s.get("id") for s in ed.get("stories") or [] if isinstance(s, dict)}
    if isinstance(ed.get("front"), list):
        ed["front"] = [i for i in ed["front"] if i in ids]
    return rep


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "edition.json")
    ed = json.load(open(path, encoding="utf-8"))
    r = apply(ed)
    print(json.dumps({k: (v if isinstance(v, int) else len(v)) for k, v in r.items()}),
          "\nlinkOnly:", r["linkOnly"], "\ncapped:", r["capped"], "\nexcluded:", r["excluded"])
