#!/usr/bin/env python3
"""The Seax data desk (owner's go-ahead, 20 Nov 2026: build original, data-led Essex reporting, fully automated).

Runs on GitHub Actions once a day (.github/workflows/datadesk.yml) and costs the newsroom nothing: it reads open,
official datasets through their public APIs, works out what is new or unusual for Essex, and saves a short digest to
the branch "data-desk". The newsroom reads the digest once a day (ops/newsroom.md, DATA DESK) and writes a story only
when the figures are news. Every figure in the digest carries the link to its official source.

  food       Food Standards Agency hygiene ratings for the 14 Essex councils (api.ratings.food.gov.uk, Open
             Government Licence): premises newly rated 0 or 1, and each council's share of premises rated 0 to 2
  contracts  Contract awards published by Essex public bodies on Find a Tender and Contracts Finder (OCDS, Open
             Government Licence): who bought what, from whom, for how much
  prices     UK House Price Index for the 14 Essex council areas (HM Land Registry and ONS, Open Government Licence)
  petitions  The UK Parliament petitions with the most signatures (petition.parliament.uk, Open Parliament
             Licence): which ones Essex constituencies sign far more, or far less, than the country as a whole

Rules: official APIs only, identifies itself honestly, a handful of requests per source, standard library only,
never fails the whole run because one source is down. Output directory is argv[1] (default ./datadesk-out); the
previous run's files there are the state.
"""
import json, os, re, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta

UA = "TheSeaxNewsDesk/1.0 (+https://theseax.com/about/; info@theseax.com)"
NOW = datetime.now(timezone.utc)
ISO = "%Y-%m-%dT%H:%M:%SZ"
OUT = sys.argv[1] if len(sys.argv) > 1 else "datadesk-out"
ONLY = set(sys.argv[2:])  # optional: run only these parts

COUNCILS = ["Basildon", "Braintree", "Brentwood", "Castle Point", "Chelmsford", "Colchester", "Epping Forest", "Harlow",
            "Maldon", "Rochford", "Southend-On-Sea", "Tendring", "Thurrock", "Uttlesford"]
CONSTITUENCIES = ["Basildon and Billericay", "Braintree", "Brentwood and Ongar", "Castle Point", "Chelmsford", "Clacton",
                  "Colchester", "Epping Forest", "Harlow", "Harwich and North Essex", "Maldon", "North West Essex",
                  "Rayleigh and Wickford", "South Basildon and East Thurrock", "Southend East and Rochford",
                  "Southend West and Leigh", "Thurrock", "Witham"]
# public bodies whose contract awards are Essex news (matched against the buyer's name)
BUYER_RX = re.compile(
    r"\bEssex\b|Southend|Thurrock|Basildon|Braintree|Brentwood|Castle Point|Chelmsford|Colchester|Epping Forest|Harlow|"
    r"Maldon District|Rochford|Tendring|Uttlesford|Princess Alexandra Hospital|Anglia Ruskin|East Suffolk and North Essex|"
    r"Mid and South Essex|Stansted|Port of Tilbury|Harwich Haven|Writtle", re.I)
BUYER_NOT_RX = re.compile(r"Middlesex|Wessex|Sussex|Essex Street|Chelmsford (Massachusetts|MA)\b", re.I)
PLACE_RX = re.compile(
    r"\b(Essex|Southend|Thurrock|Basildon|Braintree|Brentwood|Canvey|Castle Point|Chelmsford|Colchester|Epping|Harlow|Maldon|"
    r"Rochford|Rayleigh|Clacton|Harwich|Tendring|Uttlesford|Saffron Walden|Dunmow|Stansted|Tilbury|Grays|Billericay|Wickford|"
    r"Witham|Halstead|Loughton|Waltham Abbey|Burnham-on-Crouch|Brightlingsea|Frinton|Walton-on-the-Naze|Lower Thames Crossing)\b", re.I)


def get(url, headers=None, data=None, timeout=30):
    h = {"User-Agent": UA, "Accept": "application/json"}
    h.update(headers or {})
    req = urllib.request.Request(url, headers=h, data=data)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def load(name, default):
    try:
        return json.load(open(os.path.join(OUT, name), encoding="utf-8"))
    except Exception:
        return default


def save(name, obj):
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def day(v):
    return str(v or "")[:10]


def uk_date(d):
    try:
        x = datetime.strptime(d[:10], "%Y-%m-%d")
        return f"{x.day} {x.strftime('%B %Y')}"
    except Exception:
        return d


# ---------------------------------------------------------------- food hygiene
FSA = "https://api.ratings.food.gov.uk"
FSA_H = {"x-api-version": "2"}


def food(state):
    auths = get(FSA + "/Authorities/basic", FSA_H).get("authorities") or []
    ids = {}
    for a in auths:
        nm = str(a.get("Name") or "")
        for c in COUNCILS:
            if nm.lower() == c.lower():
                ids[c] = a.get("LocalAuthorityId")
    missing = [c for c in COUNCILS if c not in ids]
    seen = state.setdefault("foodSeen", {})
    first_run = not seen
    cut = (NOW - timedelta(days=45)).strftime("%Y-%m-%d")
    new, table = [], []
    for c, aid in ids.items():
        counts = {}
        for rating in ("0", "1", "2", "3", "4", "5"):
            q = urllib.parse.urlencode({"localAuthorityId": aid, "ratingKey": rating, "ratingOperatorKey": "Equal", "pageSize": 1})
            try:
                counts[rating] = int(((get(f"{FSA}/Establishments?{q}", FSA_H).get("meta") or {}).get("totalCount")) or 0)
            except Exception as e:
                counts[rating] = None
            time.sleep(0.25)
        if all(v is not None for v in counts.values()) and sum(counts.values()):
            tot = sum(counts.values()); low = counts["0"] + counts["1"] + counts["2"]
            table.append({"council": c, "rated": tot, "zero": counts["0"], "one": counts["1"], "two": counts["2"], "five": counts["5"],
                          "lowPct": round(100 * low / tot, 1), "fivePct": round(100 * counts["5"] / tot, 1)})
        q = urllib.parse.urlencode({"localAuthorityId": aid, "ratingKey": "1", "ratingOperatorKey": "LessThanOrEqual", "pageSize": 500})
        try:
            ests = get(f"{FSA}/Establishments?{q}", FSA_H).get("establishments") or []
        except Exception as e:
            print("food: establishments failed for", c, e); ests = []
        for e in ests:
            fid = str(e.get("FHRSID") or "")
            rd = day(e.get("RatingDate"))
            key = f"{fid}:{rd}:{e.get('RatingValue')}"
            if not fid or key in seen:
                continue
            seen[key] = NOW.strftime(ISO)
            if first_run or rd < cut:      # the first run only learns what is already there
                continue
            addr = ", ".join(str(e.get(k) or "").strip() for k in ("AddressLine1", "AddressLine2", "AddressLine3", "AddressLine4") if str(e.get(k) or "").strip())
            sc = e.get("scores") or {}
            new.append({"name": str(e.get("BusinessName") or "").strip(), "type": e.get("BusinessType"), "rating": str(e.get("RatingValue")),
                        "inspected": rd, "council": c, "address": addr, "postcode": str(e.get("PostCode") or "").strip(),
                        "addressWithheld": not (addr or e.get("PostCode")), "newRatingPending": bool(e.get("NewRatingPending")),
                        "scores": {"hygiene": sc.get("Hygiene"), "structural": sc.get("Structural"), "management": sc.get("ConfidenceInManagement")},
                        "url": f"https://ratings.food.gov.uk/business/{fid}"})
        time.sleep(0.4)
    table.sort(key=lambda r: -r["lowPct"])
    prev = state.get("foodTable") or {}
    for r in table:
        p = prev.get(r["council"])
        if p:
            r["lowPctBefore"] = p.get("lowPct"); r["before"] = p.get("at")
    # keep a comparison point that is at least 28 days old, so changes are month on month
    for r in table:
        p = prev.get(r["council"])
        if not p or p.get("at", "") <= (NOW - timedelta(days=28)).strftime("%Y-%m-%d"):
            prev[r["council"]] = {"lowPct": r["lowPct"], "zero": r["zero"], "one": r["one"], "rated": r["rated"], "at": NOW.strftime("%Y-%m-%d")}
    state["foodTable"] = prev
    new.sort(key=lambda r: (r["rating"], r["inspected"]))
    return {"new": new, "table": table, "missingCouncils": missing, "firstRun": first_run}


# ---------------------------------------------------------------- contract awards
def money(v, cur="GBP"):
    try:
        v = float(v)
    except Exception:
        return ""
    if v <= 0:
        return ""
    s = f"{v:,.0f}"
    return ("£" if (cur or "GBP") == "GBP" else f"{cur} ") + s


def releases_from(pkg):
    if isinstance(pkg, dict):
        if isinstance(pkg.get("releases"), list):
            return pkg["releases"]
        if isinstance(pkg.get("results"), list):   # Contracts Finder wraps release packages in "results"
            out = []
            for r in pkg["results"]:
                out += releases_from(r)
            return out
    return []


def award_rows(rel, where):
    buyer = ((rel.get("buyer") or {}).get("name")) or ""
    parties = {p.get("id"): p for p in (rel.get("parties") or []) if isinstance(p, dict)}
    if not buyer:
        for p in parties.values():
            if "buyer" in (p.get("roles") or []) or "procuringEntity" in (p.get("roles") or []):
                buyer = p.get("name") or ""; break
    tender = rel.get("tender") or {}
    title = str(tender.get("title") or "").strip()
    desc = re.sub(r"\s+", " ", str(tender.get("description") or "")).strip()
    rows = []
    for aw in (rel.get("awards") or []):
        if not isinstance(aw, dict):
            continue
        sups = [str(s.get("name") or (parties.get(s.get("id")) or {}).get("name") or "").strip() for s in (aw.get("suppliers") or []) if isinstance(s, dict)]
        val = aw.get("value") or {}
        amount = val.get("amountGross") or val.get("amount")
        period = aw.get("contractPeriod") or {}
        rows.append({"buyer": buyer.strip(), "title": title or str(aw.get("title") or "").strip(), "description": desc[:400],
                     "suppliers": [s for s in sups if s][:6], "value": amount, "valueText": money(amount, val.get("currency")),
                     "awarded": day(aw.get("date") or rel.get("date")), "published": day(rel.get("date")),
                     "start": day(period.get("startDate")), "end": day(period.get("endDate")),
                     "ocid": rel.get("ocid") or "", "id": str(rel.get("id") or ""), "where": where})
    return rows


def contracts(state):
    since = NOW - timedelta(days=8)
    rows, errors = [], []
    # Find a Tender (the central digital platform since the Procurement Act 2023 came into force)
    url = "https://www.find-tender.service.gov.uk/api/1.0/ocdsReleasePackages?" + urllib.parse.urlencode(
        {"updatedFrom": since.strftime("%Y-%m-%dT%H:%M:%S"), "updatedTo": NOW.strftime("%Y-%m-%dT%H:%M:%S"), "stages": "award", "limit": 100})
    pages = 0
    while url and pages < 40:
        try:
            pkg = get(url, timeout=60)
        except Exception as e:
            errors.append(f"find-tender: {type(e).__name__}: {str(e)[:160]}"); break
        pages += 1
        for rel in releases_from(pkg):
            for r in award_rows(rel, "Find a Tender"):
                r["url"] = "https://www.find-tender.service.gov.uk/Notice/" + r["id"] if re.fullmatch(r"\d{6}-\d{4}", r["id"]) else "https://www.find-tender.service.gov.uk/Search/Results?keywords=" + urllib.parse.quote(r["ocid"])
                rows.append(r)
        url = ((pkg.get("links") or {}).get("next")) if isinstance(pkg, dict) else None
        time.sleep(0.5)
    ft_pages = pages
    # Contracts Finder (still carries below-threshold awards)
    url = "https://www.contractsfinder.service.gov.uk/Published/Notices/OCDS/Search?" + urllib.parse.urlencode(
        {"publishedFrom": since.strftime("%Y-%m-%dT%H:%M:%S"), "publishedTo": NOW.strftime("%Y-%m-%dT%H:%M:%S"), "stages": "award", "limit": 100})
    pages = 0
    while url and pages < 40:
        try:
            pkg = get(url, timeout=60)
        except Exception as e:
            errors.append(f"contracts-finder: {type(e).__name__}: {str(e)[:160]}"); break
        pages += 1
        for rel in releases_from(pkg):
            for r in award_rows(rel, "Contracts Finder"):
                r["url"] = "https://www.contractsfinder.service.gov.uk/Notice/" + r["id"] if r["id"] else ""
                rows.append(r)
        url = ((pkg.get("links") or {}).get("next")) if isinstance(pkg, dict) else None
        time.sleep(0.5)
    total = len(rows)
    keep, seen = [], state.setdefault("contractsSeen", {})
    for r in rows:
        b = r["buyer"]
        local_buyer = bool(BUYER_RX.search(b)) and not BUYER_NOT_RX.search(b)
        local_work = bool(PLACE_RX.search(r["title"])) and not BUYER_NOT_RX.search(r["title"])
        if not (local_buyer or local_work):
            continue
        key = (r["ocid"] or r["id"]) + "|" + "|".join(r["suppliers"])[:80]
        if key in seen:
            continue
        seen[key] = NOW.strftime(ISO)
        r["why"] = "Essex buyer" if local_buyer else "work in Essex"
        keep.append(r)
    keep.sort(key=lambda r: -(float(r["value"]) if isinstance(r["value"], (int, float)) else 0))
    cut = (NOW - timedelta(days=120)).strftime(ISO)
    state["contractsSeen"] = {k: v for k, v in seen.items() if v >= cut}
    return {"awards": keep, "scanned": total, "findTenderPages": ft_pages, "contractsFinderPages": pages, "errors": errors}


# ---------------------------------------------------------------- petitions
def petitions(state):
    lst = get("https://petition.parliament.uk/petitions.json?state=open", timeout=40).get("data") or []
    lst = [p for p in lst if isinstance(p, dict)]
    lst.sort(key=lambda p: -int(((p.get("attributes") or {}).get("signature_count")) or 0))
    out = []
    prev = state.get("petitions") or {}
    cur = {}
    for p in lst[:25]:
        pid = p.get("id")
        try:
            d = (get(f"https://petition.parliament.uk/petitions/{pid}.json", timeout=40).get("data") or {}).get("attributes") or {}
        except Exception as e:
            print("petitions: failed", pid, e); continue
        time.sleep(0.3)
        by = [c for c in (d.get("signatures_by_constituency") or []) if isinstance(c, dict)]
        if len(by) < 600:
            continue
        counts = sorted(int(c.get("signature_count") or 0) for c in by)
        median = counts[len(counts) // 2] or 1
        essex = {c.get("name"): int(c.get("signature_count") or 0) for c in by if c.get("name") in CONSTITUENCIES}
        if len(essex) < 15:
            continue
        ranked = sorted(by, key=lambda c: -int(c.get("signature_count") or 0))
        rank = {c.get("name"): i + 1 for i, c in enumerate(ranked)}
        etotal = sum(essex.values())
        emedian = sorted(essex.values())[len(essex) // 2]
        top = max(essex, key=essex.get)
        before = (prev.get(str(pid)) or {}).get("essex")
        cur[str(pid)] = {"essex": etotal, "at": NOW.strftime("%Y-%m-%d")}
        out.append({"id": pid, "action": str(d.get("action") or "").strip(), "total": int(d.get("signature_count") or 0),
                    "opened": day(d.get("opened_at")), "closes": day(d.get("closed_at")), "debateThresholdReached": bool(d.get("debate_threshold_reached_at")),
                    "governmentResponded": bool(d.get("government_response_at")), "essexTotal": etotal,
                    "essexSinceLastRun": (etotal - before) if isinstance(before, int) else None,
                    "essexMedian": emedian, "ukMedian": median, "ratio": round(emedian / median, 2),
                    "top": {"name": top, "signatures": essex[top], "ukRank": rank.get(top), "of": len(by)},
                    "byConstituency": dict(sorted(essex.items(), key=lambda kv: -kv[1])),
                    "url": f"https://petition.parliament.uk/petitions/{pid}"})
    state["petitions"] = cur
    return {"petitions": out}


# ---------------------------------------------------------------- house prices
HPI_REGIONS = [("Basildon", "basildon"), ("Braintree", "braintree"), ("Brentwood", "brentwood"), ("Castle Point", "castle-point"),
               ("Chelmsford", "chelmsford"), ("Colchester", "colchester"), ("Epping Forest", "epping-forest"), ("Harlow", "harlow"),
               ("Maldon", "maldon"), ("Rochford", "rochford"), ("Southend-on-Sea", "southend-on-sea"), ("Tendring", "tendring"),
               ("Thurrock", "thurrock"), ("Uttlesford", "uttlesford"), ("Essex (county council area)", "essex"), ("England", "england")]


def hpi(slug, month):
    d = get(f"https://landregistry.data.gov.uk/data/ukhpi/region/{slug}/month/{month}.json", timeout=40)
    t = (d.get("result") or {}).get("primaryTopic") or {}
    if not isinstance(t, dict) or t.get("averagePrice") in (None, ""):
        return None
    num = lambda k: (float(t[k]) if isinstance(t.get(k), (int, float, str)) and str(t.get(k)).strip() not in ("",) else None)
    try:
        return {"price": num("averagePrice"), "annual": num("percentageAnnualChange"), "monthly": num("percentageChange"),
                "detached": num("averagePriceDetached"), "flat": num("averagePriceFlatMaisonette"), "firstTime": num("averagePriceFirstTimeBuyer")}
    except Exception:
        return None


def prices(state):
    """UK House Price Index (HM Land Registry and ONS, Open Government Licence): the newest month published."""
    month = None
    y, m = NOW.year, NOW.month
    for _ in range(6):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        cand = f"{y}-{m:02d}"
        try:
            if hpi("chelmsford", cand):
                month = cand; break
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
        time.sleep(0.3)
    if not month:
        return {"error": "no recent month found"}
    rows = []
    for name, slug in HPI_REGIONS:
        try:
            r = hpi(slug, month)
        except Exception as e:
            print("prices: failed", slug, e); r = None
        if r:
            rows.append(dict(r, area=name, slug=slug))
        time.sleep(0.3)
    is_new = state.get("hpiMonth") != month
    state["hpiMonth"] = month
    return {"month": month, "new": is_new, "rows": rows, "url": "https://landregistry.data.gov.uk/app/ukhpi"}


# ---------------------------------------------------------------- recorded crime
def _months_back(ym, n):
    y, m = int(ym[:4]), int(ym[5:7])
    m -= n
    while m <= 0:
        y, m = y - 1, m + 12
    return f"{y}-{m:02d}"


def _crimes(poly, month):
    body = urllib.parse.urlencode({"poly": poly, "date": month}).encode()
    for attempt in range(3):
        try:
            return get("https://data.police.uk/api/crimes-street/all-crime", data=body, timeout=60)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(2 + attempt * 3); continue
            raise
    return None


def crime(state):
    """Street-level recorded crime by Essex Police neighbourhood (data.police.uk, Open Government Licence), newest month,
    with the month before and the same month a year earlier. Runs in full only when a new month is published."""
    last = str(get("https://data.police.uk/api/crime-last-updated").get("date") or "")[:7]
    if not last:
        return {"error": "no last-updated date"}
    store = state.setdefault("crime", {})          # {month: {hood id: {"n": total, "cats": {...}}}}
    names = state.setdefault("crimeHoods", {})
    is_new = state.get("crimeMonth") != last
    months = [last, _months_back(last, 1), _months_back(last, 12)]
    if is_new or any(m not in store for m in months):
        hoods = get("https://data.police.uk/api/essex/neighbourhoods")
        print("crime: neighbourhoods", len(hoods), [h.get("name") for h in hoods[:12]])
        polys, failed = {}, 0
        for h in hoods:
            hid = h.get("id"); names[hid] = str(h.get("name") or hid).strip()
            try:
                b = get(f"https://data.police.uk/api/essex/{hid}/boundary", timeout=40)
            except Exception as e:
                failed += 1; continue
            step = max(1, len(b) // 120)
            pts = b[::step]
            polys[hid] = ":".join(f"{float(p['latitude']):.4f},{float(p['longitude']):.4f}" for p in pts)
            time.sleep(0.08)
        for mth in months:
            if mth in store and len(store[mth]) >= len(polys) * 0.9:
                continue
            got = {}
            for hid, poly in polys.items():
                try:
                    cs = _crimes(poly, mth)
                except Exception as e:
                    cs = None
                if cs is None:
                    continue
                cats = {}
                for c in cs:
                    cats[c.get("category") or "other"] = cats.get(c.get("category") or "other", 0) + 1
                got[hid] = {"n": len(cs), "cats": cats}
                time.sleep(0.08)
            store[mth] = got
            print("crime:", mth, "areas read", len(got), "of", len(polys), "boundaries failed", failed)
        for old in [k for k in store if k not in months]:
            del store[old]
    state["crimeMonth"] = last
    cur, prev, yago = store.get(months[0], {}), store.get(months[1], {}), store.get(months[2], {})
    rows = []
    for hid, v in cur.items():
        top = sorted(v["cats"].items(), key=lambda kv: -kv[1])[:3]
        rows.append({"area": names.get(hid, hid), "id": hid, "n": v["n"], "prev": (prev.get(hid) or {}).get("n"), "yearAgo": (yago.get(hid) or {}).get("n"),
                     "top": [[k.replace("-", " "), n] for k, n in top], "shoplifting": v["cats"].get("shoplifting", 0),
                     "violence": v["cats"].get("violent-crime", 0), "asb": v["cats"].get("anti-social-behaviour", 0), "burglary": v["cats"].get("burglary", 0),
                     "vehicle": v["cats"].get("vehicle-crime", 0)})
    rows.sort(key=lambda r: -r["n"])
    tot = lambda d: sum(x["n"] for x in d.values()) if d else None
    return {"month": last, "new": is_new, "rows": rows, "total": tot(cur), "totalPrev": tot(prev), "totalYearAgo": tot(yago),
            "months": months, "url": "https://www.police.uk/pu/your-area/essex-police/"}


# ---------------------------------------------------------------- digest
def digest(data):
    L = [f"THE SEAX DATA DESK  |  collected {NOW.strftime('%A %d %B %Y, %H:%M')} UTC",
         "Official open data, worked out for Essex. Leads for the newsroom: read ops/newsroom.md (DATA DESK) before writing.", ""]
    f = data.get("food") or {}
    L.append("== FOOD HYGIENE (Food Standards Agency) ==")
    if f.get("error"):
        L.append("  could not be read this run: " + f["error"])
    else:
        if f.get("firstRun"):
            L.append("  First run: the desk has recorded every current 0 and 1 rating and will list only NEW ones from tomorrow.")
        new = f.get("new") or []
        L.append(f"  Newly published ratings of 0 or 1 (inspected in the last 45 days): {len(new)}")
        for r in new[:40]:
            flags = (" [address withheld: do not use]" if r["addressWithheld"] else "") + (" [new rating pending: do not use]" if r["newRatingPending"] else "")
            L.append(f"  - RATING {r['rating']} | {r['name']} | {r['type']} | {r['address']} {r['postcode']} | {r['council']} | inspected {uk_date(r['inspected'])}{flags} | {r['url']}")
        if f.get("table"):
            L.append("  Share of rated premises with a rating of 0, 1 or 2, by council (highest first):")
            for r in f["table"]:
                ch = ""
                if r.get("lowPctBefore") is not None and r.get("before") and r["lowPctBefore"] != r["lowPct"]:
                    ch = f" (was {r['lowPctBefore']}% on {uk_date(r['before'])})"
                L.append(f"  - {r['council']}: {r['lowPct']}%{ch} | zero-rated {r['zero']}, one-rated {r['one']}, two-rated {r['two']} of {r['rated']} rated | rated 5: {r['fivePct']}%")
        if f.get("missingCouncils"):
            L.append("  Councils not matched: " + ", ".join(f["missingCouncils"]))
    L.append("")
    c = data.get("contracts") or {}
    L.append("== CONTRACT AWARDS (Find a Tender and Contracts Finder, last 8 days) ==")
    if c.get("error"):
        L.append("  could not be read this run: " + c["error"])
    else:
        aw = c.get("awards") or []
        L.append(f"  New awards by Essex public bodies or for work in Essex: {len(aw)} (from {c.get('scanned', 0)} UK award notices scanned)")
        for r in aw[:40]:
            L.append(f"  - {r['valueText'] or 'value not given'} | {r['buyer']} | {r['title'][:140]} | to {', '.join(r['suppliers']) or 'supplier not named'} | awarded {uk_date(r['awarded']) if r['awarded'] else '?'}"
                     f"{' | runs ' + r['start'] + ' to ' + r['end'] if r['start'] and r['end'] else ''} | {r['where']} | {r['url']}")
        for e in c.get("errors") or []:
            L.append("  note: " + e)
    L.append("")
    p = data.get("petitions") or {}
    L.append("== PARLIAMENT PETITIONS (the 25 biggest open petitions) ==")
    if p.get("error"):
        L.append("  could not be read this run: " + p["error"])
    else:
        ps = p.get("petitions") or []
        hot = sorted([x for x in ps if x["ratio"] >= 1.5 or x["top"]["ukRank"] <= 10], key=lambda x: -x["ratio"])
        cold = sorted([x for x in ps if x["ratio"] <= 0.6], key=lambda x: x["ratio"])
        L.append("  Essex signs these far MORE than the typical UK constituency (ratio = median Essex seat / median UK seat):")
        for x in hot[:8]:
            L.append(f"  - x{x['ratio']} | {x['action'][:120]} | Essex {x['essexTotal']:,} of {x['total']:,} signatures | top: {x['top']['name']} {x['top']['signatures']:,} (UK rank {x['top']['ukRank']} of {x['top']['of']}) | {x['url']}")
        L.append("  Essex signs these far LESS:")
        for x in cold[:5]:
            L.append(f"  - x{x['ratio']} | {x['action'][:120]} | Essex {x['essexTotal']:,} of {x['total']:,} | {x['url']}")
        movers = sorted([x for x in ps if x.get("essexSinceLastRun")], key=lambda x: -x["essexSinceLastRun"])
        if movers:
            L.append("  Most new Essex signatures since the last run:")
            for x in movers[:5]:
                L.append(f"  - +{x['essexSinceLastRun']:,} | {x['action'][:120]} | {x['url']}")
    cr = data.get("crime") or {}
    L.append("== RECORDED CRIME BY NEIGHBOURHOOD (data.police.uk street-level crime, Essex Police) ==")
    if cr.get("error"):
        L.append("  could not be read this run: " + cr["error"])
    elif cr.get("rows"):
        try:
            mm = datetime.strptime(cr["month"], "%Y-%m").strftime("%B %Y")
        except Exception:
            mm = cr.get("month")
        chg = lambda a, b: (f"{100 * (a - b) / b:+.0f}%" if isinstance(a, int) and isinstance(b, int) and b >= 30 else "n/a")
        L.append(f"  Newest month published: {mm}" + ("  ** NEW SINCE THE LAST RUN: worth a story **" if cr.get("new") else "  (already seen)"))
        L.append(f"  All Essex Police neighbourhoods: {cr.get('total'):,} crimes and anti-social behaviour incidents | month before {cr.get('totalPrev') or 0:,} | same month a year earlier {cr.get('totalYearAgo') or 0:,}")
        for r in cr["rows"][:60]:
            L.append(f"  - {r['area']}: {r['n']:,} | vs month before {chg(r['n'], r['prev'])} | vs a year earlier {chg(r['n'], r['yearAgo'])} | violence {r['violence']}, anti-social behaviour {r['asb']}, shoplifting {r['shoplifting']}, burglary {r['burglary']}, vehicle crime {r['vehicle']}")
        L.append("  Source: " + str(cr.get("url")))
    L.append("")
    h = data.get("prices") or {}
    L.append("== HOUSE PRICES (UK House Price Index, HM Land Registry and ONS) ==")
    if h.get("error"):
        L.append("  could not be read this run: " + h["error"])
    elif h.get("rows"):
        try:
            mm = datetime.strptime(h["month"], "%Y-%m").strftime("%B %Y")
        except Exception:
            mm = h.get("month")
        L.append(f"  Newest month published: {mm}" + ("  ** NEW SINCE THE LAST RUN: worth a story **" if h.get("new") else "  (already seen: no story unless one was never written)"))
        gbp = lambda v: ("£" + f"{v:,.0f}") if isinstance(v, (int, float)) else "n/a"
        pct = lambda v: (f"{v:+.1f}%") if isinstance(v, (int, float)) else "n/a"
        for r in sorted(h["rows"], key=lambda r: (r["area"] in ("England", "Essex (county council area)"), r.get("annual") if isinstance(r.get("annual"), (int, float)) else 0)):
            L.append(f"  - {r['area']}: average {gbp(r['price'])} | change in a year {pct(r['annual'])} | in a month {pct(r['monthly'])} | first-time buyers {gbp(r.get('firstTime'))} | flats {gbp(r.get('flat'))} | detached {gbp(r.get('detached'))}")
        L.append("  Source page: " + str(h.get("url")))
    L.append("")
    return "\n".join(L)


def gazette_probe():
    """One-off look at The Gazette's data feeds (20 Nov 2026), to see whether corporate insolvency notices can be read."""
    for u in ("https://www.thegazette.co.uk/insolvency/notice/data.json?text=essex&results-page-size=10",
              "https://www.thegazette.co.uk/all-notices/notice/data.json?text=chelmsford&results-page-size=10&noticetypes=2443"):
        try:
            req = urllib.request.Request(u, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=40) as r:
                raw = r.read(200000).decode("utf-8", "replace")
            print("GAZETTE OK", u, len(raw)); print(raw[:2500])
        except Exception as e:
            print("GAZETTE FAIL", u, type(e).__name__, str(e)[:200])


def main():
    os.makedirs(OUT, exist_ok=True)
    gazette_probe()
    state = load("state.json", {})
    data = load("data.json", {})
    for name, fn in (("food", food), ("contracts", contracts), ("petitions", petitions), ("prices", prices), ("crime", crime)):
        if ONLY and name not in ONLY:
            continue
        try:
            data[name] = fn(state)
            print(name, "ok")
        except Exception as e:
            print(name, "FAILED", type(e).__name__, str(e)[:300])
            data[name] = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
    data["at"] = NOW.strftime(ISO)
    save("data.json", data); save("state.json", state)
    txt = digest(data)
    open(os.path.join(OUT, "latest.txt"), "w", encoding="utf-8").write(txt)
    print(txt[:6000])


if __name__ == "__main__":
    main()
