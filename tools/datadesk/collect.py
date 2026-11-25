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
  elections  Elections and by-elections in Essex in the next 75 days, with candidates once published (Democracy
             Club developers API, CC BY 4.0; needs the secret DEMOCRACY_CLUB_KEY)

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
ONLY = set(sys.argv[2:])
# An item stays "new" in the digest for this long after the desk first saw it. The collector runs more often than the
# newsroom reads it (once a day at 12:35), so "new since the last run" lost every lead to the next run (found 20 Nov 2026).
FRESH_HOURS = 40
FRESH_CUT = (NOW - timedelta(hours=FRESH_HOURS)).strftime(ISO)
MONTHLY_FRESH_CUT = (NOW - timedelta(hours=72)).strftime(ISO)  # optional: run only these parts

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
            if not fid:
                continue
            if seen.setdefault(key, NOW.strftime(ISO)) < FRESH_CUT:
                continue
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
        if seen.setdefault(key, NOW.strftime(ISO)) < FRESH_CUT:
            continue
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
    d = None
    for attempt in range(3):   # the service sometimes answers 403 or 5xx for a moment
        try:
            d = get(f"https://landregistry.data.gov.uk/data/ukhpi/region/{slug}/month/{month}.json", timeout=40); break
        except urllib.error.HTTPError as e:
            if e.code == 404 or attempt == 2:
                raise
            time.sleep(6 + attempt * 10)
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
    if state.get("hpiMonth") != month or not state.get("hpiMonthAt"):
        state["hpiMonthAt"] = NOW.strftime(ISO)
    state["hpiMonth"] = month
    is_new = state["hpiMonthAt"] >= MONTHLY_FRESH_CUT
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
    # Method v2 (20 Nov 2026, after an independent recount of the September 2026 figures): full neighbourhood boundaries
    # (no thinning), every crime counted once across neighbourhoods, and crimes with no location counted separately.
    if state.get("crimeMethod") != "full-v2":
        store.clear(); state["crimeMethod"] = "full-v2"
    nolo = state.setdefault("crimeNoLocation", {})
    fetch_new = state.get("crimeMonth") != last
    if fetch_new or not state.get("crimeMonthAt"):
        state["crimeMonthAt"] = NOW.strftime(ISO)
    is_new = state["crimeMonthAt"] >= MONTHLY_FRESH_CUT
    months = [last, _months_back(last, 1), _months_back(last, 12)]
    if fetch_new or any(m not in store for m in months):
        hoods = get("https://data.police.uk/api/essex/neighbourhoods")
        print("crime: neighbourhoods", len(hoods), [h.get("name") for h in hoods[:12]])
        polys, failed = {}, 0
        for h in hoods:
            hid = h.get("id"); names[hid] = str(h.get("name") or hid).strip()
            try:
                b = get(f"https://data.police.uk/api/essex/{hid}/boundary", timeout=40)
            except Exception as e:
                failed += 1; continue
            polys[hid] = ":".join(f"{p['latitude']},{p['longitude']}" for p in b)
            time.sleep(0.08)
        for mth in months:
            if mth in store and len(store[mth]) >= len(polys) * 0.9:
                continue
            got, seen_ids = {}, set()
            for hid, poly in polys.items():
                try:
                    cs = _crimes(poly, mth)
                except Exception as e:
                    cs = None
                if cs is None:
                    continue
                cats = {}
                fresh = [c for c in cs if c.get("id") not in seen_ids]
                seen_ids.update(c.get("id") for c in cs)
                cs = fresh
                for c in cs:
                    cats[c.get("category") or "other"] = cats.get(c.get("category") or "other", 0) + 1
                got[hid] = {"n": len(cs), "cats": cats}
                time.sleep(0.08)
            store[mth] = got
            try:
                nolo[mth] = len(get(f"https://data.police.uk/api/crimes-no-location?category=all-crime&force=essex&date={mth}"))
            except Exception:
                nolo.pop(mth, None)
            print("crime:", mth, "areas read", len(got), "of", len(polys), "boundaries failed", failed, "no location", nolo.get(mth))
        for old in [k for k in store if k not in months]:
            del store[old]
        for old in [k for k in nolo if k not in months]:
            del nolo[old]
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
            "months": months, "noLocation": [nolo.get(m) for m in months], "method": "full boundaries, each crime counted once",
            "url": "https://www.police.uk/pu/your-area/essex-police/"}


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
        L.append(f"  Ratings of 0 or 1 first seen by the desk in the last {FRESH_HOURS} hours (inspected in the last 45 days): {len(new)}")
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
    ins = data.get("insolvency") or {}
    L.append("== COMPANY INSOLVENCY NOTICES MENTIONING ESSEX (The Gazette, last 8 days; companies only) ==")
    if ins.get("error"):
        L.append("  could not be read this run: " + ins["error"])
    else:
        ns = ins.get("notices") or []
        L.append(f"  New notices: {len(ns)}. LEADS ONLY: read ops/newsroom.md 2k vi before using any of them.")
        order = {"2410": 0, "2452": 1, "2450": 2, "2411": 3, "2443": 4, "2431": 5, "2432": 5}
        for r in sorted(ns, key=lambda r: order.get(r["code"], 9))[:40]:
            L.append(f"  - {r['type']} | {r['company']} | published {uk_date(r['published']) if r['published'] else '?'} | {r['text'][:200]} | {r['url']}")
    L.append("")
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
        L.append(f"  Newest month published: {mm}" + ("  ** NEW IN THE LAST 3 DAYS: worth a story if none has been written (check data/archive.json) **" if cr.get("new") else "  (already seen)"))
        L.append(f"  All Essex Police neighbourhoods: {cr.get('total'):,} crimes and anti-social behaviour incidents | month before {cr.get('totalPrev') or 0:,} | same month a year earlier {cr.get('totalYearAgo') or 0:,}")
        L.append(f"  Method: {cr.get('method') or 'thinned boundaries'}. Crimes with no location (not in the totals), this month / month before / a year earlier: {cr.get('noLocation')}. Figures are counts of police.uk records; TRIPLE CHECK every figure before publishing (ops/newsroom.md).")
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
        L.append(f"  Newest month published: {mm}" + ("  ** NEW IN THE LAST 3 DAYS: worth a story if none has been written (check data/archive.json) **" if h.get("new") else "  (already seen: no story unless one was never written)"))
        gbp = lambda v: ("£" + f"{v:,.0f}") if isinstance(v, (int, float)) else "n/a"
        pct = lambda v: (f"{v:+.1f}%") if isinstance(v, (int, float)) else "n/a"
        for r in sorted(h["rows"], key=lambda r: (r["area"] in ("England", "Essex (county council area)"), r.get("annual") if isinstance(r.get("annual"), (int, float)) else 0)):
            L.append(f"  - {r['area']}: average {gbp(r['price'])} | change in a year {pct(r['annual'])} | in a month {pct(r['monthly'])} | first-time buyers {gbp(r.get('firstTime'))} | flats {gbp(r.get('flat'))} | detached {gbp(r.get('detached'))}")
        L.append("  Source page: " + str(h.get("url")))
    L.append("")
    el = data.get("elections")
    if el:
        L.append("== ELECTIONS AND BY-ELECTIONS IN ESSEX, NEXT 75 DAYS (Democracy Club, CC BY 4.0) ==")
        if el.get("error"):
            L.append("  could not be read this run: " + el["error"])
        elif not el.get("ballots"):
            L.append(f"  none found ({el.get('scanned', 0)} ballots scanned UK-wide)")
        else:
            for r in el["ballots"]:
                flag = "  ** NEW **" if r.get("new") else ""
                if r.get("candidatesNew"):
                    flag += "  ** CANDIDATES JUST CONFIRMED **"
                cands = "; ".join(f"{c['name']} ({c['party']})" for c in r.get("candidates") or []) or "candidates not yet published"
                L.append(f"  - {r['date']}: {r['election']}, {r['seat']}{' (by-election)' if r.get('byElection') else ''}, seats {r.get('seats')}, list {'final' if r.get('candidatesLocked') else 'not final'}{flag}")
                L.append(f"    {cands}")
                L.append(f"    {r['url']}")
            L.append("  Credit: Democracy Club (whocanivotefor.co.uk). Check candidate names against the council's statement of persons nominated before publishing.")
        L.append("")
    return "\n".join(L)


GAZETTE_TYPES = {"2410": "Appointment of administrators", "2411": "Appointment of administrative receivers", "2421": "Appointment of receivers",
                 "2431": "Resolution for voluntary winding-up", "2432": "Resolution for winding-up", "2441": "Meetings of creditors",
                 "2443": "Appointment of liquidators", "2445": "Notices to creditors", "2450": "Petition to wind up a company",
                 "2452": "Winding-up order"}


def insolvency(state):
    """Corporate insolvency notices mentioning Essex in The Gazette, the official public record (Open Government Licence),
    for the last 8 days. Companies only: personal insolvency (codes 25xx) is never collected."""
    since = (NOW - timedelta(days=8)).strftime("%Y-%m-%d")
    seen = state.setdefault("gazetteSeenV2", {})
    rows, pages, sample = [], 0, ""
    url = "https://www.thegazette.co.uk/insolvency/notice/data.json?" + urllib.parse.urlencode(
        {"text": "essex", "start-publish-date": since, "results-page-size": 100, "sort-by": "latest-date"})
    while url and pages < 6:
        d = get(url, timeout=60); pages += 1
        ents = d.get("entry") or []
        if isinstance(ents, dict):
            ents = [ents]
        if pages == 1:
            print("insolvency: total", d.get("f:total"), "first entry keys", sorted((ents[0] if ents else {}).keys()))
            sample = json.dumps(ents[0])[:1500] if ents else ""
            print(sample)
        for e in ents:
            code = str(e.get("f:notice-code") or "")
            if not code.startswith("24"):
                continue
            nid = str(e.get("id") or "").rsplit("/", 1)[-1]
            pub = day(e.get("published") or e.get("updated"))
            if not nid or (pub and pub < since):
                continue
            if seen.setdefault(nid, NOW.strftime(ISO)) < FRESH_CUT:
                continue
            content = e.get("content")
            if isinstance(content, dict):
                content = content.get("$") or content.get("#text") or content.get("div") or ""
            text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html_unescape(str(content or "")))).strip()
            rows.append({"company": str(e.get("title") or "").strip(), "code": code, "type": GAZETTE_TYPES.get(code, "Corporate insolvency notice " + code),
                         "published": pub, "text": text[:420], "url": "https://www.thegazette.co.uk/notice/" + nid})
        nxt = [l.get("@href") for l in (d.get("link") or []) if isinstance(l, dict) and l.get("@rel") == "next"]
        url = nxt[0] if nxt and ents else None
        if url and "start-publish-date" not in url:
            url += "&" + urllib.parse.urlencode({"start-publish-date": since, "results-page-size": 100, "sort-by": "latest-date"})
        time.sleep(0.5)
    cut = (NOW - timedelta(days=60)).strftime(ISO)
    state["gazetteSeenV2"] = {k: v for k, v in seen.items() if v >= cut}
    return {"notices": rows, "pages": pages}


ELECTION_RX = re.compile(r"^(local|parl|mayor|pcc|europarl)\.(essex|greater-essex|basildon|braintree|brentwood|castle-point|chelmsford|colchester|epping-forest|harlow|"
                         r"maldon|rochford|southend-on-sea|southend|tendring|thurrock|uttlesford|basildon-and-billericay|brentwood-and-ongar|clacton|"
                         r"harwich-and-north-essex|north-west-essex|rayleigh-and-wickford|south-basildon-and-east-thurrock|southend-east-and-rochford|"
                         r"southend-west-and-leigh|witham)\b")


def elections(state):
    """Elections and by-elections coming up in Essex, with candidates once published (Democracy Club, CC BY 4.0).
    Uses the Democracy Club developers API (developers.democracyclub.org.uk/api/v1/), which is what the owner's key is
    for (Democracy Club, 25 Nov 2026). The key is the GitHub secret DEMOCRACY_CLUB_KEY, sent as ?auth_token=; it is
    never printed."""
    key = os.environ.get("DEMOCRACY_CLUB_KEY", "").strip()
    base = "https://developers.democracyclub.org.uk/api/v1"

    def dc(url):
        full = url + ("&" if "?" in url else "?") + urllib.parse.urlencode({"auth_token": key}) if "auth_token=" not in url else url
        try:
            return get(full, timeout=60)
        except urllib.error.HTTPError as e:
            body = e.read()[:300].decode("utf-8", "replace") if hasattr(e, "read") else ""
            print("elections: HTTP", e.code, "for", url.split("?")[0], "|", body.replace(key, "***") if key else body)
            raise

    today = NOW.strftime("%Y-%m-%d"); end = (NOW + timedelta(days=75)).strftime("%Y-%m-%d")
    url = base + "/elections/?" + urllib.parse.urlencode({"future": 1, "identifier_type": "ballot", "limit": 200})
    items, pages = [], 0
    while url and pages < 15:
        d = dc(url); pages += 1
        res = d.get("results") if isinstance(d, dict) else d
        res = res or []
        if pages == 1:
            print("elections: count", d.get("count") if isinstance(d, dict) else len(res), "first item keys", sorted((res[0] if res else {}).keys()))
            print("elections: sample", json.dumps(res[0])[:700] if res else "")
        items += res
        url = d.get("next") if isinstance(d, dict) else None
        time.sleep(0.4)
    rows, detail_logged = [], False
    for b in items:
        bid = str(b.get("election_id") or b.get("ballot_paper_id") or "")
        if not ELECTION_RX.match(bid) or b.get("cancelled"):
            continue
        date = day(b.get("poll_open_date") or b.get("election_date") or bid.rsplit(".", 1)[-1])
        if date and (date < today or date > end):
            continue
        cands, locked, seats = [], False, b.get("seats_contested") or b.get("winner_count")
        try:
            det = dc(base + "/elections/" + urllib.parse.quote(bid) + "/")
            if not detail_logged:
                print("elections: detail keys", sorted(det.keys()) if isinstance(det, dict) else type(det))
                detail_logged = True
            for c in (det.get("candidates") or []):
                per = c.get("person") or {}; par = c.get("party") or {}
                nm = str(per.get("name") or c.get("name") or "").strip()
                if nm:
                    cands.append({"name": nm, "party": str(c.get("party_name") or par.get("party_name") or par.get("name") or "").strip()})
            locked = bool(det.get("candidates_verified") or det.get("candidates_locked")) or bool(cands)
            seats = seats or det.get("seats_contested") or det.get("winner_count")
        except Exception as e:
            print("elections: detail failed", bid, type(e).__name__)
        rows.append({"id": bid, "date": date, "election": str(b.get("election_title") or b.get("name") or "").strip(),
                     "seat": str(b.get("post_name") or ((b.get("division") or {}).get("name") if isinstance(b.get("division"), dict) else "") or "").strip(),
                     "byElection": ".by." in bid, "seats": seats, "candidatesLocked": locked,
                     "candidates": sorted(cands, key=lambda c: c["name"].split()[-1] if c["name"] else ""),
                     "url": "https://whocanivotefor.co.uk/elections/" + bid + "/"})
        time.sleep(0.4)
    rows.sort(key=lambda r: r["date"] or "")
    known = state.setdefault("electionsSeen", {})
    for r in rows:
        r["new"] = r["id"] not in known
        r["candidatesNew"] = r["candidatesLocked"] and not (known.get(r["id"]) or {}).get("locked")
        known[r["id"]] = {"locked": r["candidatesLocked"], "at": NOW.strftime("%Y-%m-%d")}
    return {"ballots": rows, "scanned": len(items)}


def html_unescape(t):
    import html as _h
    return _h.unescape(t)


def main():
    os.makedirs(OUT, exist_ok=True)
    state = load("state.json", {})
    data = load("data.json", {})
    desks = [("food", food), ("contracts", contracts), ("petitions", petitions), ("prices", prices), ("crime", crime), ("insolvency", insolvency)]
    # elections(): Democracy Club's API needs a free API key (401 without one, 20 Nov 2026). The owner got one on
    # 25 Nov 2026; it is the GitHub secret DEMOCRACY_CLUB_KEY, passed in by .github/workflows/datadesk.yml.
    if os.environ.get("DEMOCRACY_CLUB_KEY", "").strip():
        desks.append(("elections", elections))
    for name, fn in desks:
        if ONLY and name not in ONLY:
            continue
        try:
            data[name] = fn(state)
            print(name, "ok")
        except Exception as e:
            print(name, "FAILED", type(e).__name__, str(e)[:300])
            old = data.get(name) if isinstance(data.get(name), dict) else None
            if old and not old.get("error"):
                old["stale"] = f"not refreshed this run ({type(e).__name__}); figures are from an earlier run today or yesterday"
            else:
                data[name] = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
    data["at"] = NOW.strftime(ISO)
    save("data.json", data); save("state.json", state)
    txt = digest(data)
    open(os.path.join(OUT, "latest.txt"), "w", encoding="utf-8").write(txt)
    print(txt[:6000])


if __name__ == "__main__":
    main()
