#!/usr/bin/env python3
"""Street maps for stories that name a road (owner, 25 Nov 2026: "Can maps be more specific if a road is mentioned -
so like big map then placed where the road is?" ... "LOVE the maps !!! Let's do it").

For each story in edition.json that names a road ("in Clifftown Road, Southend"), this finds the road in OpenStreetMap
near the story's town, draws a street map in The Seax's style with the road picked out in red and a small Essex map in
the corner, saves it as img/maps/<story id>.svg and records it in data/roadmaps.json. Both page builders (tools/build.py
and index.html) put it inside the story, after the paragraph that first names the road, captioned "Where it happened".

Safety rules:
  * only a road we can place for certain: it must be a real road of that name within 4.5 km of the story's town, and
    there must be only one such road (two "Station Road"s in the same area means no map);
  * never a home address: a road named as where someone lives ("of Sutton Road", "from Sutton Road", "lives in ...")
    is skipped, and no house number is ever drawn; the whole road is highlighted, never a point on it;
  * story field "roadMap": false turns it off for that story; "roadMap": "Clifftown Road" picks the road by hand.

Runs in GitHub Actions (.github/workflows/roadmaps.yml), which can reach OpenStreetMap's Overpass API. Map data
(c) OpenStreetMap contributors, ODbL; the caption carries the credit.

  python3 tools/roadmaps.py              all stories in the edition that need a map
  python3 tools/roadmaps.py --id X       one story, even if it was checked before
"""
import argparse, json, math, os, re, sys, time, urllib.parse, urllib.request, html

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import build  # story_pins and the Essex map data, so the town matches the story's own map

DB = os.path.join(ROOT, "data", "roadmaps.json")
OUT = os.path.join(ROOT, "img", "maps")
UA = "TheSeax/1.0 (https://theseax.com; news@theseax.com)"
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter",
            "https://overpass.private.coffee/api/interpreter"]
W, H = 1200, 750
RED = "#c8102e"
FONT = "system-ui,-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
E = lambda s: html.escape(str(s), quote=True)

SUFFIX = r"(?:Road|Street|Avenue|Lane|Way|Drive|Close|Crescent|Hill|Parade|Grove|Gardens|Place|Terrace|Rise|Walk|Square|Chase|Mews|Boulevard|Row|Broadway|Esplanade|Promenade|Bypass|By-[Pp]ass)"
WORD = r"[A-Z][a-z'’]+(?:-[A-Z]?[a-z]+)?"
ROAD_RX = re.compile(r"\b((?:" + WORD + r"\s){1,3}" + SUFFIX + r")\b")
GRAM = {"The", "On", "In", "At", "Near", "And", "By", "Off", "Along", "Into", "Onto", "From", "To", "Of", "A", "An", "Police",
        "Officers", "Essex", "That", "This", "Its", "Their", "Our", "New", "Between", "Outside", "Opposite", "Junction", "Where", "When", "While", "After", "Before", "Around"}
TOWNS = {"London", "Southend", "Chelmsford", "Colchester", "Basildon", "Harlow", "Brentwood", "Witham",
        "Braintree", "Maldon", "Clacton", "Rayleigh", "Rochford", "Benfleet", "Grays", "Thurrock", "Wickford", "Billericay",
        "Leigh", "Westcliff", "Shoeburyness", "Canvey", "Epping", "Loughton", "Saffron", "Walden", "Halstead", "Frinton",
        "Walton", "Harwich", "Dovercourt", "Burnham", "Tiptree", "Coggeshall", "Wivenhoe", "Brightlingsea", "Mersea",
        "Hadleigh", "Laindon", "Pitsea", "Tilbury", "Stanford", "Corringham", "Ongar", "Waltham", "Abbey", "Dunmow", "Thaxted"}
# a road named as someone's home: "of Sutton Road", "from Sutton Road", "who lives in Sutton Road"
HOME_RX = re.compile(r"(?:\bof|\bfrom|\blives?\s+(?:in|on|at)|\bliving\s+(?:in|on|at)|\bhomes?\s+(?:in|on|at)|\baddress\s+(?:in|on|at)|\bresident\s+of)\s+(?:\d+[a-z]?\s+)?$", re.I)
NOT_ROADS = {"Downing Street", "Fenchurch Street", "Liverpool Street", "Wall Street", "Fleet Street", "Abbey Road",
             "Coronation Street", "Baker Street", "Oxford Street", "Regent Street", "Bond Street"}
ROAD_KINDS = "motorway|trunk|primary|secondary|tertiary|unclassified|residential|living_street|pedestrian|service|road|motorway_link|trunk_link|primary_link|secondary_link|tertiary_link"


def mentions(it):
    """Roads the story names, in order: (name, paragraph index for the map, 0 if only in the headline or summary)."""
    force = it.get("roadMap")
    if isinstance(force, str) and force.strip():
        return [(force.strip(), first_para(it, force.strip()))]
    found = []
    fields = [("headline", it.get("headline")), ("place", it.get("place")), ("summary", it.get("summary"))]
    fields += [(i, p) for i, p in enumerate(it.get("body") or []) if isinstance(p, str)][:3]
    for where, txt in fields:
        for m in ROAD_RX.finditer(str(txt or "")):
            words = m.group(1).split()
            while words and (words[0] in GRAM or (len(words) > 2 and (words[0] in TOWNS or re.search(r"['’]s$", words[0])))):
                words = words[1:]
            if len(words) < 2:
                continue
            name = " ".join(words)
            if name in NOT_ROADS or name.lower() in PLACES or HOME_RX.search(str(txt)[:m.start() + (len(m.group(1)) - len(name))]):
                continue
            if name not in [f[0] for f in found]:
                found.append((name, first_para(it, name)))
    return found


PLACES = {k.lower() for k in build._map_data()["P"]}


def first_para(it, name):
    for i, p in enumerate(it.get("body") or []):
        if name.lower() in str(p).lower():
            return i
    return 0


def town_of(it):
    pins = build.story_pins(it)
    if not pins:
        return None
    M = build._map_data()["M"]
    p = pins[0]
    return {"name": p["name"], "district": p.get("d"), "lon": p["x"] / (M["kx"] * M["k"]) + M["lon0"], "lat": M["lat1"] - p["y"] / M["k"]}


def overpass(q):
    last = None
    for url in OVERPASS:
        for attempt in range(2):
            try:
                req = urllib.request.Request(url, data=urllib.parse.urlencode({"data": q}).encode(), headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=90) as r:
                    return json.load(r)
            except Exception as e:  # busy server: try again, then the next one
                last = e
                time.sleep(4 + attempt * 6)
    raise RuntimeError(f"Overpass failed: {last}")


# ---- geometry (Web Mercator metres, good enough at town scale) ----
R = 6378137.0
def merc(lon, lat):
    return R * math.radians(lon), R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))

def unmerc(x, y):
    return math.degrees(x / R), math.degrees(2 * math.atan(math.exp(y / R)) - math.pi / 2)


def find_road(name, town):
    q = f'[out:json][timeout:40];way[highway~"^({ROAD_KINDS})$"][name="{name}"](around:4500,{town["lat"]:.6f},{town["lon"]:.6f});out geom;'
    ways = [w for w in overpass(q).get("elements", []) if w.get("geometry")]
    if not ways:
        return None, "no road of that name near " + town["name"]
    segs = [[merc(p["lon"], p["lat"]) for p in w["geometry"]] for w in ways]
    # group touching pieces: one real road is usually split into many OSM ways
    groups = []
    for s in segs:
        hit = [g for g in groups if any(math.dist(a, b) < 60 for t in g for a in (t[0], t[-1]) for b in (s[0], s[-1]))
               or any(math.dist(a, b) < 25 for t in g for a in t[::3] for b in s[::3])]
        merged = [s]
        for g in hit:
            merged += g; groups.remove(g)
        groups.append(merged)
    if len(groups) > 1:
        def gap(g1, g2):
            return min(math.dist(a, b) for t1 in g1 for a in t1[::2] for t2 in g2 for b in t2[::2])
        if any(gap(a, b) > 300 for i, a in enumerate(groups) for b in groups[i + 1:]):
            return None, f"{len(groups)} different roads called {name} near {town['name']}: not sure which"
        groups = [[s for g in groups for s in g]]
    return groups[0], "ok"


def view_for(segs, town):
    xs = [p[0] for s in segs for p in s]; ys = [p[1] for s in segs for p in s]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    span = max(x1 - x0, (y1 - y0) * W / H)
    vw = min(max(span * 1.45, 750), 4000)
    if span * 1.45 > 4000:  # a very long road: centre on the part nearest the town
        tx, ty = merc(town["lon"], town["lat"])
        cx, cy = min(((p[0], p[1]) for s in segs for p in s), key=lambda p: math.dist(p, (tx, ty)))
    else:
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    vh = vw * H / W
    return cx - vw / 2, cy - vh / 2, vw, vh


def surroundings(view, svc):
    x, y, vw, vh = view
    w, s = unmerc(x, y); e, n = unmerc(x + vw, y + vh)
    bb = f"{s:.6f},{w:.6f},{n:.6f},{e:.6f}"
    kinds = ROAD_KINDS if svc else ROAD_KINDS.replace("|service", "")
    q = (f'[out:json][timeout:60];('
         f'way[highway~"^({kinds}|footway)$"]({bb});'
         f'way[railway~"^(rail|light_rail|narrow_gauge)$"]({bb});'
         f'way[natural~"^(water|beach|wetland|wood|coastline)$"]({bb});'
         f'way[waterway~"^(river|canal|riverbank|dock|stream)$"]({bb});'
         f'way[leisure~"^(park|garden|recreation_ground|pitch|golf_course|common|nature_reserve)$"]({bb});'
         f'way[landuse~"^(grass|recreation_ground|cemetery|forest|meadow|village_green|allotments)$"]({bb});'
         f'way[amenity=grave_yard]({bb});way[building]["building"!~"^(house|residential|detached|semidetached_house|terrace|garage|garages|shed|bungalow|apartments)$"]({bb});'
         f'node[railway~"^(station|halt)$"]({bb});node[public_transport=station][railway]({bb});'
         f');out geom;')
    return overpass(q).get("elements", [])


def render(it, name, town, segs, view, els):
    x0, y0, vw, vh = view
    k = W / vw
    px = lambda p: ((p[0] - x0) * k, (y0 + vh - p[1]) * k)
    zf = max(.55, min(1.35, 1000 / vw))  # line widths grow when zoomed in
    def path(pts, close=False):
        q = [px(p) for p in pts]
        return "M" + "L".join(f"{a:.1f} {b:.1f}" for a, b in q) + ("Z" if close else "")
    def geo(el):
        return [merc(g["lon"], g["lat"]) for g in el.get("geometry") or []]
    fills, waters, rails, builds, roads, stations, coast = [], [], [], [], [], [], []
    for el in els:
        t = el.get("tags") or {}
        if el["type"] == "node":
            nm = t.get("name")
            if nm and not any(nm == s[0] for s in stations):
                stations.append((nm, merc(el["lon"], el["lat"])))
            continue
        g = geo(el)
        if len(g) < 2:
            continue
        if "highway" in t:
            roads.append((t, g))
        elif "railway" in t:
            rails.append(g)
        elif t.get("natural") == "coastline":
            coast.append(g)
        elif t.get("waterway") in ("river", "canal", "stream"):
            waters.append(("line", g, t.get("waterway")))
        elif t.get("natural") == "water" or t.get("waterway") in ("riverbank", "dock"):
            waters.append(("area", g, None))
        elif "building" in t:
            builds.append(g)
        else:
            kind = t.get("natural") or t.get("leisure") or t.get("landuse") or t.get("amenity")
            col = {"beach": "#efe6cc", "wetland": "#e3e6d3", "wood": "#cfe0bf", "forest": "#cfe0bf", "cemetery": "#dbe5d2",
                   "grave_yard": "#dbe5d2", "allotments": "#e2e8cf", "pitch": "#cde3bd", "golf_course": "#d5e7c6"}.get(kind, "#d9e9c8")
            fills.append((col, g))
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" font-family="{E(FONT)}">',
           f'<rect width="{W}" height="{H}" fill="#f3efe6"/>']
    for col, g in fills:
        out.append(f'<path d="{path(g, True)}" fill="{col}"/>')
    for kind, g, ww in waters:
        out.append(f'<path d="{path(g, True)}" fill="#bcd8e8"/>' if kind == "area" else
                   f'<path d="{path(g)}" fill="none" stroke="#bcd8e8" stroke-width="{(10 if ww != "stream" else 4) * zf:.1f}" stroke-linecap="round"/>')
    for g in coast:
        out.append(f'<path d="{path(g)}" fill="none" stroke="#bcd8e8" stroke-width="{26 * zf:.1f}" stroke-linejoin="round"/>')
    for g in builds:
        out.append(f'<path d="{path(g, True)}" fill="#e2dccf" stroke="#d6cfbf" stroke-width=".6"/>')
    width = {"motorway": 15, "trunk": 14, "primary": 13, "secondary": 12, "tertiary": 11, "motorway_link": 8, "trunk_link": 8,
             "primary_link": 8, "secondary_link": 8, "tertiary_link": 8, "unclassified": 9, "residential": 9, "living_street": 8,
             "road": 8, "pedestrian": 9, "service": 5, "footway": 2.2}
    rank = lambda t: list(width).index(t.get("highway")) if t.get("highway") in width else 99
    roads.sort(key=lambda r: -rank(r[0]))
    cas, body = [], []
    for t, g in roads:
        hw = t.get("highway"); wd = width.get(hw, 6) * zf
        if hw == "footway":
            body.append(f'<path d="{path(g)}" fill="none" stroke="#fbf8f1" stroke-width="{wd:.1f}" stroke-dasharray="{4 * zf:.1f} {3 * zf:.1f}"/>')
            continue
        fill = "#f7d9a6" if hw in ("motorway", "trunk", "primary", "motorway_link", "trunk_link", "primary_link") else "#f9f1f4" if hw == "pedestrian" else "#ffffff"
        cas.append(f'<path d="{path(g)}" fill="none" stroke="#c9c1b1" stroke-width="{wd + 2.4 * zf:.1f}" stroke-linecap="round" stroke-linejoin="round"/>')
        body.append(f'<path d="{path(g)}" fill="none" stroke="{fill}" stroke-width="{wd:.1f}" stroke-linecap="round" stroke-linejoin="round"/>')
    out += cas + body
    for g in rails:
        out.append(f'<path d="{path(g)}" fill="none" stroke="#8c8c8c" stroke-width="{4.5 * zf:.1f}"/>'
                   f'<path d="{path(g)}" fill="none" stroke="#fff" stroke-width="{2.2 * zf:.1f}" stroke-dasharray="{9 * zf:.1f} {9 * zf:.1f}"/>')
    # the road itself
    tp = [path(s) for s in segs]
    for d in tp:
        out.append(f'<path d="{d}" fill="none" stroke="{RED}" stroke-opacity=".22" stroke-width="{30 * max(zf, .8):.1f}" stroke-linecap="round" stroke-linejoin="round"/>')
    for d in tp:
        out.append(f'<path d="{d}" fill="none" stroke="{RED}" stroke-width="{12 * max(zf, .8):.1f}" stroke-linecap="round" stroke-linejoin="round"/>')
    # street names along the roads (not the story's road, which gets the big label)
    boxes = [(0, 0, 330, 300)]  # the Essex corner map
    labels = []
    best = {}
    for t, g in roads:
        nm = t.get("name")
        if not nm or nm == name or t.get("highway") in ("footway", "service"):
            continue
        q = [px(p) for p in g]
        for a, b in zip(q, q[1:]):
            L = math.dist(a, b)
            if L > best.get(nm, (0,))[0]:
                best[nm] = (L, a, b, rank(t))
    fs = 21
    for nm, (L, a, b, rk) in sorted(best.items(), key=lambda kv: (kv[1][3], -kv[1][0])):
        tw = len(nm) * fs * .56
        if L < tw * 1.05 or len(labels) >= 16:
            continue
        cx, cy = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
        if ang > 90: ang -= 180
        if ang < -90: ang += 180
        c, s_ = abs(math.cos(math.radians(ang))), abs(math.sin(math.radians(ang)))
        hw, hh = (tw * c + fs * s_) / 2, (tw * s_ + fs * c) / 2
        bx = (cx - hw, cy - hh, cx + hw, cy + hh)
        if bx[0] < 6 or bx[2] > W - 6 or bx[1] < 6 or bx[3] > H - 40 or any(bx[0] < o[2] and bx[2] > o[0] and bx[1] < o[3] and bx[3] > o[1] for o in boxes):
            continue
        boxes.append(bx)
        labels.append(f'<text x="{cx:.1f}" y="{cy:.1f}" transform="rotate({ang:.1f} {cx:.1f} {cy:.1f})" font-size="{fs}" text-anchor="middle" '
                      f'dominant-baseline="central" fill="#5b564c" stroke="#f3efe6" stroke-width="5" paint-order="stroke" stroke-linejoin="round">{E(nm)}</text>')
    for nm, p in stations[:3]:
        x, y = px(p)
        if not (20 < x < W - 20 and 20 < y < H - 50):
            continue
        lab = nm if re.search(r"station", nm, re.I) else nm + " station"
        tw = len(lab) * 19 * .56
        tx = x + 16 if x + 16 + tw < W - 10 else x - 16 - tw
        boxes.append((tx, y - 14, tx + tw, y + 14))
        labels.append(f'<g><circle cx="{x:.1f}" cy="{y:.1f}" r="9" fill="#1d4f91" stroke="#fff" stroke-width="3"/>'
                      f'<text x="{tx:.1f}" y="{y + 7:.1f}" font-size="19" font-weight="700" fill="#1d4f91" stroke="#f3efe6" stroke-width="5" paint-order="stroke">{E(lab)}</text></g>')
    out += labels
    # big label for the story's road, above its middle (below if there is no room)
    allp = [px(p) for s in segs for p in s]
    vis = [p for p in allp if 0 <= p[0] <= W and 0 <= p[1] <= H] or allp
    vis.sort(key=lambda p: (p[0], p[1]))
    mx, my = vis[len(vis) // 2]
    big = 34; tw = len(name) * big * .6 + 40; th = 56
    lx = min(max(mx - tw / 2, 340 if my < 310 else 12), W - tw - 12)
    above = my - 40 - th > 12 and not (lx < 330 and my - 40 - th < 300)
    ly = my - 40 - th if above else min(my + 40, H - th - 46)
    tip = f'{mx - 13:.1f},{ly + th:.1f} {mx + 13:.1f},{ly + th:.1f} {mx:.1f},{ly + th + 18:.1f}' if above else f'{mx - 13:.1f},{ly:.1f} {mx + 13:.1f},{ly:.1f} {mx:.1f},{ly - 18:.1f}'
    if lx + 20 < mx < lx + tw - 20:
        out.append(f'<polygon points="{tip}" fill="#14171f"/>')
    out.append(f'<rect x="{lx:.1f}" y="{ly:.1f}" width="{tw:.1f}" height="{th}" rx="12" fill="#14171f"/>'
               f'<text x="{lx + tw / 2:.1f}" y="{ly + th / 2 + 1:.1f}" font-size="{big}" font-weight="800" fill="#fff" text-anchor="middle" dominant-baseline="central">{E(name)}</text>')
    # scale bar
    for m_ in (50, 100, 200, 250, 500, 1000):
        if m_ * k >= 110:
            break
    sb = m_ * k
    out.append(f'<g><rect x="14" y="{H - 44}" width="{sb + 92:.1f}" height="32" rx="6" fill="#fff" opacity=".85"/>'
               f'<path d="M24 {H - 22}h{sb:.1f}" stroke="#14171f" stroke-width="4"/><path d="M24 {H - 30}v16M{24 + sb:.1f} {H - 30}v16" stroke="#14171f" stroke-width="3"/>'
               f'<text x="{sb + 34:.1f}" y="{H - 21}" font-size="18" font-weight="700" fill="#14171f" dominant-baseline="central">{m_ if m_ < 1000 else 1} {"m" if m_ < 1000 else "km"}</text></g>')
    att = "© OpenStreetMap contributors"
    out.append(f'<text x="{W - 12}" y="{H - 14}" font-size="17" text-anchor="end" fill="#55524b" stroke="#f3efe6" stroke-width="5" paint-order="stroke">{att}</text>')
    # Essex corner map: the county with the story's district lit and a red ring where the street map is
    M = build._map_data()["M"]
    lon, lat = unmerc(x0 + vw / 2, y0 + vh / 2)
    ex, ey = (lon - M["lon0"]) * M["kx"] * M["k"], (M["lat1"] - lat) * M["k"]
    dpaths = "".join(f'<path d="{d}" fill="{RED if n == town.get("district") else "#e6dfd0"}" stroke="#fff" stroke-width="2.5"/>' for n, d in M["districts"].items())
    out.append(f'<g><rect x="14" y="14" width="310" height="282" rx="10" fill="#fff" stroke="#d6cfbf" stroke-width="1.5"/>'
               f'<svg x="22" y="22" width="294" height="226" viewBox="20 10 {M["w"] - 40} {M["h"] - 60}" preserveAspectRatio="xMidYMid meet">'
               f'<rect x="-50" y="-50" width="{M["w"] + 100}" height="{M["h"] + 100}" fill="#d3e6f0"/><path d="{M["context"]}" fill="#f1ede4"/>{dpaths}'
               f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="22" fill="none" stroke="#14171f" stroke-width="7"/></svg>'
               f'<text x="28" y="276" font-size="22" font-weight="800" fill="#14171f">{E(town["name"])}, Essex</text></g>')
    out.append("</svg>")
    return "".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id")
    ap.add_argument("--max", type=int, default=8)
    a = ap.parse_args()
    ed = json.load(open(os.path.join(ROOT, "edition.json"), encoding="utf-8"))
    db = json.load(open(DB, encoding="utf-8")) if os.path.exists(DB) else {}
    os.makedirs(OUT, exist_ok=True)
    done = 0
    for it in ed.get("stories") or []:
        sid = it.get("id")
        if not sid or (a.id and sid != a.id) or it.get("roadMap") is False or re.search(r"week-ahead|round-?up|whats-on", sid):
            continue
        roads = mentions(it)
        town = town_of(it)
        sig = json.dumps([[r[0] for r in roads], town and town["name"], it.get("roadMap")])
        if not a.id and sid in db and db[sid].get("sig") == sig:
            continue
        if not roads or not town:
            db[sid] = {"sig": sig, "none": "no road named" if not roads else "no town to search near"}
            continue
        if done >= a.max:
            break
        done += 1
        entry = {"sig": sig, "none": ""}
        for name, after in roads[:3]:
            try:
                segs, why = find_road(name, town)
            except Exception as e:
                print(sid, name, "ERROR", e); entry = None; break
            print(sid, "|", name, "|", town["name"], "|", why)
            if not segs:
                entry["none"] = why; continue
            view = view_for(segs, town)
            try:
                els = surroundings(view, view[2] < 1600)
            except Exception as e:
                print(sid, "surroundings ERROR", e); entry = None; break
            svg = render(it, name, town, segs, view, els)
            open(os.path.join(OUT, sid + ".svg"), "w", encoding="utf-8").write(svg)
            txt = " ".join([str(it.get("headline") or ""), str(it.get("summary") or "")] + [str(x) for x in (it.get("body") or [])[:3]])
            incident = re.search(r"\b(attack\w*|robb\w*|crash\w*|collision|fire|blaze|stabb\w*|assault\w*|thef(t|ts)|stole\w*|burglar\w*|"
                                 r"appeal|injur\w*|died|death|killed|arrest\w*|shoplift\w*|raid\w*|shot|shooting|incident|"
                                 r"sinkhole|flood\w*|derail\w*|closed|closure|cannabis)\b", txt, re.I)
            entry = {"sig": sig, "kicker": "Where it happened" if incident else "On the map", "road": name, "town": town["name"], "src": f"/img/maps/{sid}.svg", "w": W, "h": H,
                     "after": after, "made": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            print(sid, "map", len(svg) // 1024, "KB")
            break
        if entry is not None:
            db[sid] = entry
        time.sleep(2)
    json.dump(db, open(DB, "w", encoding="utf-8"), indent=1, ensure_ascii=False, sort_keys=True)
    open(DB, "a").write("\n")


if __name__ == "__main__":
    main()
