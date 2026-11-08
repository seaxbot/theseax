#!/usr/bin/env python3
"""Apply the source policy (tools/policy.py) to story pages that are no longer in the edition.

tools/build.py rebuilds pages for stories in the current edition, so those always follow the policy.
Older pages stay online as they were built. Run this after changing tools/sources-policy.json
(for example after an opt-out request) to bring the older pages into line:

    python3 tools/policy_pages.py           # report and rewrite
    python3 tools/policy_pages.py --dry-run # report only

Pages from an excluded outlet are not deleted here: add their ids to tools/takedown.txt instead,
and this script lists them for you.
"""
import html, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import policy

BODY_LINE = re.compile(r"^  ((?:<p>.*?</p>)+)$", re.M)
POINTS = re.compile(r'<h2>Key points</h2><ul class="points">(.*?)</ul>', re.S)
READ_FULL = re.compile(r'<div class="readfull">.*?<a class="go" href="([^"]+)"', re.S)
ALSO = re.compile(r'<ul class="also">(.*?)</ul>', re.S)


def main():
    dry = "--dry-run" in sys.argv
    pol = policy.load_policy()
    ed = json.load(open(os.path.join(ROOT, "edition.json"), encoding="utf-8"))
    archive = json.load(open(os.path.join(ROOT, "data", "archive.json"), encoding="utf-8"))
    current = set()
    for k in ("stories", "official", "courts", "community", "councilwatch"):
        current |= {x.get("id") for x in ed.get(k) or [] if isinstance(x, dict)}
    current |= {x.get("id") for x in (ed.get("sport") or {}).get("stories") or [] if isinstance(x, dict)}
    report = {"linkOnly": [], "capped": [], "exclude": [], "unchanged": 0}
    for sid, rec in sorted(archive.items()):
        if sid in current or rec.get("sec") == "councilwatch":
            continue
        path = os.path.join(ROOT, "story", sid, "index.html")
        if not os.path.exists(path):
            continue
        page = open(path, encoding="utf-8").read()
        m = READ_FULL.search(page)
        main = policy.host(html.unescape(m.group(1))) if m else ""
        also = []
        am = ALSO.search(page)
        if am:
            also = [policy.host(html.unescape(u)) for u in re.findall(r'href="([^"]+)"', am.group(1))]
        if policy.on(main, pol["exclude"]):
            report["exclude"].append(sid)
            continue
        also = [h for h in also if h and not policy.on(h, pol["exclude"])]
        hosts = {h for h in [main] + also if h}
        new = page
        if hosts and all(policy.on(h, pol["linkOnly"]) for h in hosts):
            new = BODY_LINE.sub("", new, count=1)
            new = POINTS.sub("", new, count=1)
            kind = "linkOnly"
        elif (len(hosts) <= 1 and not policy.official(main)) or policy.on(main, pol["linkOnly"]):
            bm = BODY_LINE.search(new)
            if bm:
                paras = [html.unescape(p) for p in re.findall(r"<p>(.*?)</p>", bm.group(1))]
                capped = policy.cap_body(paras)
                if capped != paras:
                    line = "  " + "".join(f"<p>{html.escape(p, quote=False)}</p>" for p in capped)
                    new = new[:bm.start()] + line + new[bm.end():]
            pm = POINTS.search(new)
            if pm:
                lis = re.findall(r"<li>.*?</li>", pm.group(1), re.S)
                if len(lis) > 3:
                    new = new[:pm.start()] + '<h2>Key points</h2><ul class="points">' + "".join(lis[:3]) + "</ul>" + new[pm.end():]
            kind = "capped"
        else:
            report["unchanged"] += 1
            continue
        if new != page:
            report[kind].append(sid)
            if not dry:
                open(path, "w", encoding="utf-8").write(new)
        else:
            report["unchanged"] += 1
    print(json.dumps({k: (v if isinstance(v, int) else len(v)) for k, v in report.items()}))
    for k in ("linkOnly", "capped", "exclude"):
        if report[k]:
            print(k + ":", " ".join(report[k]))
    if report["exclude"]:
        print("Add the 'exclude' ids above to tools/takedown.txt to remove those pages.")


if __name__ == "__main__":
    main()
