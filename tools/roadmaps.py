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

Runs in GitHub Actions (.github/workflows/roadmaps.yml), which can reach OpenStreetMap: Nominatim finds the road and
the main OpenStreetMap API gives the streets around it (one call each per story, within both services' usage rules). Map data
(c) OpenStreetMap contributors, ODbL; the caption carries the credit.

  python3 tools/roadmaps.py              all stories in the edition that need a map
  python3 tools/roadmaps.py --id X       one story, even if it was checked before
"""
import argparse, json, math, os, re, sys, time, urllib.error, urllib.parse, urllib.request, html

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import build  # story_pins and the Essex map data, so the town matches the story's own map

DB = os.path.join(ROOT, "data", "roadmaps.json")
OUT = os.path.join(ROOT, "img", "maps")
UA = "TheSeax/1.0 (https://theseax.com; news@theseax.com)"
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


def http_get(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en-GB"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (400, 404, 509):
                raise
            last = e
        except Exception as e:
            last = e
        time.sleep(3 + i * 5)
    raise RuntimeError(f"{url[:60]}: {last}")


# ---- geometry (Web Mercator metres, good enough at town scale) ----
R = 6378137.0
def merc(lon, lat):
    return R * math.radians(lon), R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))

def unmerc(x, y):
    return math.degrees(x / R), math.degrees(2 * math.atan(math.exp(y / R)) - math.pi / 2)


def nominatim(name, town):
    d = 0.065
    q = urllib.parse.urlencode({"q": f"{name}, {town['name']}", "format": "jsonv2", "limit": 15, "dedupe": 0, "countrycodes": "gb",
                                "viewbox": f"{town['lon'] - d * 1.6:.5f},{town['lat'] + d:.5f},{town['lon'] + d * 1.6:.5f},{town['lat'] - d:.5f}", "bounded": 1})
    time.sleep(1.2)  # Nominatim's limit is one request a second
    res = json.loads(http_get("https://nominatim.openstreetmap.org/search?" + q))
    norm = lambda x: re.sub(r"[^a-z]", "", x.lower())
    return [r for r in res if r.get("category") == "highway" and norm(r.get("name") or "") == norm(name)]


def osm_map(view):
    """Everything OpenStreetMap holds inside the view (the main API's map call), as Overpass-style elements."""
    import xml.etree.ElementTree as ET
    x, y, vw, vh = view
    w, s_ = unmerc(x, y); e, n = unmerc(x + vw, y + vh)
    raw = http_get(f"https://api.openstreetmap.org/api/0.6/map?bbox={w:.6f},{s_:.6f},{e:.6f},{n:.6f}")
    root = ET.fromstring(raw)
    nodes, ways, els = {}, {}, []
    tags = lambda el: {t.get("k"): t.get("v") for t in el.findall("tag")}
    for nd in root.iter("node"):
        nodes[nd.get("id")] = (float(nd.get("lat")), float(nd.get("lon")))
        tg = tags(nd)
        if tg.get("railway") in ("station", "halt"):
            els.append({"type": "node", "lat": nodes[nd.get("id")][0], "lon": nodes[nd.get("id")][1], "tags": tg})
    for wy in root.iter("way"):
        refs = [r.get("ref") for r in wy.findall("nd") if r.get("ref") in nodes]
        if len(refs) < 2:
            continue
        el = {"type": "way", "id": wy.get("id"), "tags": tags(wy), "refs": refs,
              "geometry": [{"lat": nodes[r][0], "lon": nodes[r][1]} for r in refs]}
        ways[wy.get("id")] = el
        els.append(el)
    # parks, water and woods drawn as multipolygon relations: draw their outer ways with the relation's tags
    for rel in root.iter("relation"):
        tg = tags(rel)
        if tg.get("type") != "multipolygon":
            continue
        for m in rel.findall("member"):
            if m.get("type") == "way" and m.get("role") in ("outer", "") and m.get("ref") in ways:
                w_ = ways[m.get("ref")]
                if w_["refs"][0] == w_["refs"][-1]:
                    els.append({"type": "way", "tags": tg, "geometry": w_["geometry"]})
    return els


def find_road(name, town):
    """The road's pieces, the map view and the map data, or (None, reason)."""
    hits = nominatim(name, town)
    if not hits:
        return None, f"no road called {name} near {town['name']}"
    pts = [merc(float(h["lon"]), float(h["lat"])) for h in hits]
    if max((math.dist(a, b) for a in pts for b in pts), default=0) > 6000:
        return None, f"roads called {name} far apart near {town['name']}: not sure which"
    bxs = []
    for h in hits:
        s_, n, w, e = map(float, h["boundingbox"])
        bxs += [merc(w, s_), merc(e, n)]
    view = view_for([bxs], town)
    try:
        els = osm_map(view)
    except urllib.error.HTTPError as e:  # too much data: a tighter view
        x, y, vw, vh = view
        view = (x + vw * .2, y + vh * .2, vw * .6, vh * .6)
        els = osm_map(view)
    norm = lambda x: re.sub(r"[^a-z]", "", (x or "").lower())
    mine = [el for el in els if el["type"] == "way" and "highway" in el["tags"] and norm(el["tags"].get("name")) == norm(name)
            and el["tags"].get("highway") not in ("footway", "path", "cycleway", "steps", "bridleway", "proposed", "construction")]
    if not mine:
        return None, f"{name} not found in the map data"
    # join pieces that share a node: one real road is many OSM ways
    groups = []
    for el in mine:
        hit = [g for g in groups if any(set(el["refs"]) & set(o["refs"]) for o in g)]
        merged = [el]
        for g in hit:
            merged += g; groups.remove(g)
        groups.append(merged)
    if len(groups) > 1:
        gs = [[merc(p["lon"], p["lat"]) for el in g for p in el["geometry"]] for g in groups]
        if any(min(math.dist(a, b) for a in g1 for b in g2) > 300 for i, g1 in enumerate(gs) for g2 in gs[i + 1:]):
            return None, f"{len(groups)} different roads called {name} near {town['name']}: not sure which"
    segs = [[merc(p["lon"], p["lat"]) for p in el["geometry"]] for el in mine]
    return (segs, view, els), "ok"


def view_for(segs, town):
    xs = [p[0] for s in segs for p in s]; ys = [p[1] for s in segs for p in s]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    span = max(x1 - x0, (y1 - y0) * W / H)
    vw = min(max(span * 1.45, 750), 2500)
    if span * 1.45 > 2500:  # a very long road: centre on the part nearest the town
        tx, ty = merc(town["lon"], town["lat"])
        cx, cy = min(((p[0], p[1]) for s in segs for p in s), key=lambda p: math.dist(p, (tx, ty)))
    else:
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    vh = vw * H / W
    return cx - vw / 2, cy - vh / 2, vw, vh


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
            hw = t["highway"]
            if hw in ("path", "cycleway", "steps", "bridleway", "track", "footway", "corridor"):
                if vw < 1600 and t.get("area") != "yes":
                    roads.append((dict(t, highway="footway"), g))
            elif hw == "service":
                if vw < 1600 and t.get("service") not in ("parking_aisle", "driveway", "drive-through"):
                    roads.append((t, g))
            elif hw in ("motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street",
                        "pedestrian", "road", "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link"):
                roads.append((t, g))
        elif "railway" in t:
            rails.append(g)
        elif t.get("natural") == "coastline":
            coast.append(g)
        elif t.get("waterway") in ("river", "canal", "stream"):
            waters.append(("line", g, t.get("waterway")))
        elif t.get("natural") == "water" or t.get("waterway") in ("riverbank", "dock") or t.get("landuse") in ("reservoir", "basin"):
            waters.append(("area", g, None))
        elif "building" in t and t.get("building") != "no":
            builds.append(g)
        else:
            kind = t.get("natural") or t.get("leisure") or t.get("landuse") or t.get("amenity")
            if kind not in ("beach", "wetland", "wood", "forest", "cemetery", "grave_yard", "allotments", "pitch", "golf_course", "park",
                            "garden", "recreation_ground", "grass", "meadow", "village_green", "common", "nature_reserve", "scrub", "heath"):
                continue
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
               f'<text x="28" y="276" font-size="22" font-weight="800" fill="#14171f">{E(town["name"])}</text></g>')
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
                got, why = find_road(name, town)
            except Exception as e:
                print(sid, name, "ERROR", e); entry = None; break
            print(sid, "|", name, "|", town["name"], "|", why)
            if not got:
                entry["none"] = why; continue
            segs, view, els = got
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
