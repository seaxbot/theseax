#!/usr/bin/env python3
"""Build The Seax's static pages from edition.json.

Run from anywhere:  python3 tools/build.py   (options: --briefing-now, --out DIR)

Writes, inside the repository:
  story/<id>/index.html    one page per story, kept after the story leaves the edition
  data/archive.json        index of every story page ever built
  about/index.html         about, contact and corrections page
  briefing/<date>/         the daily "Essex at 7" briefing (made once a day, 06:30 to 12:00 UK)
  briefing/index.html      latest briefing
  briefing.xml             RSS feed of briefings (for RSS-to-email)
  feed.xml                 RSS feed of the latest stories
  sitemap.xml, news-sitemap.xml
  index.html               only the config block between <!--seax-config--> markers

Uses only the Python standard library. Never touches edition.json.
"""
import json, os, re, sys, html, shutil, argparse
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from email.utils import format_datetime
from urllib.parse import urlparse, quote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UK = ZoneInfo("Europe/London")
CFG = json.load(open(os.path.join(ROOT, "tools", "site.json"), encoding="utf-8"))
SITE = CFG["site"].rstrip("/")
NOW = datetime.now(timezone.utc)

E = lambda s: html.escape(str(s if s is not None else ""), quote=True)

# ---------- helpers ----------
ICON_COLOUR = {
    "news": "#3a3f4b", "police": "#1d4e9e", "court": "#3c3a7a", "crime": "#1d4e9e", "appeal": "#1d4e9e", "tribute": "#55596a",
    "council": "#1b2a44", "fire": "#b3122b", "ambulance": "#1d7448", "health": "#1d7448", "business": "#8a6414", "retail": "#8a6414",
    "halloween": "#a8501a", "history": "#6b5638", "football": "#0f5b84", "racing": "#0f5b84", "cricket": "#0f5b84", "sport": "#0f5b84",
    "community": "#1a6e6b", "charity": "#1a6e6b", "volunteering": "#1a6e6b", "wildlife": "#3a6b34", "environment": "#2b6e60",
    "transport": "#344559", "weather": "#356f9f", "whatson": "#8f1546", "property": "#7a5228", "education": "#3a4a8f",
}
CARD_FOR = {
    "police": "police", "crime": "police", "appeal": "police", "court": "court", "council": "council", "politics": "council",
    "fire": "fire", "ambulance": "health", "health": "health", "business": "business", "retail": "business", "property": "property",
    "transport": "transport", "weather": "weather", "community": "community", "charity": "community", "volunteering": "community",
    "tribute": "community", "wildlife": "environment", "environment": "environment", "whatson": "whatson", "halloween": "whatson",
    "history": "history", "education": "education", "football": "football", "cricket": "cricket", "racing": "racing", "sport": "sport",
}
TAG_ICON = {"police": "police", "crime": "police", "court": "court", "appeal": "appeal", "tribute": "tribute", "council": "council",
            "politics": "council", "environment": "environment", "business": "business", "health": "health", "transport": "transport",
            "property": "property", "education": "education", "history": "history", "what's on": "whatson", "halloween": "halloween",
            "community": "community", "charity": "charity", "volunteering": "volunteering", "wildlife": "wildlife", "fire": "fire",
            "ambulance": "ambulance", "football": "football", "cricket": "cricket", "racing": "racing", "sport": "sport",
            "ice hockey": "sport", "rugby": "sport"}
SECTION_LABEL = {"news": "News", "sport": "Sport", "official": "Public Services", "courts": "Courts",
                 "community": "Community", "features": "Features", "councilwatch": "Council Watch"}

def icon_of(it, sec):
    if sec == "councilwatch":
        return "council"
    ic = str(it.get("icon") or "").lower()
    if ic in ICON_COLOUR:
        return ic
    tag = str(it.get("tag") or "").lower()
    if tag in TAG_ICON:
        return TAG_ICON[tag]
    if sec == "sport":
        return "sport"
    return "news"

ROAD_OG = [("a130", re.compile(r"\bA130\b")), ("a127", re.compile(r"\bA127\b")),
           ("a13", re.compile(r"\bA13\b")), ("a12", re.compile(r"\bA12\b")),
           ("a414", re.compile(r"\bA414\b")), ("m11", re.compile(r"\bM11\b")),
           ("m25", re.compile(r"\bM25\b"))]  # stories about these roads share their road sign

def road_of(it):
    """The first road named in the headline, else the summary, else the place (same rule as the page)."""
    for t in (it.get("headline"), it.get("summary"), it.get("place")):
        hits = [(m.start(), key) for key, rx in ROAD_OG for m in [rx.search(str(t or ""))] if m]
        if hits:
            return min(hits)[1]
    return None

# hospital stories share the owner's hospital photo (img/topics/hospital.jpg; share card img/og/hospital.jpg).
# Same rule as the page: a health story that mentions a hospital or A&E, or any story (not police, crime,
# court, appeal, tribute or fire) with a hospital or A&E in its headline.
HOSPITAL_RX = re.compile(r"\bhospitals?\b|\bA&E\b", re.I)
HOSPITAL_SKIP = {"police", "crime", "court", "appeal", "tribute", "fire"}
# police, crime and appeal stories share the owner's blue lights photo (img/topics/bluelights.jpg; share card
# img/og/bluelights.jpg). Same rule as the page's isPoliceStory: icon police, crime or appeal, or tag Police unless
# the icon is court, tribute, fire or ambulance.
POLICE_ICONS = {"police", "crime", "appeal"}
POLICE_TAG_SKIP = {"court", "tribute", "fire", "ambulance"}
# stories about police policy and politics keep the map (same as the page's POLICE_POLICY_RX)
POLICE_POLICY_RX = re.compile(r"\b(commissioners?|PFCC|mergers?|mega[ -]force|budgets?|precept|council tax|HMICFRS|inspections?|inspectorate)\b", re.I)
POLICE_PHOTOS = ["bluelights", "bluelights-2"]  # img/topics/<name>.jpg and share cards img/og/<name>.jpg, rotated like the page
POLICE_PICK = {}
OG_JPG = {"ambulance", "tiptree", "tiptree-2", "statefayre", "christmas-2", "hospital", "bluelights", "bluelights-2", "fireengine", "countyhall", "fog", "zoo", "stansted-1", "stansted-2", "stansted-3", "gaswork", "datacentre", "remembrance", "food", "harlowcollege", "christmas", "c2c", "mersea-1", "mersea-2", "mersea-3", "bus", "pool", "homeless"}
LIBRARY_PHOTOS = POLICE_PHOTOS + ["fireengine", "ambulance", "tiptree", "tiptree-2", "statefayre", "christmas-2", "countyhall", "fog", "zoo", "stansted-1", "stansted-2", "stansted-3", "gaswork", "datacentre", "remembrance", "food", "harlowcollege", "christmas", "c2c", "mersea-1", "mersea-2", "mersea-3", "bus", "pool", "homeless"]  # owner's library photos shown on story pages
LIBRARY_ALT = {"ambulance": "an ambulance with blue lights", "statefayre": "the State Fayre 2027 festival logo over a crowd at Hylands Park", "tiptree": "the Wilkin & Sons Tiptree sign", "tiptree-2": "the Wilkin & Sons Tiptree sign", "christmas-2": "a lit Christmas tree", "fog": "fog over a footpath and flats at dusk", "fireengine": "a fire engine", "countyhall": "County Hall, Chelmsford, home of Essex County Council", "zoo": "visitors watching elephants at Colchester Zoo", "stansted-1": "check-in desks at London Stansted Airport", "stansted-2": "the terminal concourse at London Stansted Airport", "stansted-3": "a bus outside the terminal at London Stansted Airport", "gaswork": "a worker fitting yellow gas pipe in a trench", "datacentre": "server racks in a data centre", "remembrance": "poppy wreaths laid at a war memorial", "food": "a plate of roast chicken, grains and roasted vegetables", "harlowcollege": "the entrance to Harlow College", "christmas": "red Christmas baubles on a fir garland", "c2c": "a c2c train in white and magenta livery near Ripple Lane, Barking", "mersea-1": "pastel beach huts on the sand at West Mersea", "mersea-2": "a long row of pastel beach huts on West Mersea beach", "mersea-3": "the sandy beach and the Blackwater estuary at West Mersea", "bus": "inside a bus, with a red stop button on a yellow pole", "homeless": "a man in a woolly hat sitting on a pavement, seen from behind", "pool": "an indoor swimming pool with lane ropes and steps"}
# Essex County Council stories use the owner's photo of County Hall, Chelmsford (owner's rule, Nov 2026), ahead of
# stock, town and map art. Road signs, police and fire photos still win. Same rule as the page's isCountyHallStory.
ECC_RX = re.compile(r"\bEssex County Council\b|\bCounty Hall\b", re.I)

def og_path(card):
    return f"/img/og/{card}.jpg" if card in OG_JPG else f"/img/og/{card}.png"

def is_hospital(it, sec):
    if sec == "sport":
        return False
    ic = icon_of(it, sec)
    if ic in HOSPITAL_SKIP:
        return False
    if is_road_incident(it, sec):
        return False
    head_ = str(it.get("headline") or "")
    both = head_ + " " + str(it.get("summary") or "")
    return bool(HOSPITAL_RX.search(head_) or (ic == "health" and HOSPITAL_RX.search(both)))

# road crashes and emergency road closures always use the blue lights photo (owner's rule, Nov 2026); planned
# closures (roadworks, parades, events) do not. Same rule as the page's isRoadIncident.
ROAD_CRASH_RX = re.compile(r"\b(crash(es|ed)?|collisions?|collided|accidents?|smash(es|ed)?|overturned|jack-?knifed|pile-?up|hit by an? (car|van|lorry|vehicle|bus)|(pedestrian|cyclist|motorcyclist|biker|driver) (was |is |has been )?(seriously |critically |badly |fatally )?(hit|struck|killed|injured|hurt|dies|died))\b", re.I)
ROAD_CLOSE_RX = re.compile(r"\b(closed|closures?|shut|blocked|reopen(s|ed)?|cordon(ed)?|diversions?|tailbacks?|queues?)\b", re.I)
ROAD_PLANNED_RX = re.compile(r"\b(road ?works?|works|resurfacing|maintenance|repairs?|parades?|remembrance|festival|events?|marathon|race|fun ?run|carnival|market|lights switch-on)\b", re.I)
ROAD_EMERGENCY_RX = re.compile(r"\b(police|emergency|incident|serious|ambulance|air ambulance|investigation)\b", re.I)

def is_road_incident(it, sec):
    if sec == "sport":
        return False
    ic, tag = icon_of(it, sec), str(it.get("tag") or "").lower()
    if ic in {"court", "tribute", "fire", "health"}:
        return False
    h = str(it.get("headline") or "")
    both = h + " " + str(it.get("summary") or "")
    if ROAD_CRASH_RX.search(h):
        return True
    if not (ic == "transport" or tag in {"transport", "travel", "police"} or ic == "police"):
        return False
    if ROAD_CRASH_RX.search(both):
        return True
    return bool(ROAD_CLOSE_RX.search(h) and ROAD_EMERGENCY_RX.search(both) and not ROAD_PLANNED_RX.search(h))

def is_police(it, sec):
    if sec == "sport":
        return False
    if POLICE_POLICY_RX.search(str(it.get("headline") or "")):
        return False
    if is_road_incident(it, sec):
        return True
    ic = icon_of(it, sec)
    if ic in POLICE_ICONS:
        return True
    return str(it.get("tag") or "").lower() == "police" and ic not in POLICE_TAG_SKIP

def pick_police(ed):
    """Same rotation as the page's policePhotoSrc: newest first across stories and official items, a variant
    from the id's hash, never the same as the police story just before it."""
    POLICE_PICK.clear()
    def tm(x):
        ts = [t.timestamp() for t in (parse_t(x.get("updated")), parse_t(x.get("time"))) if t]
        return max(ts) if ts else 0
    items = [(("news" if i < len(ed.get("stories") or []) else "official"), x)
             for i, x in enumerate((ed.get("stories") or []) + (ed.get("official") or [])) if isinstance(x, dict) and x.get("id")]
    items.sort(key=lambda p: -tm(p[1]))
    n, prev = len(POLICE_PHOTOS), -1
    for sec, x in items:
        if not is_police(x, sec):
            continue
        h = 0
        for c in str(x["id"]):
            h = (h * 31 + ord(c)) & 0xFFFFFFFF
        v = h % n
        if v == prev:
            v = (v + 1) % n
        POLICE_PICK[x["id"]] = v
        prev = v

def police_photo(it):
    return POLICE_PHOTOS[POLICE_PICK.get(it.get("id"), 0) % len(POLICE_PHOTOS)]

def is_fire(it, sec):
    """Fire stories use the owner's fire engine photo (same rule as the page's isFireStory)."""
    if sec == "sport" or POLICE_POLICY_RX.search(str(it.get("headline") or "")):
        return False
    return icon_of(it, sec) == "fire" or str(it.get("tag") or "").lower() == "fire"

# Ambulance stories use the owner's ambulance photo (owner's rule, 11 Nov 2026): icon or tag "ambulance", or a headline
# naming an ambulance or paramedics. Road crashes keep the police photo; air ambulance (helicopter) stories keep their
# usual art. Checked ahead of County Hall, hospital and stock art. Same rule as the page's isAmbulanceStory.
AMB_RX = re.compile(r"\bambulances?\b|\bparamedics?\b|\bEEAST\b", re.I)
AIR_AMB_RX = re.compile(r"\bair ambulance", re.I)

def is_ambulance(it, sec):
    if sec in ("sport", "councilwatch") or is_police(it, sec) or is_fire(it, sec):
        return False
    h = str(it.get("headline") or "")
    if AIR_AMB_RX.search(h):
        return False
    return icon_of(it, sec) == "ambulance" or str(it.get("tag") or "").lower() == "ambulance" or bool(AMB_RX.search(h))

# Tiptree jam (Wilkin & Sons) stories rotate the owner's two photos of the Wilkin & Sons Tiptree sign (owner's rule,
# 11 Nov 2026). Only stories about the company: Tiptree the village alone does not count. Police and fire stories keep
# their own photos. Same rule as the page's isTiptreeStory.
TIPTREE_RX = re.compile(r"\bWilkin(\s*(&|and)\s*Sons|'s)\b|\bTiptree (jams?|preserves|tea ?rooms?|jam museum|jam factory)\b|\bTiptree\b.{0,60}(?<!traffic )\bjams?\b|(?<!traffic )\bjams?\b.{0,60}\bTiptree\b", re.I)
TIPTREE_PHOTOS = ["tiptree", "tiptree-2"]

def is_tiptree(it, sec):
    if sec in ("sport", "councilwatch") or is_police(it, sec) or is_fire(it, sec) or is_ambulance(it, sec):
        return False
    h = host(it.get("url"))
    if h == "tiptree.com" or h.endswith(".tiptree.com"):
        return True
    return bool(TIPTREE_RX.search(" ".join(str(it.get(k) or "") for k in ("headline", "summary", "org"))))

# State Fayre (Hylands Park, Chelmsford) festival stories show the owner's State Fayre 2027 photo (owner's rule,
# 11 Nov 2026). Police, fire and ambulance stories keep their own photos. Same rule as the page's isStateFayreStory.
STATEFAYRE_RX = re.compile(r"\bState Fayre\b", re.I)

def is_statefayre(it, sec):
    if sec in ("sport", "councilwatch") or is_police(it, sec) or is_fire(it, sec) or is_ambulance(it, sec):
        return False
    return bool(STATEFAYRE_RX.search(" ".join(str(it.get(k) or "") for k in ("headline", "summary", "org", "title"))))

def id_pick(it, photos):
    h = 0
    for c in str(it.get("id") or ""):
        h = (h * 31 + ord(c)) & 0xFFFFFFFF
    return photos[h % len(photos)]

def is_county_hall(it, sec):
    if sec == "sport" or is_police(it, sec) or is_fire(it, sec):
        return False
    if sec == "councilwatch":
        return str(it.get("council") or "").lower() == "essex"
    h = host(it.get("url"))
    if h == "essex.gov.uk" or h.endswith(".essex.gov.uk"):
        return True
    if ECC_RX.search(" ".join(str(it.get(k) or "") for k in ("headline", "source", "org"))):
        return True
    return (icon_of(it, sec) == "council" or str(it.get("tag") or "").lower() in ("politics", "council")) and \
        bool(ECC_RX.search(str(it.get("summary") or "")))

# Harlow College stories use the owner's photo of the college entrance (owner's rule, Nov 2026), ahead of stock, town
# and map art; road signs, police and fire photos still win, like County Hall. Same rule as the page's isHarlowCollegeStory.
HCOL_RX = re.compile(r"\bHarlow College\b")  # case-sensitive: "Harlow college" can mean another college in the town
HCOL_NOT_RX = re.compile(r"\bGibberd\b", re.I)

def is_harlow_college(it, sec):
    if sec in ("sport", "councilwatch") or is_police(it, sec) or is_fire(it, sec):
        return False
    h = host(it.get("url"))
    if h == "harlow-college.ac.uk" or h.endswith(".harlow-college.ac.uk"):
        return True
    t = " ".join(str(it.get(k) or "") for k in ("headline", "source", "org", "summary"))
    return bool(HCOL_RX.search(t) and not HCOL_NOT_RX.search(t))

# Fog stories use the owner's fog photo (owner's rule, Nov 2026) on story pages and share cards, ahead of road signs,
# weather cards, stock, town and map art; sport, police and fire stories keep their own. Same rule as the page's isFogStory.
FOG_RX = re.compile(r"\bfog(gy|s|bound)?\b|\bmist(y)?\b", re.I)
BRAIN_FOG_RX = re.compile(r"brain[- ]fog", re.I)
WX_BEFORE_FOG_RX = re.compile(r"\bflood(s|ing|ed)?\b|flood warning|flood alert|\bstorm|thunder|lightning|\bsnow|\bice\b|\bicy\b|frost|freez|gritt", re.I)

def is_fog(it, sec):
    if sec == "sport" or is_police(it, sec) or is_fire(it, sec):
        return False
    if str(it.get("wx") or "").lower() == "fog":
        return True
    head, summ = str(it.get("headline") or ""), str(it.get("summary") or "")
    if any(rx.search(head) for _, rx in ROAD_OG):
        return False  # fog on a named road (e.g. M25 lanes shut in fog) shows that road's sign (owner's rule)
    if FOG_RX.search(head) and not BRAIN_FOG_RX.search(head):
        return True
    weatherish = icon_of(it, sec) in ("weather", "environment") or str(it.get("tag") or "").lower() == "weather"
    pts = " ".join(str(x) for x in (it.get("points") or []))
    return weatherish and bool(FOG_RX.search(summ)) and not BRAIN_FOG_RX.search(summ) and \
        not WX_BEFORE_FOG_RX.search(" ".join([head, summ, pts]))

# Colchester Zoo stories use the owner's zoo photo when the story is positive or neutral, and the map (no photo) when it
# is bad news (owner's rule, Nov 2026). Checked before every other photo rule. Same rule as the page's isZooStory.
ZOO_RX = re.compile(r"\bColchester Zoo\b", re.I)
ZOO_WORD_RX = re.compile(r"\bzoo\b", re.I)
ZOO_BAD_RX = re.compile(r"\b(died|dies|die|death|deaths|dead|killed|kills?|put down|put to sleep|euthan\w*|escap\w*|attack\w*|bit(e|ten)|mauled|injur\w*|hurt|fire|blaze|closed|closes|closure|shut|fined|prosecut\w*|court|inquest|investigat\w*|critici[sz]\w*|condemn\w*|cruel\w*|neglect\w*|welfare concerns?|protest\w*|complain\w*|redundanc\w*|job cuts|loss(es)?|stolen|theft|tragic|tragedy|mourn\w*|sad news|grief|grieving|illness|disease|outbreak|bird flu|avian flu|crash\w*|collision|evacuat\w*|police|arrest\w*|warning)\b", re.I)

def is_zoo(it, sec):
    if sec == "sport":
        return False
    h = str(it.get("headline") or "")
    if ZOO_RX.search(h) or "colchester-zoo" in host(it.get("url")):
        return True
    return bool(ZOO_WORD_RX.search(h) and ZOO_RX.search(" ".join(str(it.get(k) or "") for k in ("summary", "source", "org", "place"))))

def zoo_bad(it):
    return bool(ZOO_BAD_RX.search(str(it.get("headline") or "") + " " + str(it.get("summary") or "")))

# London Stansted Airport stories rotate the owner's three airport photos when the story is positive or neutral, and
# show the map (no photo) when it is bad news (owner's rule, Nov 2026). Bad news is the zoo list plus airport trouble.
# A headline naming a signed road (M11 etc.) keeps the road rules. Same rule as the page's isStanstedStory.
STN_RX = re.compile(r"\bStansted\b(?!\s+Mountfitchet)", re.I)
AIRPORT_WORD_RX = re.compile(r"\b(airport|airports|flights?|terminal|runway|airline)\b", re.I)
STN_BAD_RX = re.compile(r"\b(delay(s|ed)?|cancel(l)?(ed|ations?)|chaos|disruption|disrupted|diverted|emergency landing|strikes?|walk-?outs?|stranded|outage|fault|security alert|bomb|suspicious|drones?|smuggl\w*|drugs|seized|jailed|charged|guilty|sentenced|noise complaints?|queues?)\b", re.I)
STN_PHOTOS = ["stansted-1", "stansted-2", "stansted-3"]

def is_stansted(it, sec):
    if sec == "sport":
        return False
    h = str(it.get("headline") or "")
    if any(rx.search(h) for _, rx in ROAD_OG):
        return False
    if STN_RX.search(h) or "stanstedairport" in host(it.get("url")):
        return True
    return bool(AIRPORT_WORD_RX.search(h) and STN_RX.search(" ".join(str(it.get(k) or "") for k in ("summary", "source", "org", "place"))))

def stansted_bad(it):
    t = str(it.get("headline") or "") + " " + str(it.get("summary") or "")
    return bool(ZOO_BAD_RX.search(t) or STN_BAD_RX.search(t))

def stansted_photo(it):
    h = 0
    for c in str(it.get("id") or ""):
        h = (h * 31 + ord(c)) & 0xFFFFFFFF
    return STN_PHOTOS[h % len(STN_PHOTOS)]

# West Mersea beach stories rotate the owner's three West Mersea photos (two of the pastel beach huts, one of the open
# beach), except when a death is involved (drowning, body found, fatal, tribute, inquest), when the story shows the map
# (owner's rule, 11 Nov 2026). A story counts when its headline names Mersea (not East Mersea) and a beach word, or
# its headline has a beach word and its place or summary names Mersea. A headline naming a signed road keeps the road
# rules. Same rule as the page's isMerseaStory.
MERSEA_RX = re.compile(r"\b(?<!east )mersea\b", re.I)
BEACH_RX = re.compile(r"\b(beach(es)?|beach ?huts?|seafront|sea front|foreshore|shoreline|bathing|bathers?|swim(s|mers?|ming)?|sea swim\w*|paddl\w*|promenade|seaside|lifeguards?|blue flag)\b", re.I)
MERSEA_DEATH_RX = re.compile(r"\b(died|dies|death|deaths|dead|drown\w*|bod(y|ies)|fatal\w*|killed|tributes?|inquest|passed away|lost (his|her|their) li(fe|ves)|funeral|remains)\b", re.I)
MERSEA_PHOTOS = ["mersea-1", "mersea-2", "mersea-3"]

def is_mersea(it, sec):
    if sec == "sport":
        return False
    h = str(it.get("headline") or "")
    if any(rx.search(h) for _, rx in ROAD_OG):
        return False
    if MERSEA_RX.search(h) and BEACH_RX.search(h):
        return True
    return bool(BEACH_RX.search(h) and MERSEA_RX.search(" ".join(str(it.get(k) or "") for k in ("place", "summary"))))

def mersea_bad(it):
    if icon_of(it, None) == "tribute" or str(it.get("tag") or "").lower() == "tribute":
        return True
    return bool(MERSEA_DEATH_RX.search(str(it.get("headline") or "") + " " + str(it.get("summary") or "")))

# Restaurant and food stories (restaurants, cafes, takeaways, pubs serving food, food festivals and markets, chefs)
# use the owner's plated meal photo when the story is positive or neutral, and the map (no photo) when it is bad news
# (owner's rule, Nov 2026). Colchester Zoo and Stansted stories keep their own photos, food banks and other food
# charity stories are not food stories, and a headline naming a signed road keeps the road rules.
# Same rule as the page's isFoodStory.
FOOD_RX = re.compile(r"\b(restaurants?|caf[e\u00e9]s?|bistros?|brasseries?|eater(y|ies)|diners?|takeaways?|take-aways?|steakhouses?|gastro ?pubs?|carver(y|ies)|tea ?rooms?|coffee shops?|pizzerias?|pizza|burgers?|curry houses?|fish and chips|fish & chips|chippy|chip shops?|bakery|bakeries|patisser(ie|ies)|deli|delis|delicatessens?|food (and|&) drink|food (festivals?|fairs?|markets?|halls?|courts?|vans?|trucks?|awards?|businesses|outlets?|stalls?)|street food|foodies?|dining|diners|chefs?|menus?|michelin|brunch|afternoon tea|beefeater|toby carvery|nando'?s|wetherspoons?|harvester|table table)\b", re.I)
FOOD_NOT_RX = re.compile(r"\bfood ?banks?\b|\bfood (poverty|parcels?|collections?|donations?|drives?|waste|insecurity|vouchers?|support|aid)\b|\bsoup kitchens?\b|\bpantr(y|ies)\b|\bschool (meals?|dinners?)\b|\bfree school meals?\b", re.I)
FOOD_BAD_RX = re.compile(r"\b(zero[- ]star|0[- ]star|one[- ]star|1[- ]star|hygiene rating of (0|1|zero|one)|poor hygiene|unhygienic|rats?|mice|rodents?|cockroach\w*|maggots?|mould\w*|infest\w*|poison\w*|sickness|sick|vomit\w*|e\.? ?coli|salmonella|listeria|norovirus|allerg\w*|anaphyla\w*|administration|administrators|bust|collaps\w*|clos(e|es|ed|ing|ure|ures)|shut\w*|axed|scrapped|struggl\w*|robb\w*|burglar\w*|break-?ins?|raid\w*|stabb\w*|assault\w*|fights?|brawl\w*|vandal\w*|smash\w*|charged|jailed|guilty|sentenced|banned|revoked|suspended|licence review|rows?|anger|angry|fury|furious|objections?|objectors?|refused|rejected|noise|flood\w*|explo\w*|damage\w*|warn\w*|fears?|concerns?|illegal\w*|exploit\w*|modern slavery|immigration (raid|offences?)|unpaid|owed|debts?|scam\w*|fraud\w*|blaze|fire|flames)\b", re.I)
FOOD_REOPEN_RX = re.compile(r"\bre-?open\w*|\bsaved\b|\brescued?\b|\bnew owners?\b|\btaken over\b|\btakeover\b|\bback in business\b", re.I)
FOOD_CLOSE_RX = re.compile(r"\bclos(e|es|ed|ing|ure|ures)\b|\bshut\w*", re.I)

def is_food(it, sec):
    if sec == "sport" or is_zoo(it, sec) or is_stansted(it, sec) or is_mersea(it, sec):
        return False
    h = str(it.get("headline") or "")
    if any(rx.search(h) for _, rx in ROAD_OG):
        return False
    return bool(FOOD_RX.search(h) and not FOOD_NOT_RX.search(h))

def food_bad(it):
    t = str(it.get("headline") or "") + " " + str(it.get("summary") or "")
    if FOOD_REOPEN_RX.search(t):
        t = FOOD_CLOSE_RX.sub(" ", t)  # "closed restaurant to reopen" is good news
    return bool(ZOO_BAD_RX.search(t) or FOOD_BAD_RX.search(t))

# Gas works stories (mains replacement, pipe repairs, gas network roadworks) use the owner's gas works photo
# (owner's rule, Nov 2026). Not explosions, fires, evacuations or casualties: those keep the normal rules.
# Same rule as the page's isGasWorkStory.
GAS_HEAD_RX = re.compile(r"\bgas\b|\bCadent\b|\bSGN\b", re.I)
GAS_WORK_RX = re.compile(r"\bgas (mains?|pipes?|pipelines?|network|works?|engineers?|supply|leaks?|upgrades?|repairs?)\b|\bCadent\b|\bSGN\b|\b(mains|pipe|pipeline) (replacement|work|works|upgrade|repair)", re.I)
GAS_BAD_RX = re.compile(r"\b(explo\w*|blast|fire|blaze|flames|evacuat\w*|killed|died|dies|death|dead|injur\w*|hospital|arrest\w*|court|charged|carbon monoxide)\b", re.I)

def is_gaswork(it, sec):
    if sec == "sport":
        return False
    h = str(it.get("headline") or "")
    t = h + " " + str(it.get("summary") or "")
    return bool(GAS_HEAD_RX.search(h) and GAS_WORK_RX.search(t) and not GAS_BAD_RX.search(t))

# Data centre stories (plans, objections, petitions, approvals) use the owner's data centre photo (owner's rule,
# Nov 2026), ahead of County Hall, road signs, stock, town and map art. Fires, explosions, deaths, injuries and
# court cases keep the normal rules. Same rule as the page's isDataCentreStory.
DC_RX = re.compile(r"\bdata[- ]?cent(re|er)s?\b|\bhyperscale\b|\bserver farms?\b", re.I)
DC_BAD_RX = re.compile(r"\b(explo\w*|blast|fire|blaze|flames|evacuat\w*|killed|died|dies|death|dead|injur\w*|arrest\w*|court|charged|jailed|sentenced)\b", re.I)

def is_datacentre(it, sec):
    if sec == "sport":
        return False
    h = str(it.get("headline") or "")
    return bool(DC_RX.search(h) and not DC_BAD_RX.search(h + " " + str(it.get("summary") or "")))

# c2c stories use the owner's chosen photo of c2c train 357 040 at Ripple Lane (owner's rule, Nov 2026): kitmasterbloke,
# CC BY 4.0, via Wikimedia Commons, so it is always credited. A story is a c2c story when its headline or org names c2c.
# Derailments and very serious injuries (deaths, hit by a train, serious or critical injuries, crashes) do not use it:
# they show the Breaking News picture when major breaking, otherwise the map. A story about services resuming or
# reopening after a derailment is a service story and keeps the photo. Same rule as the page's isC2cStory/isC2cBad.
C2C_RX = re.compile(r"\bc2c\b", re.I)
C2C_BAD_RX = re.compile(r"\b(derail\w*|killed|died|dies|death|dead|fatal\w*|seriously (hurt|injured)|serious(ly)? injur\w*|critical\w*|life[- ](threatening|changing)|hit by (a |the )?train|struck by (a |the )?train|(train|rail) (crash|collision)|collided)\b", re.I)
C2C_OK_RX = re.compile(r"\b(resum\w*|reopen\w*|re-open\w*|back|again|restored|return\w*|repairs?)\b", re.I)
C2C_CREDIT = {"by": "kitmasterbloke", "license": "CC BY 4.0", "licenseUrl": "https://creativecommons.org/licenses/by/4.0/",
              "source": "https://commons.wikimedia.org/wiki/File:357_040_Ripple_Lane_151025.jpg"}

def is_c2c(it, sec):
    if sec == "sport":
        return False
    return bool(C2C_RX.search(str(it.get("headline") or "")) or C2C_RX.search(str(it.get("org") or "")))

def c2c_bad(it):
    h = str(it.get("headline") or "")
    t = h + " " + str(it.get("summary") or "")
    if not C2C_BAD_RX.search(t):
        return False
    # follow-ups about services coming back after a derailment keep the photo, unless someone was hurt or killed
    hurt = re.search(r"\b(killed|died|dies|death|dead|fatal\w*|injur\w*|hurt|critical\w*|life[- ](threatening|changing)|hit by|struck by)\b", t, re.I)
    return bool(hurt) or not C2C_OK_RX.search(h)

# Bus stories (fares, routes, timetables, services, bus stations and stops, bus lanes, park and ride) use the owner's
# photo of the inside of a bus (owner's rule, 11 Nov 2026), ahead of fog, stock, County Hall, town and map art. c2c
# and Remembrance stories keep their own photos and a headline naming a signed road keeps the sign. Crashes and
# collisions never use it (owner's rule): they keep the police photo, as do deaths, injuries, police incidents,
# fires and court cases. Same rule as the page's isBusStory.
BUS_RX = re.compile(r"\bbus(es|ses)?\b|\bpark (and|&) ride\b|\bFirst (Essex|Bus)\b|\bEnsign ?bus\b", re.I)
BUS_BAD_RX = re.compile(r"\b(crash\w*|collision\w*|collided|accidents?|smash\w*|overturn\w*|hit by|struck|ran over|run over|killed|died|dies|death|dead|fatal\w*|injur\w*|hurt|seriously|critical\w*|stabb?\w*|assault\w*|attack\w*|arrest\w*|charged|jailed|sentenced|court|police|fire|blaze|flames|explo\w*|evacuat\w*)\b", re.I)

def is_bus(it, sec):
    if sec == "sport" or is_c2c(it, sec) or is_remembrance(it, sec):
        return False
    h = str(it.get("headline") or "")
    if any(rx.search(h) for _, rx in ROAD_OG):
        return False
    return bool(BUS_RX.search(h) and not BUS_BAD_RX.search(h + " " + str(it.get("summary") or "")))

# Swimming pool stories (pools, swimming baths and lidos: closures, reopenings, funding, refits, opening hours) use the
# owner's photo of an indoor pool (owner's rule, 11 Nov 2026), ahead of fog, stock, County Hall, town and map art.
# Sport stories keep the sport photos and a headline naming a signed road keeps the sign. Drownings, deaths, injuries,
# police, abuse, court cases, fires and chemical leaks keep the normal rules. Same rule as the page's isPoolStory.
POOL_RX = re.compile(r"\bswimming (pools?|baths?)\b|\blidos?\b|\b(leisure|school|public|council|indoor|outdoor|learner|teaching|training|community|hydrotherapy|main) pools?\b|\bpools?\b.{0,40}\bswim\w*|\bswim\w*\b.{0,40}\bpools?\b", re.I)
POOL_BAD_RX = re.compile(r"\b(drown\w*|crash\w*|collision\w*|killed|died|dies|death|dead|fatal\w*|injur\w*|hurt|seriously|critical\w*|stabb?\w*|assault\w*|attack\w*|abuse\w*|voyeur\w*|indecent|sexual\w*|arrest\w*|charged|jailed|sentenced|court|police|fire|blaze|flames|explo\w*|evacuat\w*|chemical|chlorine (leak|gas)|gas leak)\b", re.I)

def is_pool(it, sec):
    if sec == "sport" or is_remembrance(it, sec):
        return False
    h = str(it.get("headline") or "")
    if any(rx.search(h) for _, rx in ROAD_OG):
        return False
    return bool(POOL_RX.search(h) and not POOL_BAD_RX.search(h + " " + str(it.get("summary") or "")))

# Homeless stories (homelessness, rough sleeping, night and winter shelters, SWEP) use the owner's photo of a man sitting
# on a pavement, seen from behind (owner's rule, 11 Nov 2026), ahead of fog, stock, County Hall, town and map art. Sport
# stories keep the sport photos and a headline naming a signed road keeps the sign. Deaths, injuries, police, abuse,
# court cases and fires keep the normal rules. Same rule as the page's isHomelessStory.
HOMELESS_RX = re.compile(r"\bhomeless\w*\b|\brough[- ]sleep\w*\b|\bsleep\w* rough\b|\b(night|winter|homeless|emergency) shelters?\b|\bSWEP\b", re.I)
# Not for homeless families, temporary housing or council budget stories (owner's rule, 11 Nov 2026): rough sleeping and shelters only.
HOMELESS_HOUSING_RX = re.compile(r"\b(famil(y|ies)|children|kids|temporary (housing|accommodation)|B&Bs?|bed and breakfasts?|overspend\w*|budgets?|deficits?|council tax|housing (costs?|bill|pressures?|waiting list))\b", re.I)
HOMELESS_BAD_RX = re.compile(r"\b(drown\w*|crash\w*|collision\w*|killed|died|dies|death|dead|body|fatal\w*|injur\w*|hurt|seriously|critical\w*|stabb?\w*|assault\w*|attack\w*|abuse\w*|indecent|sexual\w*|rape\w*|murder\w*|arrest\w*|charged|jailed|sentenced|court|police|fire|blaze|flames|explo\w*|evacuat\w*)\b", re.I)

def is_homeless(it, sec):
    if sec == "sport" or is_remembrance(it, sec):
        return False
    h = str(it.get("headline") or "")
    if any(rx.search(h) for _, rx in ROAD_OG):
        return False
    return bool(HOMELESS_RX.search(h) and not HOMELESS_HOUSING_RX.search(h) and not HOMELESS_BAD_RX.search(h + " " + str(it.get("summary") or "")))

# Remembrance stories use the owner's poppy wreath photo (owner's rule, Nov 2026). Same test as the page's
# seasonKindOf(s) === "remembrance": not sport, police, court, crime, appeal, fire, ambulance or tribute stories.
REM_RX = re.compile(r"remembrance|armistice|\bpoppy|\bpoppies|cenotaph|war memorial|two[- ]minute silence|royal british legion", re.I)
REM_SKIP_RX = re.compile(r"\b(arrest|charged|jailed|died|death|dead|killed|crash|stabb|assault|injur|attack|investigation)", re.I)

def is_remembrance(it, sec):
    if sec == "sport":
        return False
    if str(it.get("season") or "").lower() == "remembrance":
        return True
    ic, tag = icon_of(it, sec), str(it.get("tag") or "")
    if ic in {"police", "crime", "court", "appeal", "fire", "ambulance", "tribute"} or re.search(r"police|court|crime|appeal|tribute|fire|ambulance", tag, re.I):
        return False
    h = str(it.get("headline") or "")
    return bool(REM_RX.search(h) and not REM_SKIP_RX.search(h))

# Christmas stories with no specific photo use the owner's baubles photo (owner's rule, Nov 2026). Same test as the
# page's seasonKindOf(s) === "christmas" (the earlier occasions win, and the same story types are skipped); every
# specific photo rule, a stock photo and the Breaking News picture win. Same rule as the page's isChristmasStory.
XMAS_PHOTOS = ["christmas", "christmas-2"]  # baubles and the lit tree (owner's photos), chosen by story id like the page
XMAS_RX = re.compile(r"christmas|festive|santa|carol service|\bcarols\b|nativity|\badvent\b|lights switch[- ]on", re.I)
XMAS_BEFORE_RX = re.compile(r"new year'?s? eve|new year celebrations|new year fireworks|hogmanay|new year'?s? day|bonfire|firework|guy fawkes|hallowe'?en|trick[- ]or[- ]treat|pumpkin", re.I)

def is_christmas(it, sec):
    if sec == "sport":
        return False
    season = str(it.get("season") or "").lower()
    if season:
        return season == "christmas"
    ic, tag = icon_of(it, sec), str(it.get("tag") or "")
    if ic in {"police", "crime", "court", "appeal", "fire", "ambulance", "tribute"} or re.search(r"police|court|crime|appeal|tribute|fire|ambulance", tag, re.I):
        return False
    h = str(it.get("headline") or "")
    if REM_SKIP_RX.search(h) or REM_RX.search(h) or XMAS_BEFORE_RX.search(h):
        return False
    return bool(XMAS_RX.search(h))

# Major breaking news with no suitable photo shows the owner's Breaking News picture (owner's rule, Nov 2026):
# img/topics/breaking.png on the page, img/og/breaking.png as the share card. Only a news story flagged breaking
# with weight 9 or 10; every specific photo rule above it, and a stock photo, still win. Same rule as the page's
# isBreakingArtStory.
def is_major_breaking(it, sec):
    if sec != "news":
        return False
    try:
        w = float(it.get("weight") or 0)
    except (TypeError, ValueError):
        w = 0
    return it.get("breaking") is True and w >= 9

def card_of(it, sec):
    if it.get("showMap") is True:  # owner's choice: map only, no photo (same rule as the page's isOwnerMap)
        return CARD_FOR.get(icon_of(it, sec), "news")
    if is_zoo(it, sec):
        if not zoo_bad(it) and os.path.exists(os.path.join(ROOT, "img", "og", "zoo.jpg")):
            return "zoo"
        return CARD_FOR.get(icon_of(it, sec), "news")
    if is_stansted(it, sec):
        if not stansted_bad(it) and os.path.exists(os.path.join(ROOT, "img", "og", stansted_photo(it) + ".jpg")):
            return stansted_photo(it)
        return CARD_FOR.get(icon_of(it, sec), "news")
    if is_mersea(it, sec):
        if not mersea_bad(it) and os.path.exists(os.path.join(ROOT, "img", "og", id_pick(it, MERSEA_PHOTOS) + ".jpg")):
            return id_pick(it, MERSEA_PHOTOS)
        return CARD_FOR.get(icon_of(it, sec), "news")
    if is_food(it, sec):
        if not food_bad(it) and os.path.exists(os.path.join(ROOT, "img", "og", "food.jpg")):
            return "food"
        return CARD_FOR.get(icon_of(it, sec), "news")
    if is_gaswork(it, sec) and os.path.exists(os.path.join(ROOT, "img", "og", "gaswork.jpg")):
        return "gaswork"
    if is_datacentre(it, sec) and os.path.exists(os.path.join(ROOT, "img", "og", "datacentre.jpg")):
        return "datacentre"
    if is_remembrance(it, sec) and os.path.exists(os.path.join(ROOT, "img", "og", "remembrance.jpg")):
        return "remembrance"
    if is_c2c(it, sec):
        if not c2c_bad(it) and os.path.exists(os.path.join(ROOT, "img", "og", "c2c.jpg")):
            return "c2c"
        if is_major_breaking(it, sec) and os.path.exists(os.path.join(ROOT, "img", "og", "breaking.png")):
            return "breaking"
        return CARD_FOR.get(icon_of(it, sec), "news")
    if is_bus(it, sec) and os.path.exists(os.path.join(ROOT, "img", "og", "bus.jpg")):
        return "bus"
    if is_pool(it, sec) and os.path.exists(os.path.join(ROOT, "img", "og", "pool.jpg")):
        return "pool"
    if is_homeless(it, sec) and os.path.exists(os.path.join(ROOT, "img", "og", "homeless.jpg")):
        return "homeless"
    if is_fog(it, sec) and os.path.exists(os.path.join(ROOT, "img", "og", "fog.jpg")):
        return "fog"
    road = road_of(it)
    if sec != "sport" and road and os.path.exists(os.path.join(ROOT, "img", "og", road + ".png")):
        return road
    if is_ambulance(it, sec) and os.path.exists(os.path.join(ROOT, "img", "og", "ambulance.jpg")):
        return "ambulance"
    if is_tiptree(it, sec) and os.path.exists(os.path.join(ROOT, "img", "og", id_pick(it, TIPTREE_PHOTOS) + ".jpg")):
        return id_pick(it, TIPTREE_PHOTOS)
    if is_statefayre(it, sec) and os.path.exists(os.path.join(ROOT, "img", "og", "statefayre.jpg")):
        return "statefayre"
    if is_harlow_college(it, sec) and os.path.exists(os.path.join(ROOT, "img", "og", "harlowcollege.jpg")):
        return "harlowcollege"
    if is_county_hall(it, sec) and os.path.exists(os.path.join(ROOT, "img", "og", "countyhall.jpg")):
        return "countyhall"
    if is_hospital(it, sec) and os.path.exists(os.path.join(ROOT, "img", "og", "hospital.jpg")):
        return "hospital"
    if is_police(it, sec) and os.path.exists(os.path.join(ROOT, "img", "og", police_photo(it) + ".jpg")):
        return police_photo(it)
    if is_fire(it, sec) and os.path.exists(os.path.join(ROOT, "img", "og", "fireengine.jpg")):
        return "fireengine"
    if is_major_breaking(it, sec) and not (PHOTOS.get(it.get("id")) and not it.get("noPhoto")) \
            and os.path.exists(os.path.join(ROOT, "img", "og", "breaking.png")):
        return "breaking"
    if is_christmas(it, sec) and not (PHOTOS.get(it.get("id")) and not it.get("noPhoto")) \
            and os.path.exists(os.path.join(ROOT, "img", "og", id_pick(it, XMAS_PHOTOS) + ".jpg")):
        return id_pick(it, XMAS_PHOTOS)
    if sec == "councilwatch":
        return "council"
    if sec == "features":
        return "feature"
    return CARD_FOR.get(icon_of(it, sec), "news")

def parse_t(s):
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None

def iso(d):
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if d else ""

def uk_long(d):
    if not d:
        return ""
    u = d.astimezone(UK)
    return f"{u.strftime('%A')} {u.day} {u.strftime('%B %Y')}, {u.strftime('%H:%M')}"

def uk_day(d):
    u = d.astimezone(UK)
    return f"{u.strftime('%A')} {u.day} {u.strftime('%B')}"

def host(u):
    try:
        h = urlparse(u).netloc.lower()
        return h[4:] if h.startswith("www.") else h
    except Exception:
        return ""

def safe_url(u):
    u = str(u or "")
    return u if re.match(r"^https?://", u, re.I) else ""

def slug_ok(i):
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,120}", str(i or "")))

def trunc(s, n):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"

def write(path, text):
    full = os.path.join(ROOT, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    old = open(full, encoding="utf-8").read() if os.path.exists(full) else None
    if old != text:
        with open(full, "w", encoding="utf-8") as f:
            f.write(text)
        return True
    return False

# ---------- shared page chrome ----------
SHIELD = '<img class="shield" src="/favicon.svg" width="40" height="47" alt="">'

def analytics():
    code = CFG.get("goatcounter") or ""
    if not code:
        return ""
    return f'<script data-goatcounter="https://{E(code)}.goatcounter.com/count" async src="//gc.zgo.at/count.js"></script>'

def head(title, desc, canonical, og_image, og_type="website", extra=""):
    return f"""<!DOCTYPE html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(title)}</title>
<meta name="description" content="{E(desc)}">
<link rel="canonical" href="{E(canonical)}">
<meta property="og:site_name" content="The Seax">
<meta property="og:locale" content="en_GB">
<meta property="og:type" content="{og_type}">
<meta property="og:title" content="{E(title.replace(' · The Seax', ''))}">
<meta property="og:description" content="{E(desc)}">
<meta property="og:url" content="{E(canonical)}">
<meta property="og:image" content="{SITE}{og_image if og_image.startswith("/") else og_path(og_image)}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="The Seax, Essex News, Sport, Life.">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{E(title.replace(' · The Seax', ''))}">
<meta name="twitter:description" content="{E(desc)}">
<meta name="twitter:image" content="{SITE}{og_image if og_image.startswith("/") else og_path(og_image)}">
<meta name="theme-color" content="#c8102e">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/icons/apple-touch-icon.png">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="alternate" type="application/rss+xml" title="The Seax: latest Essex news" href="/feed.xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Schibsted+Grotesk:wght@500..900&family=Inter:opsz,wght@14..32,400..700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/assets/page.css">
{extra}{analytics()}
</head>
<body>
<header class="mast"><div class="wrap">
  <a class="brand" href="/" aria-label="The Seax front page">{SHIELD}<span><b>The <em>Seax</em></b><small>Essex News, Sport, Life.</small></span></a>
  <a class="home" href="/">Front page</a>
</div></header>
<nav class="sec"><div class="wrap">
  <a href="/#news">News</a><a href="/#sport">Sport</a><a href="/#desk">Public Services</a><a href="/council-watch/">Council Watch</a><a href="/#community">Community</a><a href="/#whatson">What's On</a><a href="/briefing/">Morning briefing</a><a href="/about/">About</a>
</div></nav>
"""

def newsletter_box():
    form = CFG.get("newsletterForm") or ""
    link = CFG.get("newsletterLink") or ""
    if link and not form:
        return f"""<section class="nl"><div><h3>{E(CFG.get('newsletterName','Essex at 7'))}</h3><p>The morning briefing: the lead, the stories that matter, weather, travel and last night's results, free in your inbox every morning.</p></div>
<div class="nl-go"><a href="{E(link)}" target="_blank" rel="noopener">Get it free by email</a></div></section>"""
    if not form:
        return ""
    field = CFG.get("newsletterField") or "email"
    return f"""<section class="nl"><div><h3>{E(CFG.get('newsletterName','Essex at 7'))}</h3><p>The morning briefing: the lead, the stories that matter, weather, travel and last night's results, in your inbox before 7.</p></div>
<form action="{E(form)}" method="post" target="_blank"><label class="sr" for="nlE">Email address</label><input id="nlE" type="email" name="{E(field)}" placeholder="Your email address" required><button>Sign me up</button></form></section>"""

def foot():
    mail = CFG["contactEmail"]
    social = []
    if CFG.get("whatsappChannel"):
        social.append(f'<a href="{E(CFG["whatsappChannel"])}">WhatsApp channel</a>')
    if CFG.get("facebookPage"):
        social.append(f'<a href="{E(CFG["facebookPage"])}">Facebook</a>')
    local = " · ".join(f'<a href="/news/{sl}/">{E(nm)}</a>' for _k, sl, nm, *_ in AREA_PAGES)
    return f"""<footer class="foot"><div class="wrap">
  <p class="area-links"><b>Local news:</b> <a href="/news/">All Essex</a> · {local}</p>
  <p><b>The Seax</b> brings together Essex news, sport and life from trusted local and national sources. Every story links to the original reporting.</p>
  <p><a href="/about/">About The Seax</a> · <a href="/about/#corrections">Corrections</a> · <a href="mailto:{E(mail)}">{E(mail)}</a> · <a href="/briefing/">Morning briefing</a> · <a href="/feed.xml">RSS</a>{' · ' + ' · '.join(social) if social else ''}</p>
</div></footer>
"""

SHARE_JS = """<script>
document.addEventListener("click",function(e){
  var b=e.target.closest("[data-share]"); if(!b) return;
  var url=b.getAttribute("data-url"), title=b.getAttribute("data-title");
  if(b.dataset.share==="native"){ if(navigator.share){ navigator.share({title:title,url:url}).catch(function(){}); e.preventDefault(); } }
  else if(b.dataset.share==="copy"){ e.preventDefault(); try{ navigator.clipboard.writeText(url).then(function(){ b.textContent="Link copied"; setTimeout(function(){ b.textContent="Copy link"; },2500); }); }catch(_){ b.textContent=url; } }
});
if(!navigator.share){ var n=document.querySelector('[data-share="native"]'); if(n) n.style.display="none"; }
</script>"""

def share_bar(url, title):
    t = quote(title + " " + url)
    return f"""<div class="share">
  <button data-share="native" data-url="{E(url)}" data-title="{E(title)}">Share</button>
  <a class="wa" href="https://wa.me/?text={t}" target="_blank" rel="noopener">WhatsApp</a>
  <a href="https://www.facebook.com/sharer/sharer.php?u={quote(url, safe='')}" target="_blank" rel="noopener">Facebook</a>
  <a href="https://x.com/intent/post?url={quote(url, safe='')}&amp;text={quote(title)}" target="_blank" rel="noopener">X</a>
  <button data-share="copy" data-url="{E(url)}" data-title="{E(title)}">Copy link</button>
</div>"""

# ---------- stock photos (tools/photos.py) ----------
try:
    PHOTOS = json.load(open(os.path.join(ROOT, "data", "photos.json"), encoding="utf-8"))
except Exception:
    PHOTOS = {}

# Owner-supplied file photos of people named in a headline (data/portraits.json; owner's choice, Nov 2026). They
# override every other picture on the card, story page and share card, with the photographer's credit and licence.
try:
    PORTRAITS = json.load(open(os.path.join(ROOT, "data", "portraits.json"), encoding="utf-8"))
except Exception:
    PORTRAITS = []

def portrait_of(it):
    h = str(it.get("headline") or "")
    for p in PORTRAITS:
        try:
            if re.search(p["match"], h):
                return p
        except Exception:
            pass
    return None

def portrait_figure(p):
    lic = f'<a href="{E(p["licenseUrl"])}" target="_blank" rel="noopener license">{E(p["license"])}</a>' if safe_url(p.get("licenseUrl")) else E(p.get("license"))
    src = f' via <a href="{E(p["source"])}" target="_blank" rel="noopener">{E(p.get("provider") or "source")}</a>' if safe_url(p.get("source")) else ""
    return (f'<figure class="stock"><img src="{E(p["wide"])}?v=1" width="1200" height="655" alt="File photo of {E(p["name"])}" loading="eager">'
            f'<figcaption><b>{E(p["name"])}</b>. File photo. Photo: {E(p["creator"])}{src}, {lic}, set on a blurred background.</figcaption></figure>')

def stock_figure(it, sec):
    p = PHOTOS.get(it.get("id")) if sec != "sport" and not it.get("noPhoto") else None
    if not p:
        return ""
    who = f'<a href="{E(p["creatorUrl"])}" target="_blank" rel="noopener">{E(p["creator"])}</a>' if safe_url(p.get("creatorUrl")) else E(p.get("creator"))
    lic = f'<a href="{E(p["licenseUrl"])}" target="_blank" rel="noopener">{E(p["license"])}</a>' if safe_url(p.get("licenseUrl")) else E(p.get("license"))
    src = f' via <a href="{E(p["source"])}" target="_blank" rel="noopener">{E(p.get("provider") or "source")}</a>' if safe_url(p.get("source")) else ""
    if p.get("kind") == "commons":  # Wikimedia Commons file photo of the story's own subject (owner's rule, Nov 2026)
        return (f'<figure class="stock"><img src="{E(p["file"])}" width="{E(p.get("w") or 1200)}" height="{E(p.get("h") or 800)}" alt="{E("File photo: " + (p.get("title") or p.get("keyword") or ""))}" loading="eager">'
                f'<figcaption><b>File photo</b>{": " + E(p.get("title")) if p.get("title") else ""}. Photo: {who}, {lic}{src}</figcaption></figure>')
    return (f'<figure class="stock"><img src="{E(p["file"])}" width="{E(p.get("w") or 1200)}" height="{E(p.get("h") or 800)}" alt="{E("Stock photo: " + (p.get("title") or p.get("keyword") or ""))}" loading="eager">'
            f'<figcaption><b>Stock photo</b>, not the scene of this story. {E(p.get("title") or "")}{" · " if p.get("title") else ""}{who}, {lic}{src}</figcaption></figure>')


# ---------- town and sport photos on story pages (owner's rule, 11 Nov 2026) ----------
# Every story page shows the picture its front-page card shows, so social media share cards carry it too. When no
# specific photo rule above applies, the page uses the same town photograph (img/places) or sport photograph
# (img/sport) as the front page, with a 1200x630 share crop in img/og/place-<key>.jpg or img/og/sport-<file>.jpg.
# Same rules as the page's townKeyOf, sportKindOf and sportPhotoSrc. Stories the front page draws as a map or as
# artwork (courts, police, weather, bonfire and other drawn occasions) keep their branded share card.
TOWN_PHOTO_SKIP = {"police", "crime", "court", "appeal", "tribute", "fire", "ambulance"}
TOWN_ALIAS = [(re.compile(r), k) for r, k in [
    (r"^(chelmsford|moulsham|great baddow|broomfield|springfield|writtle|galleywood)$", "chelmsford"),
    (r"^(colchester|stanway|lexden|highwoods)$", "colchester"),
    (r"^(southend(-on-sea)?|westcliff(-on-sea)?|southchurch|prittlewell|thorpe bay)$", "southend"),
    (r"^(leigh(-on-sea)?|old leigh)$", "leigh"), (r"^shoebury(ness)?$", "shoebury"),
    (r"^(basildon|laindon|vange)$", "basildon"), (r"^billericay$", "billericay"), (r"^wickford$", "wickford"),
    (r"^(brentwood|shenfield|hutton)$", "brentwood"), (r"^(grays|chafford hundred|thurrock|west thurrock)$", "grays"),
    (r"^(tilbury|west tilbury|east tilbury)$", "tilbury"), (r"^purfleet(-on-thames)?$", "purfleet"),
    (r"^(stanford[- ]le[- ]hope|corringham)$", "stanford"), (r"^(harlow|old harlow)$", "harlow"), (r"^epping$", "epping"),
    (r"^(loughton|debden)$", "loughton"), (r"^chigwell$", "chigwell"), (r"^waltham abbey$", "walthamabbey"),
    (r"^saffron walden$", "saffronwalden"), (r"^(great )?dunmow$", "dunmow"), (r"^stansted mountfitchet$", "stansted"),
    (r"^braintree$", "braintree"), (r"^witham$", "witham"), (r"^halstead$", "halstead"), (r"^coggeshall$", "coggeshall"),
    (r"^(maldon|heybridge)$", "maldon"), (r"^burnham([- ]on[- ]crouch)?$", "burnham"), (r"^south woodham ferrers$", "swf"),
    (r"^rayleigh$", "rayleigh"), (r"^rochford$", "rochford"), (r"^canvey( island)?$", "canvey"), (r"^(south )?benfleet$", "benfleet"),
    (r"^clacton(-on-sea)?$", "clacton"), (r"^frinton(-on-sea)?$", "frinton"), (r"^walton(-on-the-naze)?$", "walton"),
    (r"^(harwich|dovercourt)$", "harwich"), (r"^brightlingsea$", "brightlingsea"), (r"^((west|east) )?mersea( island)?$", "mersea")]]
DRAWN_SEASON_RX = re.compile(r"new year'?s? eve|new year celebrations|new year fireworks|hogmanay|new year'?s? day|bonfire|firework|guy fawkes|hallowe'?en|trick[- ]or[- ]treat|pumpkin|\beaster\b", re.I)
SPORT_PHOTO_FILES = {"football": ["football", "football-2", "football-3", "football-4"], "cricket": ["cricket"], "tennis": ["tennis"],
                     "rugby": ["rugby"], "cycling": ["cycling"], "icehockey": ["icehockey"], "golf": ["golf"], "racing": ["racing"], "boxing": ["boxing"]}
SPORT_NAME = {"football": "Football", "cricket": "Cricket", "tennis": "Tennis", "rugby": "Rugby", "cycling": "Cycling",
              "icehockey": "Ice hockey", "golf": "Golf", "racing": "Racing", "boxing": "Boxing"}
SPORT_PICK = {}
try:
    TOWN_CREDITS = json.load(open(os.path.join(ROOT, "img", "places", "credits.json"), encoding="utf-8"))
except Exception:
    TOWN_CREDITS = {}

def jpeg_size(path, default=(1200, 800)):
    """Width and height of a JPEG from its SOF marker (standard library only)."""
    try:
        with open(path, "rb") as f:
            d = f.read(200000)
        i = 2
        while i < len(d) - 9:
            if d[i] != 0xFF:
                i += 1; continue
            m = d[i + 1]
            if m in (0xC0, 0xC1, 0xC2):
                return (d[i + 7] << 8 | d[i + 8], d[i + 5] << 8 | d[i + 6])
            i += 2 + (d[i + 2] << 8 | d[i + 3])
    except Exception:
        pass
    return default

def sport_kind(it, sec):
    sa = str(it.get("sportArt") or "").lower()
    if sa in SPORT_PHOTO_FILES or sa == "athletics":
        return sa
    k = str(it.get("icon") or "").lower() or icon_of(it, sec)
    tag = str(it.get("tag") or "").lower()
    if not (k in ("football", "racing", "cricket", "sport") or re.match(r"^(football|racing|cricket|ice hockey|rugby|sport|athletics|cycling|tennis|golf|boxing)$", tag)):
        return None
    t = f" {tag} {str(it.get('headline') or '').lower()} {str(it.get('summary') or '').lower()} "
    if k == "cricket" or re.search(r"cricket|county championship|\bt20\b|\bwicket|\binnings\b", t): return "cricket"
    if k == "racing" or re.search(r"\bracing\b|racecourse|race ?day|jockey|\btrainer\b|\bhorses?\b|\bfurlong", t): return "racing"
    if re.search(r"ice hockey|chieftains|\bnihl\b", t): return "icehockey"
    if re.search(r"\brugby\b", t): return "rugby"
    if re.search(r"\btennis\b|wimbledon|\bwta\b|\batp\b", t): return "tennis"
    if re.search(r"\bgolf", t): return "golf"
    if re.search(r"\bboxing\b|\bboxers?\b|\bbout\b|heavyweight|middleweight|welterweight|title fight", t): return "boxing"
    if re.search(r"cycling|cyclist|\bgiro\b|tour de france|velodrome|\bbike race", t): return "cycling"
    if k == "football" or re.search(r"football|\bfc\b|\bleague\b|\bunited\b|\bgoal", t): return "football"
    return "athletics"

def js_hash(sid):
    h = 0
    for c in str(sid):
        h = (h * 31 + ord(c)) & 0xFFFFFFFF
    return h

def _load_clubs():
    """The page's CLUBS list (name and match pattern), read from index.html so the two never drift apart."""
    try:
        page = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
        i = page.index("const CLUBS = {"); j = page.index("};", i)
        return [(n, re.compile(rx)) for n, rx in re.findall(r'^\s*"([^"]+)":\s*\{re:/(.*?)/[a-z]*,', page[i:j], re.M)]
    except Exception:
        return []
CLUBS = _load_clubs()
CLUB_NAMES = {n for n, _ in CLUBS}
CLUB_CARDS = set()

def club_of(it, sec):
    if it.get("club") in CLUB_NAMES:
        return it["club"]
    k = str(it.get("icon") or "").lower() or icon_of(it, sec)
    if not (k == "football" or re.search(r"football|ice hockey", str(it.get("tag") or ""), re.I)):
        return None
    for field in (it.get("headline"), it.get("summary")):
        t = str(field or "").lower()
        best, at = None, 10 ** 9
        for name, rx in CLUBS:
            m = rx.search(t)
            if m and m.start() < at:
                best, at = name, m.start()
        if best:
            return best
    return None

def pick_sport(ed):
    """Rotate the football photos like the page: newest first, never the same photo twice in a row."""
    SPORT_PICK.clear()
    def tm(x):
        return max((parse_t(x.get("updated")) or datetime.min.replace(tzinfo=timezone.utc)), (parse_t(x.get("time")) or datetime.min.replace(tzinfo=timezone.utc)))
    lst = [("sport", x) for x in (ed.get("sport") or {}).get("stories", []) or [] if isinstance(x, dict) and x.get("id")] + \
          [("news", x) for x in ed.get("stories", []) or [] if isinstance(x, dict) and x.get("id")]
    CLUB_CARDS.clear()
    clubbed = sorted([x for sec, x in lst if sec == "sport" and club_of(x, sec)], key=tm, reverse=True)
    CLUB_CARDS.update(x["id"] for n, x in enumerate(clubbed) if n % 2 == 1)  # every other club story shows club colours
    lst = [p for p in lst if p[1]["id"] not in CLUB_CARDS]
    prev = {}
    for sec, x in sorted(lst, key=lambda p: tm(p[1]), reverse=True):
        k = sport_kind(x, sec)
        files = SPORT_PHOTO_FILES.get(k) or []
        if len(files) < 2:
            continue
        v = js_hash(x["id"]) % len(files)
        if v == prev.get(k):
            v = (v + 1) % len(files)
        SPORT_PICK[x["id"]] = v
        prev[k] = v

def town_key(it, sec):
    if sec == "sport" or icon_of(it, sec) in TOWN_PHOTO_SKIP or str(it.get("icon") or "").lower() in TOWN_PHOTO_SKIP:
        return None
    parts = [re.sub(r"\s+(town centre|district)$", "", x).strip() for x in re.split(r"\s*(?:,|&|/|\band\b)\s*", str(it.get("place") or "").lower())]
    parts = [x for x in parts if x]
    keys = []
    for x in parts:
        for rx, k in TOWN_ALIAS:
            if rx.search(x):
                if k not in keys:
                    keys.append(k)
                break
    first = next((k for rx, k in TOWN_ALIAS if parts and rx.search(parts[0])), None)
    return first if first and len(keys) <= 2 and first in TOWN_CREDITS else None

def fallback_photo(it, sec, card):
    """(figure html, share image path) for a story with no specific photo, or ("", "") to keep the branded card."""
    if card == "hospital":
        return ('<figure class="stock"><img src="/img/topics/hospital.jpg?v=1" width="1200" height="655" alt="Library photo: a hospital" loading="eager">'
                '<figcaption><b>Hospital</b>. Library image, not the scene of this story.</figcaption></figure>', "/img/og/hospital.jpg")
    if card not in set(CARD_FOR.values()) | {"news", "feature", "default"} or it.get("showMap") is True:
        return "", ""
    k = sport_kind(it, sec)
    if k in SPORT_PHOTO_FILES:
        files = SPORT_PHOTO_FILES[k]
        f = files[SPORT_PICK.get(it.get("id"), 0) % len(files)]
        if os.path.exists(os.path.join(ROOT, "img", "og", f"sport-{f}.jpg")):
            w, h = jpeg_size(os.path.join(ROOT, "img", "sport", f + ".jpg"))
            return (f'<figure class="stock"><img src="/img/sport/{f}.jpg?v=1" width="{w}" height="{h}" alt="Library photo: {E(SPORT_NAME[k].lower())}" loading="eager">'
                    f'<figcaption><b>{E(SPORT_NAME[k])}</b>. Library image, not the scene of this story.</figcaption></figure>', f"/img/og/sport-{f}.jpg")
        return "", ""
    if k:  # athletics and other drawn sport art keep the branded card
        return "", ""
    ic = icon_of(it, sec)
    if ic == "weather" or it.get("wx") or DRAWN_SEASON_RX.search(str(it.get("headline") or "")):
        return "", ""
    tk = town_key(it, sec)
    cr = TOWN_CREDITS.get(tk) if tk else None
    if not cr or not os.path.exists(os.path.join(ROOT, "img", "og", f"place-{tk}.jpg")):
        return "", ""
    lic = cr.get("license") or ""
    licl = "public domain" if lic in ("Public domain", "CC0") else lic
    lic_html = f'<a href="{E(cr["licenseUrl"])}" target="_blank" rel="noopener license">{E(licl)}</a>' if safe_url(cr.get("licenseUrl")) else E(licl)
    via = f', via <a href="{E(cr["source"])}" target="_blank" rel="noopener">Wikimedia Commons</a>' if safe_url(cr.get("source")) else ""
    w, h = jpeg_size(os.path.join(ROOT, "img", "places", tk + ".jpg"))
    return (f'<figure class="stock"><img src="/img/places/{tk}.jpg?v=1" width="{w}" height="{h}" alt="File photo: {E(cr.get("what"))}" loading="eager">'
            f'<figcaption><b>{E(cr.get("what"))}</b>. File photo, not the scene of this story. Photo: {E(cr.get("by"))}, {lic_html}{via}.</figcaption></figure>',
            f"/img/og/place-{tk}.jpg")

# ---------- story page map (owner's rule, 11 Nov 2026: every story page has a picture) ----------
# A story with no photo of any kind (no library, stock, town or sport photo, or the owner chose "map only") shows the
# same Essex map its front-page card draws: the story's places pinned and their districts shaded, or the whole county
# for county-wide stories. The map data (district outlines, places, reference towns) is read from index.html so the
# two always match; this is a straight port of the page's storyPins, storyDistricts, storyMap and mapCaption.
_MAP = None

def _map_data():
    global _MAP
    if _MAP is None:
        src = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
        grab = lambda n: re.search(r"^const " + n + r" = (.*?);\s*$", src, re.M).group(1)
        ad = re.sub(r"([{,]\s*)([a-z_]+):", r'\1"\2":', grab("AREA_DISTRICTS"))
        _MAP = {"M": json.loads(grab("ESSEX_MAP")), "P": json.loads(grab("ESSEX_PLACES")), "REF": json.loads(grab("REF_TOWNS")),
                "AD": json.loads(ad)}
        keys = sorted(_MAP["P"], key=len, reverse=True)
        _MAP["RX"] = [(k, re.compile(r"(^|[^a-z])" + re.sub(r"[-\s]", r"[-\\s]", re.escape(k).replace("\\ ", " ").replace("\\-", "-")) + r"(?![a-z])", re.I)) for k in keys]
    return _MAP

def story_pins(it):
    D = _map_data(); M = D["M"]
    pins, seen = [], set()
    def add(name, x, y, d):
        key = (round(x), round(y))
        if key not in seen:
            seen.add(key); pins.append({"name": name, "x": x, "y": y, "d": d})
    try:
        lat, lon = float(it.get("lat")), float(it.get("lon"))
        x, y = (lon - M["lon0"]) * M["kx"] * M["k"], (M["lat1"] - lat) * M["k"]
        add(re.split(r"[,&]", str(it.get("place") or ""))[0].strip() or "Here", x, y, None)
    except (TypeError, ValueError):
        pass
    def scan(txt):
        t = " " + str(txt or "") + " "
        for k, rx in D["RX"]:
            if rx.search(t):
                p = D["P"][k]; add(k, p[0], p[1], p[2]); t = rx.sub(" ", t, count=1)
    for f in ("place", "headline", "summary"):
        if not pins:
            scan(it.get(f))
    return pins[:3]

def story_districts(it, pins):
    D = _map_data()
    lit = []
    for p in pins:
        if p["d"] and p["d"] not in lit:
            lit.append(p["d"])
    if not lit:
        for a in it.get("areas") or []:
            for d in D["AD"].get(a, []):
                if d not in lit:
                    lit.append(d)
    return lit

def map_caption(it):
    pins = story_pins(it); lit = story_districts(it, pins)
    if pins:
        extra = f" · {lit[0]} district" if len(lit) == 1 and not any(p["name"].lower().startswith(re.split(r"[- ]", lit[0].lower())[0]) for p in pins) else ""
        return " · ".join(p["name"] for p in pins) + extra
    return " · ".join(lit) if lit else "Across Essex"

def _mix(hex_c, pct, base="#fbf8f1"):
    a = [int(hex_c[i:i + 2], 16) for i in (1, 3, 5)]; b = [int(base[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x * pct + y * (1 - pct)):02x}" for x, y in zip(a, b))

def story_map_svg(it, colour, aspect=0.5, zoom=760):
    D = _map_data(); M = D["M"]
    pins = story_pins(it); lit = story_districts(it, pins); countywide = not pins and not lit
    if pins:
        xs, ys = [p["x"] for p in pins], [p["y"] for p in pins]
        dx, dy = max(xs) - min(xs), max(ys) - min(ys)
        need = max(dx * 1.7 + 160, (dy * 1.7 + 160) / aspect)
        fit = min(820, max(zoom, need))
        if dx <= fit * .9 and dy <= fit * aspect * .85:
            cx, cy, w = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, fit
        else:
            cx, cy, w = pins[0]["x"], pins[0]["y"], zoom
    elif lit:
        cs = [M["centroids"][d] for d in lit if d in M["centroids"]]
        cx, cy = sum(c[0] for c in cs) / len(cs), sum(c[1] for c in cs) / len(cs)
        w = max(zoom, 560 if len(lit) > 2 else 0)
    else:
        cx, cy, w = 520, 360, 1000  # county-wide: the whole county fits the wide story-page frame
    w = min(w, 820) if not countywide else w; h = w * aspect
    x0, y0 = max(0, min(M["w"] - w, cx - w / 2)), max(0, min(M["h"] - h, cy - h / 2))
    fs, sw = w / 42, w / 520
    font = "font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif"
    fills = {"lit": (_mix(colour, .78), "#fbf8f1"), "all": (_mix(colour, .16), "#a99f8b"), "ed": ("#fbf8f1", "#b9af9c")}
    parts = []
    for n, d in M["districts"].items():
        f, st = fills["lit" if n in lit else "all" if countywide else "ed"]
        parts.append(f'<path d="{d}" fill="{f}" stroke="{st}" stroke-width="{sw * 1.1:.2f}"/>')
    pinned = {p["name"].lower() for p in pins}
    refs = []
    for t in D["REF"]:
        if t.lower() in pinned or t not in D["P"]:
            continue
        x, y = D["P"][t][0], D["P"][t][1]
        if any(((p["x"] - x) ** 2 + (p["y"] - y) ** 2) ** .5 < w / 9 for p in pins) or not (x0 <= x <= x0 + w and y0 <= y <= y0 + h):
            continue
        refs.append(f'<g><circle cx="{x}" cy="{y}" r="{fs * .22:.1f}" fill="#6d675c"/><text x="{x + fs * .45:.1f}" y="{y + fs * .32:.1f}" font-size="{fs * .78:.1f}" '
                    f'fill="#5a554b" stroke="#fbf8f1" stroke-width="{fs * .12:.1f}" paint-order="stroke" style="{font};font-weight:600">{E(t)}</text></g>')
    labels = []
    for d in lit:
        if d in M["centroids"] and not any(((p["x"] - M["centroids"][d][0]) ** 2 + (p["y"] - M["centroids"][d][1]) ** 2) ** .5 < w / 6 for p in pins):
            x, y = M["centroids"][d]
            labels.append(f'<text x="{x}" y="{y}" font-size="{fs * .8:.1f}" text-anchor="middle" fill="#fff" opacity=".9" style="{font};font-weight:800;letter-spacing:.12em">{E(d.upper())}</text>')
    placed, pin_svg = [], []
    for p in pins:
        r, lw, lh = fs * .42, len(p["name"]) * fs * .56 + fs * 1.1, fs * 1.7
        right = p["x"] + lw + fs < x0 + w
        tries = [(p["x"] + r + fs * .5 if right else p["x"] - r - fs * .5 - lw, p["y"] - fs * .85),
                 (p["x"] - r - fs * .5 - lw if right else p["x"] + r + fs * .5, p["y"] - fs * .85),
                 (p["x"] - lw / 2, p["y"] - r - fs * .4 - lh), (p["x"] - lw / 2, p["y"] + r + fs * .4)]
        hit = lambda t: any(t[0] < q[0] + q[2] and t[0] + lw > q[0] and t[1] < q[1] + q[3] and t[1] + lh > q[1] for q in placed)
        lx, ly = next((t for t in tries if not hit(t)), tries[0]); placed.append((lx, ly, lw, lh))
        pin_svg.append(f'<g><circle cx="{p["x"]}" cy="{p["y"]}" r="{r * 2.6:.1f}" fill="{colour}" opacity=".3"/>'
                       f'<circle cx="{p["x"]}" cy="{p["y"]}" r="{r:.1f}" fill="#fff" stroke="#14171f" stroke-width="{sw * 2.6:.2f}"/>'
                       f'<rect x="{lx:.1f}" y="{ly:.1f}" width="{lw:.1f}" height="{lh:.1f}" rx="{fs * .25:.1f}" fill="#14171f"/>'
                       f'<text x="{lx + fs * .55:.1f}" y="{ly + fs * 1.18:.1f}" font-size="{fs * .95:.1f}" fill="#fff" style="{font};font-weight:700">{E(p["name"])}</text></g>')
    cw = ""
    if countywide:
        c = M["centroids"]["Chelmsford"]
        cw = (f'<text x="{c[0]}" y="{c[1] + fs * .3:.1f}" font-size="{fs * 2.2:.1f}" text-anchor="middle" fill="{colour}" opacity=".35" '
              f'style="font-family:Georgia,serif;font-weight:900;letter-spacing:.2em">ESSEX</text>')
    what = ", ".join(p["name"] for p in pins) or ", ".join(lit) or "the whole county"
    return (f'<svg viewBox="{x0:.1f} {y0:.1f} {w:.1f} {h:.1f}" preserveAspectRatio="xMidYMid slice" role="img" aria-label="Map of Essex showing {E(what)}" '
            f'style="display:block;width:100%;height:auto;aspect-ratio:{1 / aspect:.3f};border-radius:10px;background:#d6e1e7">'
            f'<rect x="-2000" y="-2000" width="{M["w"] + 4000}" height="{M["h"] + 4000}" fill="#d6e1e7"/><path d="{M["context"]}" fill="#e7e0d1"/>'
            + "".join(parts) + "".join(labels) + "".join(refs) + cw + "".join(pin_svg) + "</svg>")

def map_figure(it, colour):
    return (f'<figure class="stock">{story_map_svg(it, colour)}'
            f'<figcaption><b>Where</b>. {E(map_caption(it))}</figcaption></figure>')

# ---------- story pages ----------
def collect(ed):
    out = []
    for sec, items in [("news", ed.get("stories", [])), ("sport", (ed.get("sport") or {}).get("stories", [])),
                       ("official", ed.get("official", [])), ("courts", ed.get("courts", [])),
                       ("community", ed.get("community", [])),
                       ("councilwatch", ed.get("councilwatch", []))]:  # features were removed in Nov 2026
        for it in items or []:
            if isinstance(it, dict) and slug_ok(it.get("id")) and it.get("headline"):
                out.append((sec, it))
    return out

def story_page(sec, it, more):
    sid = it["id"]
    url = f"{SITE}/story/{sid}/"
    title = str(it["headline"]).strip()
    summary = str(it.get("summary") or "").strip()
    desc = trunc(summary or title, 200)
    icon = icon_of(it, sec)
    colour = ICON_COLOUR.get(icon, "#3a3f4b")
    card = card_of(it, sec)
    t = parse_t(it.get("time"))
    # latest genuine update or headline change (owner's rule: a new headline moves the time shown)
    ups = [u for u in (parse_t(it.get("updated")), parse_t(it.get("headlineAt"))) if u]
    up = max(ups) if ups else None
    place = it.get("place") or "Essex"
    src = it.get("source") or ""
    surl = safe_url(it.get("url"))
    also = [a for a in (it.get("also") or []) if isinstance(a, dict) and safe_url(a.get("url"))]
    kicker = "Feature" if sec == "features" else "Council Watch" if sec == "councilwatch" else (it.get("tag") or SECTION_LABEL.get(sec, "News"))
    ld = {
        "@context": "https://schema.org", "@type": "NewsArticle",
        "headline": title, "description": desc,
        "mainEntityOfPage": url, "url": url,
        "image": [SITE + og_path(card)],
        "articleSection": SECTION_LABEL.get(sec, "News"),
        "author": {"@type": "Organization", "name": "The Seax", "url": SITE + "/"},
        "publisher": {"@type": "Organization", "name": "The Seax", "url": SITE + "/",
                      "logo": {"@type": "ImageObject", "url": f"{SITE}/icons/icon-512.png", "width": 512, "height": 512}},
    }
    if not it.get("noWhere"):
        ld["contentLocation"] = {"@type": "Place", "name": f"{place}, Essex"}
    if t:
        ld["datePublished"] = iso(t)
        ld["dateModified"] = iso(up or t)
    if surl:
        ld["isBasedOn"] = surl
    extra = f'<meta property="article:section" content="{E(SECTION_LABEL.get(sec, "News"))}">\n'
    if t:
        extra += f'<meta property="article:published_time" content="{iso(t)}">\n<meta property="article:modified_time" content="{iso(up or t)}">\n'
    extra += '<script type="application/ld+json">' + json.dumps(ld, ensure_ascii=False).replace("</", "<\\/") + "</script>\n"
    body = it.get("body") if isinstance(it.get("body"), list) else []
    points = it.get("points") if isinstance(it.get("points"), list) else []
    meta = [f"<b>{E(place)}</b>"]
    if t:
        meta.append(f'<time datetime="{iso(t)}">{E(uk_long(t))}</time>')
    if up and t and up > t + timedelta(minutes=5):
        meta.append(f'<span>Updated <time datetime="{iso(up)}">{E(uk_long(up))}</time></span>')
    if src and sec != "councilwatch":
        meta.append(f"<span>Reported by {E(src)}</span>")
    if sec == "councilwatch":
        meta.append("<span>Original reporting from council papers</span>")
    org = ""
    if it.get("org") and sec in ("official", "courts", "community"):
        org = f'<div class="org">{E(SECTION_LABEL[sec])} · {E(it["org"])}</div>'
    readfull = ""
    if surl:
        readfull = f"""<div class="readfull"><div><div class="k">Read the full story</div><div class="src">{E(src or host(surl))}</div></div>
<a class="go" href="{E(surl)}" target="_blank" rel="noopener">Open at {E(host(surl) or src)} ↗</a></div>"""
    if sec == "councilwatch":
        readfull = cw_record_box(it)
    also_html = ""
    if also:
        also_html = '<h2>Also reported by</h2><ul class="also">' + "".join(
            f'<li><a href="{E(a["url"])}" target="_blank" rel="noopener"><b>{E(a.get("name") or host(a["url"]))}</b> <span>{E(host(a["url"]))} ↗</span></a></li>' for a in also) + "</ul>"
    mail = CFG["contactEmail"]
    corr = f'mailto:{mail}?subject={quote("Correction: " + title)}&body={quote("Page: " + url)}'
    more_html = "".join(
        f'<a class="rel" href="/story/{E(m["id"])}/" style="--c:{ICON_COLOUR.get(icon_of(m, s), "#3a3f4b")}"><i></i><b>{E(m["headline"])}</b><span>{E(m.get("place") or "Essex")}</span></a>'
        for s, m in more)
    fig = "" if card in ("countyhall", "tiptree", "tiptree-2", "statefayre", "harlowcollege", "fog", "zoo", "gaswork", "datacentre", "remembrance", "food", "c2c", "bus", "pool", "homeless") or is_zoo(it, sec) or is_stansted(it, sec) or is_mersea(it, sec) or is_food(it, sec) or is_c2c(it, sec) or it.get("showMap") is True else stock_figure(it, sec)
    if not fig and card in LIBRARY_PHOTOS:
        cap = ("<b>County Hall, Chelmsford</b>, home of Essex County Council. Library image."
               if card == "countyhall" else "<b>Harlow College</b>. Library image."
               if card == "harlowcollege" else "<b>Colchester Zoo</b>. Library image, not the scene of this story."
               if card == "zoo" else "<b>London Stansted Airport</b>. Library image, not the scene of this story. Photo: London Stansted Airport."
               if card in STN_PHOTOS else "<b>West Mersea</b>. Library image, not the scene of this story."
               if card in MERSEA_PHOTOS else "<b>Gas works</b>. Library image, not the scene of this story."
               if card == "gaswork" else "<b>Data centre</b>. Library image, not the scene of this story."
               if card == "datacentre" else "<b>Bus</b>. Library image, not the scene of this story."
               if card == "bus" else "<b>Swimming pool</b>. Library image, not the scene of this story."
               if card == "pool" else "<b>Homelessness</b>. Library image, not the scene of this story."
               if card == "homeless" else "<b>Remembrance</b>. Library image, not the scene of this story."
               if card == "remembrance" else "<b>Christmas</b>. Library image, not the scene of this story."
               if card in ("christmas", "christmas-2") else "<b>Wilkin &amp; Sons, Tiptree</b>. Library image."
               if card in TIPTREE_PHOTOS else "<b>State Fayre, Hylands Park</b>. Library image."
               if card == "statefayre" else ('<b>c2c train</b>. Library image, not the scene of this story. Photo: kitmasterbloke, '
               f'<a href="{C2C_CREDIT["licenseUrl"]}" target="_blank" rel="noopener">CC BY 4.0</a>, via '
               f'<a href="{C2C_CREDIT["source"]}" target="_blank" rel="noopener">Wikimedia Commons</a>, cropped.')
               if card == "c2c" else "<b>Food and drink</b>. Library image, not the scene of this story."
               if card == "food" else "<b>Fog</b>. Library image, not the scene of this story."
               if card == "fog" else "<b>Library image</b>, not the scene of this story.")
        fig = (f'<figure class="stock"><img src="/img/topics/{card}.jpg?v=1" width="1200" height="655" '
               f'alt="Library photo: {LIBRARY_ALT.get(card, "police car blue lights")}" loading="eager">'
               f'<figcaption>{cap}</figcaption></figure>')
    if not fig and card == "breaking":
        fig = ('<figure class="stock"><img src="/img/topics/breaking.png?v=1" width="1200" height="630" '
               'alt="The Seax Breaking News graphic" loading="eager">'
               '<figcaption><b>Breaking news</b>. No photo of this story yet.</figcaption></figure>')
    og_img = PHOTOS[sid]["file"] if fig and card not in [k for k, _ in ROAD_OG] + ["hospital", "breaking"] + LIBRARY_PHOTOS else card
    pt = portrait_of(it)
    if pt:
        fig, og_img = portrait_figure(pt), pt["og"]
    if not fig:
        fig2, og2 = fallback_photo(it, sec, card)
        if fig2:
            fig, og_img = fig2, og2
    map_only = False
    if not fig:  # no photo of any kind: show the front page's map (the share card stays the branded card)
        fig, map_only = map_figure(it, colour), True
    if fig and not map_only:
        ld["image"] = [SITE + og_img if og_img.startswith("/") else ld["image"][0]]
        extra = extra.replace(SITE + og_path(card), ld["image"][0])
    return head(f"{title} · The Seax", desc, url, og_img, "article", extra) + f"""<main class="wrap story">
<article style="--c:{colour}">
  <div class="kick"><span>{E(kicker)}</span><span>{E(place)}</span></div>
  {org}{cw_badge(it) if sec == "councilwatch" else ""}
  <h1>{E(title)}</h1>
  <!-- Article Start -->
  {f'<p class="standfirst">{E(summary)}</p>' if summary else ''}
  <div class="meta">{' <span class="dot">·</span> '.join(meta)}</div>
  {share_bar(url, title)}
  {fig}
  {''.join(f'<p>{E(p)}</p>' for p in body if str(p).strip())}
  {('<h2>Key points</h2><ul class="points">' + ''.join(f'<li>{E(p)}</li>' for p in points) + '</ul>') if points else ''}
  <!-- Article End -->
  {readfull}
  {also_html}
  {cw_note(corr) if sec == "councilwatch" else f'<p class="note">This is a summary written by The Seax. The original reporting, quotes and images belong to {E(src or "the outlet named above")}{" and the other outlets listed" if also else ""}. <a href="{E(corr)}">Spotted a mistake? Tell us</a>.</p>'}
</article>
<aside>
  <h3>More from Essex</h3>
  {more_html}
  <a class="front" href="/">Go to the front page →</a>
</aside>
</main>
{newsletter_box()}
{foot()}{SHARE_JS}
</body></html>
"""


# ---------- local news pages (SEO: one page per area, e.g. /news/chelmsford/) ----------
# key matches the front page area picker; slug is the public URL; words find the area from a story's place
AREA_PAGES = [
    ("chelmsford", "chelmsford", "Chelmsford", "Chelmsford news", "the city and nearby places such as Great Baddow, Broomfield, Writtle and South Woodham Ferrers",
     ["chelmsford", "great baddow", "broomfield", "writtle", "south woodham", "danbury", "boreham", "springfield", "galleywood", "chelmer village", "howe green"],
     ["chelmsford"]),
    ("colchester", "colchester", "Colchester", "Colchester news", "the city and nearby places such as Stanway, Wivenhoe, West Mersea and Tiptree",
     ["colchester", "stanway", "wivenhoe", "mersea", "tiptree", "layer de la haye", "abberton", "mount bures", "dedham", "rowhedge", "marks tey"],
     ["colchester"]),
    ("southend", "southend", "Southend", "Southend news", "the city and nearby places such as Leigh-on-Sea, Westcliff, Shoeburyness and Rochford",
     ["southend", "leigh-on-sea", "westcliff", "shoebury", "prittlewell", "thorpe bay", "rochford", "rayleigh", "hockley", "hullbridge", "great wakering"],
     ["southend", "rochford"]),
    ("south", "basildon-thurrock", "Basildon, Thurrock & Castle Point", "Basildon, Thurrock and Castle Point news", "Basildon, Billericay, Wickford, Grays, Tilbury, Purfleet, Stanford-le-Hope, Canvey Island and Benfleet",
     ["basildon", "billericay", "wickford", "laindon", "pitsea", "crays hill", "thurrock", "grays", "tilbury", "purfleet", "stanford-le-hope", "corringham", "aveley", "south ockendon", "chafford", "lakeside", "fobbing", "canvey", "benfleet", "hadleigh", "thundersley", "castle point"],
     ["basildon", "thurrock", "castlepoint"]),
    ("brentwood", "brentwood", "Brentwood", "Brentwood news", "the town and nearby places such as Shenfield, Ingatestone, Hutton and Mountnessing",
     ["brentwood", "shenfield", "ingatestone", "hutton", "mountnessing", "warley", "pilgrims hatch", "doddinghurst", "navestock"],
     ["brentwood"]),
    ("braintree", "braintree-witham", "Braintree & Witham", "Braintree and Witham news", "Braintree, Witham, Halstead, Great Notley, Coggeshall and nearby villages",
     ["braintree", "witham", "halstead", "great notley", "coggeshall", "wethersfield", "kelvedon", "silver end", "rayne", "sible hedingham"],
     ["braintree"]),
    ("maldon", "maldon", "Maldon & Dengie", "Maldon news", "Maldon, Heybridge, Burnham-on-Crouch, Tollesbury and the Dengie peninsula",
     ["maldon", "heybridge", "burnham-on-crouch", "dengie", "tollesbury", "latchingdon", "great totham", "southminster", "bradwell"],
     ["maldon"]),
    ("tendring", "clacton-tendring", "Clacton, Harwich & Tendring", "Clacton, Harwich and Tendring news", "Clacton-on-Sea, Harwich, Dovercourt, Frinton, Walton, Brightlingsea and the Tendring coast",
     ["tendring", "clacton", "harwich", "dovercourt", "frinton", "walton", "brightlingsea", "st osyth", "jaywick", "manningtree", "kirby le soken", "holland-on-sea"],
     ["tendring"]),
    ("uttlesford", "saffron-walden-uttlesford", "Saffron Walden & Uttlesford", "Saffron Walden, Dunmow and Stansted news", "Saffron Walden, Great Dunmow, Stansted, Thaxted and the villages of Uttlesford",
     ["uttlesford", "saffron walden", "dunmow", "stansted", "thaxted", "little canfield", "great bardfield", "takeley", "elsenham", "newport"],
     ["uttlesford"]),
    ("epping", "harlow-epping", "Harlow & Epping Forest", "Harlow and Epping news", "Harlow, Epping, Loughton, Waltham Abbey, Chigwell, Ongar and North Weald",
     ["harlow", "epping", "loughton", "waltham abbey", "chigwell", "ongar", "north weald", "buckhurst hill", "theydon"],
     ["harlow", "epping"]),
]

def areas_of(rec):
    """Areas for an archive record: its own tags, or guessed from its place for older records."""
    a = [x for x in (rec.get("a") or []) if x != "all"]
    if a:
        return a
    pl = str(rec.get("place") or "").lower()
    return [key for key, _sl, _n, _h, _d, words, _c in AREA_PAGES if any(w in pl for w in words)]

def area_pages(archive):
    """/news/ hub and one page per area. Returns the list of (url, lastmod) for the sitemap."""
    recs = sorted([(sid, r) for sid, r in archive.items() if r.get("sec") in ("news", "sport", "official", "courts", "community", "councilwatch")],
                  key=lambda kv: kv[1].get("t") or kv[1].get("first") or "", reverse=True)
    def row(sid, r):
        t = parse_t(r.get("t"))
        lab = "Council Watch" if r.get("sec") == "councilwatch" else SECTION_LABEL.get(r.get("sec"), "News")
        return (f'<a class="cw-row" href="/story/{E(sid)}/"><span class="cw-c">{E(lab)}</span>'
                f'<b>{E(r["h"])}</b><span class="cw-m">{E(r.get("place") or "")}{(" · " + E(uk_day(t))) if t else ""}</span></a>')
    def ld(name, url, items):
        return ('<script type="application/ld+json">' + json.dumps({
            "@context": "https://schema.org", "@graph": [
                {"@type": "CollectionPage", "name": name, "url": url, "inLanguage": "en-GB",
                 "isPartOf": {"@type": "WebSite", "name": "The Seax", "url": SITE + "/"},
                 "mainEntity": {"@type": "ItemList", "itemListElement": [
                     {"@type": "ListItem", "position": i + 1, "url": f"{SITE}/story/{sid}/"} for i, (sid, _r) in enumerate(items[:20])]}},
                {"@type": "BreadcrumbList", "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "The Seax", "item": SITE + "/"},
                    {"@type": "ListItem", "position": 2, "name": "Essex news", "item": SITE + "/news/"}] +
                    ([{"@type": "ListItem", "position": 3, "name": name, "item": url}] if not url.endswith("/news/") else [])}]},
            ensure_ascii=False).replace("</", "<\\/") + "</script>\n")
    links = " · ".join(f'<a href="/news/{sl}/">{E(nm)}</a>' for _k, sl, nm, *_ in AREA_PAGES)
    pages, changed = [], 0
    hub_url = f"{SITE}/news/"
    hub_desc = "The latest Essex news from every corner of the county: Chelmsford, Colchester, Southend, Basildon, Thurrock, Harlow, Clacton and more, updated through the day."
    hub = f"""<main class="wrap prose cw-hub">
<div class="kick"><span>Essex news</span><span>Every area</span></div>
<h1>Essex news</h1>
<p class="standfirst">{E(hub_desc)}</p>
<h2>News by area</h2>
<p class="area-links">{links}</p>
<h2>Latest across Essex</h2>
<div class="cw-list">{"".join(row(sid, r) for sid, r in recs[:40])}</div>
<p><a href="/">Go to the live front page →</a></p>
</main>"""
    changed += write("news/index.html", head("Essex News Today: latest news from across Essex · The Seax", hub_desc, hub_url, "default",
                                              extra=ld("Essex news", hub_url, recs)) + hub + newsletter_box() + foot() + "</body></html>\n")
    pages.append((hub_url, (recs[0][1].get("t") or NOW.isoformat())[:10] if recs else None))
    for key, sl, nm, heading, covers, _words, councils in AREA_PAGES:
        mine = [(sid, r) for sid, r in recs if key in areas_of(r)]
        u = f"{SITE}/news/{sl}/"
        desc = f"The latest {heading} from The Seax, covering {covers}. Updated through the day, with every story linked to its original source."
        cw = " · ".join(f'<a href="/council-watch/{c}/">Council Watch: what the council is deciding</a>' if len(councils) == 1 else
                        f'<a href="/council-watch/{c}/">{E(c.title().replace("point", " Point"))} council</a>' for c in councils)
        others = " · ".join(f'<a href="/news/{s2}/">{E(n2)}</a>' for _k2, s2, n2, *_ in AREA_PAGES if s2 != sl)
        page = f"""<main class="wrap prose cw-hub">
<div class="kick"><span><a href="/news/">Essex news</a></span><span>{E(nm)}</span></div>
<h1>{E(heading[0].upper() + heading[1:])}</h1>
<p class="standfirst">{E(desc)}</p>
<div class="cw-list">{"".join(row(sid, r) for sid, r in mine[:40]) or '<p>No stories for this area yet. The latest from across Essex is on the <a href="/news/">Essex news</a> page.</p>'}</div>
<h2>Council decisions</h2>
<p>{cw}</p>
<h2>Elsewhere in Essex</h2>
<p class="area-links">{others}</p>
<p><a href="/">Go to the live front page →</a></p>
</main>"""
        title = f"{heading[0].upper() + heading[1:]}: latest stories today · The Seax"
        changed += write(f"news/{sl}/index.html", head(title, desc, u, "default", extra=ld(heading[0].upper() + heading[1:], u, mine)) +
                         page + newsletter_box() + foot() + "</body></html>\n")
        pages.append((u, (mine[0][1].get("t") or NOW.isoformat())[:10] if mine else None))
    return pages, changed

# ---------- Council Watch ----------
CW_STAGE = {"decided": "Decided", "upcoming": "Coming up", "proposed": "Proposed", "held": "Discussed", "update": "Update"}

def cw_badge(it):
    stage = CW_STAGE.get(str(it.get("stage") or "").lower(), "")
    bits = [f'<a href="/council-watch/{E(it.get("council") or "")}/">{E(it.get("councilName") or "Essex council")}</a>' if it.get("council") else E(it.get("councilName") or "")]
    if it.get("meeting"):
        bits.append(E(it["meeting"]))
    return (f'<div class="org cw"><b>Council Watch</b> · {" · ".join(b for b in bits if b)}'
            + (f' <span class="cw-stage cw-{E(str(it.get("stage")).lower())}">{E(stage)}</span>' if stage else "") + "</div>")

def cw_record_box(it):
    docs = [d for d in (it.get("docs") or []) if isinstance(d, dict) and safe_url(d.get("url"))]
    murl = safe_url(it.get("meetingUrl"))
    if not docs and not murl:
        return ""
    rows = "".join(
        f'<li><a href="{E(d["url"])}" target="_blank" rel="noopener"><b>{E(d.get("title") or "Council document")}</b>'
        f'<span>{("page " + E(d["page"]) + " · ") if d.get("page") else ""}{E(host(d["url"]))} ↗</span></a></li>' for d in docs)
    meet = (f'<li><a href="{E(murl)}" target="_blank" rel="noopener"><b>Meeting page: {E(it.get("meeting") or "agenda and minutes")}</b>'
            f'<span>{E(host(murl))} ↗</span></a></li>') if murl else ""
    return f'<h2>From the public record</h2><ul class="also cw-docs">{rows}{meet}</ul>'

def cw_note(corr):
    return ('<p class="note">Council Watch is original reporting by The Seax from public council papers: agendas, reports, decisions and minutes. '
            'It is written with the help of AI from the documents linked above, and every fact comes from them. Councils sometimes change '
            'decisions after a meeting, so check the minutes for the final word. '
            f'<a href="{E(corr)}">Spotted a mistake? Tell us</a>. <a href="/council-watch/">How Council Watch works</a>.</p>')

def cw_load(name):
    p = os.path.join(ROOT, "data", "councilwatch", name)
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}

def cw_councils(ed):
    names = {}
    for cid, rec in (cw_load("status.json").get("councils") or {}).items():
        names[cid] = rec.get("name") or cid
    for it in ed.get("councilwatch") or []:
        if it.get("council"):
            names.setdefault(it["council"], it.get("councilName") or it["council"])
    return names

def cw_card(sid, rec):
    t = parse_t(rec.get("t"))
    return (f'<a class="cw-row" href="/story/{E(sid)}/"><span class="cw-c">{E(rec.get("councilName") or "")}</span>'
            f'<b>{E(rec["h"])}</b><span class="cw-m">{E(rec.get("place") or "")}{(" · " + E(uk_day(t))) if t else ""}</span></a>')

def cw_meet_rows(meets):
    out = []
    for m in meets:
        d = parse_t(m.get("date") + "T12:00:00Z") if m.get("date") else None
        items = "".join(f"<li>{E(x)}</li>" for x in (m.get("items") or [])[:4])
        out.append(f'<li class="cw-meet"><a href="{E(safe_url(m.get("url")) or "#")}" target="_blank" rel="noopener">'
                   f'<span class="cw-d">{E(uk_day(d)) if d else ""}{(" · " + E(m["time"])) if m.get("time") else ""}</span>'
                   f'<b>{E(m.get("councilName") or "")}: {E(m.get("committee") or "")}</b></a>{("<ul>" + items + "</ul>") if items else ""}</li>')
    return "".join(out)

def cw_pages(ed, archive):
    """/council-watch/ hub and one page per council. Returns the list of (url, lastmod)."""
    names = cw_councils(ed)
    cal = (cw_load("calendar.json").get("meetings") or [])
    status = cw_load("status.json").get("councils") or {}
    live = {it["id"]: it for it in (ed.get("councilwatch") or []) if isinstance(it, dict) and it.get("id")}
    recs = sorted([(sid, r) for sid, r in archive.items() if r.get("sec") == "councilwatch"],
                  key=lambda kv: kv[1].get("t") or kv[1].get("first") or "", reverse=True)
    for sid, r in recs:
        if sid in live:
            r["councilName"] = live[sid].get("councilName") or r.get("councilName")
    pages = []
    upcoming = [m for m in cal if m.get("date", "") >= NOW.astimezone(UK).date().isoformat()]
    cover = []
    for cid, nm in sorted(names.items(), key=lambda kv: kv[1]):
        st = (status.get(cid) or {}).get("state", "")
        how = {"ok": "papers read automatically", "quiet": "papers read automatically", "blocked": "checked by our desk (site limits automated reading)",
               "unreachable": "checked by our desk", "manual": "checked by our desk", "refused": "checked by our desk (site asks automated readers to stay away)"}.get(st, "")
        n = sum(1 for _, r in recs if r.get("council") == cid)
        cover.append(f'<li><a href="/council-watch/{E(cid)}/">{E(nm)}</a><span>{E(how)}{(" · " + str(n) + (" story" if n == 1 else " stories")) if n else ""}</span></li>')
    url = f"{SITE}/council-watch/"
    desc = "Original reporting from every Essex council's public papers: what was decided, what is coming up, and what it means for you."
    body = f"""<main class="wrap prose cw-hub">
<div class="kick"><span>Council Watch</span><span>Essex</span></div>
<h1>Council Watch</h1>
<p class="standfirst">{E(desc)}</p>
<h2>Latest from Council Watch</h2>
<div class="cw-list">{"".join(cw_card(sid, r) for sid, r in recs[:40]) or '<p>The first Council Watch stories are on their way.</p>'}</div>
<h2>Coming up at your councils</h2>
<ul class="cw-meets">{cw_meet_rows(upcoming[:30]) or '<li>No upcoming meetings found yet.</li>'}</ul>
<h2>Councils we watch</h2>
<ul class="cw-cover">{"".join(cover)}</ul>
<h2 id="how">How Council Watch works</h2>
<p>Essex has fifteen principal councils: Essex County Council, Southend, Thurrock and twelve district, borough and city councils. Each publishes agendas, reports, decisions and minutes that few people have time to read. Council Watch reads them for you.</p>
<p>Twice a day an automated collector visits each council's public meetings website, politely and within the rules each site publishes, and lists the meetings, agenda items and reports. It ranks items by how much they are likely to matter to residents: money, services, homes, planning, closures, consultations and decisions. Our desk then writes short stories from the most important papers, with the help of AI, and links every story to the exact documents and pages it comes from.</p>
<p>Council Watch only reports what the council papers say. It does not report private or exempt business, and it does not name members of the public who appear in council papers. Where a council's website limits automated reading, our desk checks it by hand instead.</p>
<p>Spotted a mistake, or work for an Essex council and want to point us at something? Email <a href="mailto:{E(CFG['contactEmail'])}">{E(CFG['contactEmail'])}</a>.</p>
</main>"""
    changed = write("council-watch/index.html", head("Council Watch: what Essex councils are deciding · The Seax", desc, url, "council") + body + newsletter_box() + foot() + "</body></html>\n")
    pages.append((url, NOW.date().isoformat()))
    for cid, nm in names.items():
        mine = [(sid, r) for sid, r in recs if r.get("council") == cid]
        meets = [m for m in upcoming if m.get("council") == cid]
        u = f"{SITE}/council-watch/{cid}/"
        d2 = f"What {nm} is deciding: Council Watch stories from its public papers, and its upcoming meetings."
        page = f"""<main class="wrap prose cw-hub">
<div class="kick"><span><a href="/council-watch/">Council Watch</a></span><span>{E(nm)}</span></div>
<h1>{E(nm)}</h1>
<p class="standfirst">{E(d2)}</p>
<h2>Latest</h2>
<div class="cw-list">{"".join(cw_card(sid, r) for sid, r in mine[:40]) or '<p>No Council Watch stories for this council yet.</p>'}</div>
<h2>Coming up</h2>
<ul class="cw-meets">{cw_meet_rows(meets[:20]) or '<li>No upcoming meetings found.</li>'}</ul>
<p><a href="/council-watch/#how">How Council Watch works</a></p>
</main>"""
        changed += write(f"council-watch/{cid}/index.html", head(f"{nm}: Council Watch · The Seax", d2, u, "council") + page + newsletter_box() + foot() + "</body></html>\n")
        pages.append((u, (mine[0][1].get("t") or NOW.isoformat())[:10] if mine else None))
    return pages, changed

# ---------- about ----------
def photo_credits():
    """Credits for the town photographs in img/places (all from Wikimedia Commons)."""
    try:
        cr = json.load(open(os.path.join(ROOT, "img", "places", "credits.json"), encoding="utf-8"))
    except Exception:
        return ""
    rows = []
    for k in sorted(cr, key=lambda k: cr[k]["what"]):
        c = cr[k]
        lic = c["license"]
        lic_html = f'<a href="{E(c["licenseUrl"])}" rel="license noopener">{E(lic)}</a>' if c.get("licenseUrl") else E(lic)
        rows.append(f'<li>{E(c["what"])}: photo by {E(c["by"])}, {lic_html}, via <a href="{E(c["source"])}" rel="noopener">Wikimedia Commons</a></li>')
    return ('<h2 id="photo-credits">Photo credits</h2>\n<p>Town photographs on The Seax come from Wikimedia Commons and are used under the licences shown. '
            'They have been resized for the web and are shared under the same terms. Our map artwork is our own.</p>\n<ul class="credits">' + "".join(rows) + '<li>London Stansted Airport library images: photos by London Stansted Airport</li>' + f'<li>c2c train 357 040 at Ripple Lane (used on c2c stories): photo by kitmasterbloke, <a href="{C2C_CREDIT["licenseUrl"]}" rel="license noopener">CC BY 4.0</a>, via <a href="{C2C_CREDIT["source"]}" rel="noopener">Wikimedia Commons</a>; cropped and resized</li>' + "".join(f'<li>{E(p["name"])} (file photo): photo by {E(p["creator"])}, <a href="{E(p["licenseUrl"])}" rel="license noopener">{E(p["license"])}</a>, via <a href="{E(p["source"])}" rel="noopener">{E(p.get("provider") or "source")}</a>; set on a blurred background and shared under the same licence</li>' for p in PORTRAITS) + "</ul>\n")


def about_page():
    mail = CFG["contactEmail"]
    url = f"{SITE}/about/"
    return head("About The Seax · The Seax", "How The Seax works, who it is for, how to contact us and how we correct mistakes.", url, "default") + f"""<main class="wrap prose">
<h1>About The Seax</h1>
<p class="standfirst">The Seax is a free, independent website for the people of Essex: the county's news, sport, weather, public services, community life and what's on, in one place and updated through the day.</p>

<h2>How The Seax works</h2>
<p>We watch hundreds of trusted sources across Essex and beyond: local newspapers and radio, hyperlocal and independent newsrooms, Essex Police, the fire and ambulance services, councils, the NHS, courts, charities, clubs and venues, plus national and specialist outlets when they report on Essex.</p>
<p>The Seax is produced with the help of AI. Automated research tools gather the latest reports each hour, and AI writes our headlines, summaries and short story pages in our own words, following our editorial rules. Every story names the outlet that reported it and links directly to the original, so you can always read the full report and support the journalists who did the work. When only one outlet has reported a story, our summary is deliberately short and points you to theirs.</p>
<p>We do not copy articles, take photographs from other publishers, or publish anything that is not reported by a named source or set out in a public document.</p>
<h2 id="council-watch">Council Watch</h2>
<p><a href="/council-watch/">Council Watch</a> is The Seax's own reporting. Twice a day we read the public meeting papers of Essex's councils (agendas, reports, decisions and minutes), politely and within each website's published rules, and write short stories about the decisions that matter to residents. Every Council Watch story links to the council documents, and the pages, it is based on. It is written with the help of AI from those documents only.</p>

<h2>Our editorial rules</h2>
<ul>
<li>Facts only as the source states them. No invented quotes, figures, scores or details.</li>
<li>Crime and court reporting is limited to what police and courts have said. People who have been arrested or charged are presumed innocent, and we do not report anything that could prejudice a trial.</li>
<li>We never name victims of sexual offences or identify children involved in criminal cases.</li>
<li>We do not report suicide or self-harm, or individual inquests.</li>
</ul>

<h2 id="corrections">Corrections and complaints</h2>
<p>We work hard to be accurate, but if we get something wrong we want to put it right quickly. Email <a href="mailto:{E(mail)}?subject=Correction">{E(mail)}</a> with a link to the page and what is wrong. We aim to review every correction request within 24 hours and will correct, clarify or remove content where it is inaccurate, unfair or should not have been published. Significant corrections are noted on the page.</p>
<p>If a story concerns you personally and you would like it reviewed or removed, contact us at the same address.</p>

<h2>Contact</h2>
<p>News tips, corrections and partnership ideas: <a href="mailto:{E(mail)}">{E(mail)}</a>.</p>
<p>If you run an Essex newsroom, magazine or community site and would like to be featured, or would prefer we did not summarise your work, please get in touch and we will respond promptly.</p>

<h2>Privacy</h2>
<p>The Seax does not use advertising cookies or track you across other websites. {"We count visits with GoatCounter, a privacy-friendly service that uses no cookies and collects no personal data." if CFG.get("goatcounter") else "We may count visits with a privacy-friendly service that uses no cookies and collects no personal data."} Our free morning newsletter is delivered by follow.it; if you sign up, your email address is used only to send it, and every email includes an unsubscribe link.</p>

<h2 id="launch">Our launch</h2>
<p>The Seax went live at 7am on Monday 9 November 2026: a free website that brings Essex's news, sport, council decisions, community life and what's on together in one place, from Harlow to Harwich and Saffron Walden to Southend.</p>
<p><a href="/story/the-seax-launches/">Read our launch story: A new way to see Essex</a></p>

{photo_credits()}
<h2>Why "The Seax"?</h2>
<p>The seax is the short sword of the Saxons, and three seaxes appear on the arms of Essex: gules, three seaxes fesswise in pale argent, pommels and hilts or. Our badge follows that blazon.</p>
</main>
{newsletter_box()}
{foot()}
</body></html>
"""

# ---------- briefing ----------
def briefing(ed, when):
    day = when.astimezone(UK).date()
    stories = {s["id"]: s for s in ed.get("stories", []) if isinstance(s, dict) and s.get("id")}
    lead = stories.get((ed.get("lead") or {}).get("id"))
    picked = [lead] if lead else []
    for fid in ed.get("front", []) or []:
        if fid in stories and stories[fid] not in picked:
            picked.append(stories[fid])
    cutoff = when - timedelta(hours=30)
    rest = sorted([s for s in stories.values() if s not in picked and (parse_t(s.get("time")) or when) >= cutoff],
                  key=lambda s: (-(s.get("weight") or 0), -(parse_t(s.get("time")) or when).timestamp()))
    picked += rest[: max(0, 8 - len(picked))]
    picked = [p for p in picked if p]
    w = ed.get("weather") or {}
    today = next((d for d in (w.get("days") or []) if d.get("date") == day.isoformat()), None)
    travel = [t for t in (ed.get("travel") or []) if t.get("level") in ("red", "amber")][:4]
    res = []
    for r in (ed.get("sport") or {}).get("results", []) or []:
        rt = parse_t(r.get("date"))
        if rt and rt >= when - timedelta(hours=40) and r.get("hs") is not None and r.get("as") is not None:
            res.append(r)
    res.sort(key=lambda r: r.get("date") or "", reverse=True)
    whats = []
    for ev in (ed.get("events") or []) + (ed.get("culture") or []):
        s, e = parse_t(ev.get("start")), parse_t(ev.get("end"))
        if not s:
            continue
        sd, ed_ = s.astimezone(UK).date(), (e.astimezone(UK).date() if e else s.astimezone(UK).date())
        if sd == day or (e and sd <= day <= ed_ and (ed_ - sd).days <= 3):
            whats.append(ev)
    whats = whats[:5]
    cw = sorted([c for c in (ed.get("councilwatch") or []) if isinstance(c, dict) and c.get("id") and c.get("headline")
                 and (parse_t(c.get("time")) or when - timedelta(days=9)) >= when - timedelta(hours=40)],
                key=lambda c: (-(c.get("weight") or 0), c.get("time") or ""))[:3]
    return {"date": day.isoformat(), "label": uk_day(when), "lead": lead, "stories": picked, "weather": today,
            "warnings": w.get("warnings") or [], "travel": travel, "results": res[:8], "whats": whats, "council": cw}

def briefing_html_inner(b, email=False):
    """The briefing body. email=True gives inline-styled markup for RSS-to-email."""
    S = (lambda css: f' style="{css}"') if email else (lambda css: "")
    out = []
    if b["weather"] or b["warnings"]:
        wx = b["weather"]
        line = f"{E(wx.get('desc', ''))}, high {E(wx.get('hi'))}°C, low {E(wx.get('lo'))}°C" if wx else ""
        if wx and wx.get("rain") is not None:
            line += f", {E(wx.get('rain'))}% chance of rain"
        out.append(f'<h2{S("font:700 18px Arial,sans-serif;margin:22px 0 6px")}>Weather</h2><p{S("margin:0 0 6px")}>{line}.</p>' if line else "")
        for wn in b["warnings"][:3]:
            out.append(f'<p{S("margin:0 0 6px;color:#960a21;font-weight:bold")}>⚠ {E(wn)}</p>')
    if b["stories"]:
        out.append(f'<h2{S("font:700 18px Arial,sans-serif;margin:22px 0 6px")}>The stories that matter</h2>')
        for i, s in enumerate(b["stories"]):
            u = f"{SITE}/story/{s['id']}/"
            big = i == 0
            out.append(
                f'<div class="bs{" lead" if big else ""}"{S("margin:0 0 14px")}><a href="{u}"{S("color:#15161b;text-decoration:none;font:" + ("800 22px" if big else "700 17px") + " Arial,sans-serif")}>{E(s["headline"])}</a>'
                f'<p{S("margin:4px 0 0;color:#3a3a40")}>{E(s.get("place") or "Essex")} · {E(trunc(s.get("summary"), 220))}</p></div>')
    if b.get("council"):
        out.append(f'<h2{S("font:700 18px Arial,sans-serif;margin:22px 0 6px")}>From Council Watch</h2>')
        for c in b["council"]:
            out.append(f'<div class="bs"{S("margin:0 0 12px")}><a href="{SITE}/story/{E(c["id"])}/"{S("color:#15161b;text-decoration:none;font:700 17px Arial,sans-serif")}>{E(c["headline"])}</a>'
                       f'<p{S("margin:4px 0 0;color:#3a3a40")}>{E(c.get("councilName") or "")} · {E(trunc(c.get("summary"), 200))}</p></div>')
    if b["travel"]:
        out.append(f'<h2{S("font:700 18px Arial,sans-serif;margin:22px 0 6px")}>Travel</h2><ul>' + "".join(
            f'<li><a href="{E(safe_url(t.get("url")) or SITE + "/")}">{E(t.get("text"))}</a></li>' for t in b["travel"]) + "</ul>")
    if b["results"]:
        out.append(f'<h2{S("font:700 18px Arial,sans-serif;margin:22px 0 6px")}>Results</h2><ul>' + "".join(
            f'<li>{E(r.get("home"))} {E(r.get("hs"))}-{E(r.get("as"))} {E(r.get("away"))} <span{S("color:#6d675c")}>({E(r.get("comp"))})</span></li>' for r in b["results"]) + "</ul>")
    if b["whats"]:
        out.append(f'<h2{S("font:700 18px Arial,sans-serif;margin:22px 0 6px")}>On today</h2><ul>' + "".join(
            f'<li><a href="{E(safe_url(ev.get("url")) or SITE + "/#whatson")}">{E(ev.get("title"))}</a>, {E(ev.get("where") or ev.get("venue") or "")}{(" · " + E(ev.get("price"))) if ev.get("price") else ""}</li>' for ev in b["whats"]) + "</ul>")
    out.append(f'<p{S("margin:22px 0 0;color:#6d675c;font-size:13px")}>Every story links to the original reporting. More all day at <a href="{SITE}/">theseax.com</a>.</p>')
    return "\n".join(x for x in out if x)

def whatsapp_text(b):
    lines = [f"*Essex at 7* · {b['label']}", ""]
    for s in b["stories"][:6]:
        lines.append(f"• {s['headline']}\n{SITE}/story/{s['id']}/")
    if b["weather"]:
        wx = b["weather"]
        lines += ["", f"Weather: {wx.get('desc', '')}, high {wx.get('hi')}°C"]
    for t in b["travel"][:2]:
        lines.append(f"Travel: {t.get('text')}")
    lines += ["", f"More: {SITE}/"]
    return "\n".join(lines)

def briefing_page(b):
    url = f"{SITE}/briefing/{b['date']}/"
    lead = b["lead"] or (b["stories"][0] if b["stories"] else None)
    title = f"Essex at 7, {b['label']}" + (f": {lead['headline']}" if lead else "")
    desc = "The Seax morning briefing: the Essex stories that matter, weather, travel and results."
    wa = whatsapp_text(b)
    return head(f"{trunc(title, 120)} · The Seax", desc, url, "briefing") + f"""<main class="wrap prose briefing">
<div class="kick" style="--c:#c8102e"><span>Morning briefing</span><span>{E(b['label'])}</span></div>
<h1>Essex at 7</h1>
<p class="standfirst">Good morning. Here is what matters in Essex today.</p>
{share_bar(url, 'Essex at 7, ' + b['label'])}
{briefing_html_inner(b)}
<details class="wa-copy"><summary>Copy this briefing for WhatsApp</summary><textarea readonly rows="14">{E(wa)}</textarea></details>
</main>
{newsletter_box()}
{foot()}{SHARE_JS}
</body></html>
"""

def rss(title, link, desc, self_url, items):
    out = [f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:content="http://purl.org/rss/1.0/modules/content/">
<channel>
<title>{E(title)}</title>
<link>{E(link)}</link>
<description>{E(desc)}</description>
<language>en-gb</language>
<lastBuildDate>{format_datetime(NOW)}</lastBuildDate>
<atom:link href="{E(self_url)}" rel="self" type="application/rss+xml"/>
<image><url>{SITE}/icons/icon-192.png</url><title>{E(title)}</title><link>{E(link)}</link></image>"""]
    for it in items:
        out.append("<item>" + "".join([
            f"<title>{E(it['title'])}</title>", f"<link>{E(it['link'])}</link>",
            f'<guid isPermaLink="true">{E(it["link"])}</guid>',
            f"<pubDate>{format_datetime(it['date'])}</pubDate>" if it.get("date") else "",
            f"<category>{E(it['cat'])}</category>" if it.get("cat") else "",
            f"<description>{E(it['desc'])}</description>",
            f"<content:encoded><![CDATA[{it['html'].replace(']]>', ']]&gt;')}]]></content:encoded>" if it.get("html") else "",
        ]) + "</item>")
    out.append("</channel>\n</rss>\n")
    return "\n".join(out)

# ---------- index.html config block ----------
def patch_index(latest_briefing):
    p = os.path.join(ROOT, "index.html")
    s = open(p, encoding="utf-8").read()
    conf = {k: CFG.get(k, "") for k in ("site", "contactEmail", "goatcounter", "newsletterForm", "newsletterField", "newsletterLink", "newsletterName", "whatsappChannel", "facebookPage")}
    conf["latestBriefing"] = latest_briefing or ""
    block = "<!--seax-config--><script>window.SEAX_CONFIG = " + json.dumps(conf, ensure_ascii=False) + ";</script>"
    if conf["goatcounter"]:
        block += analytics()
    block += "<!--/seax-config-->"
    new = re.sub(r"<!--seax-config-->.*?<!--/seax-config-->", lambda m: block, s, count=1, flags=re.S)
    if new != s:
        open(p, "w", encoding="utf-8").write(new)
        return True
    return False

# ---------- main ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--briefing-now", action="store_true", help="make today's briefing even outside 06:30-12:00 UK")
    ap.add_argument("--preview-briefing", metavar="FILE", help="write a briefing preview to FILE and change nothing else")
    a = ap.parse_args()

    ed = json.load(open(os.path.join(ROOT, "edition.json"), encoding="utf-8"))
    if a.preview_briefing:
        b = briefing(ed, NOW)
        open(a.preview_briefing, "w", encoding="utf-8").write(briefing_page(b).replace('href="/assets/page.css"', f'href="file://{ROOT}/assets/page.css"'))
        print("preview written"); return

    # owner's source and copyright policy (tools/policy.py): no features, link-only outlets,
    # single-source length cap, opt-outs. publish.py applies it to edition.json too.
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import policy
    policy.apply(ed)

    changed = 0
    arch_path = os.path.join(ROOT, "data", "archive.json")
    archive = json.load(open(arch_path, encoding="utf-8")) if os.path.exists(arch_path) else {}

    # features were removed (owner's decision, Nov 2026): delete any feature pages still online
    for sid in [k for k, v in archive.items() if v.get("sec") == "features"]:
        d = os.path.join(ROOT, "story", sid)
        if os.path.isdir(d):
            shutil.rmtree(d); changed += 1
        archive.pop(sid, None)

    # takedowns: ids listed in tools/takedown.txt are removed everywhere
    tk = os.path.join(ROOT, "tools", "takedown.txt")
    takedown = set()
    if os.path.exists(tk):
        takedown = {l.strip() for l in open(tk, encoding="utf-8") if l.strip() and not l.startswith("#")}
    for sid in takedown:
        d = os.path.join(ROOT, "story", sid)
        if os.path.isdir(d):
            shutil.rmtree(d); changed += 1
        archive.pop(sid, None)

    pick_police(ed)
    pick_sport(ed)
    items = [(s, it) for s, it in collect(ed) if it["id"] not in takedown]
    seen = set()
    top = sorted([(s, it) for s, it in items if s in ("news", "sport")],
                 key=lambda x: (-(x[1].get("weight") or 3), -((parse_t(x[1].get("time")) or NOW).timestamp())))
    for sec, it in items:
        if it["id"] in seen:
            continue
        seen.add(it["id"])
        rel = [x for x in top if x[1]["id"] != it["id"] and set(x[1].get("areas") or []) & (set(it.get("areas") or []) - {"all"})][:3]
        more = rel + [x for x in top if x[1]["id"] != it["id"] and x not in rel][: 6 - len(rel)]
        if sec == "councilwatch":  # other council stories first, and never lead with crime beside a council story
            cws = [x for x in items if x[0] == "councilwatch" and x[1]["id"] != it["id"]][:4]
            calm = [x for x in top if x[1]["id"] != it["id"] and str(x[1].get("tag") or "").lower() not in ("police", "court", "crime")]
            more = cws + calm[: 6 - len(cws)]
        if write(f"story/{it['id']}/index.html", story_page(sec, it, more)):
            changed += 1
        t = parse_t(it.get("time"))
        prev = archive.get(it["id"], {})
        archive[it["id"]] = {
            "h": it["headline"], "sec": sec, "card": card_of(it, sec), "place": it.get("place") or "",
            "t": iso(t) if t else prev.get("t", ""), "u": iso(parse_t(it.get("updated"))) if it.get("updated") else prev.get("u", ""),
            "first": prev.get("first") or iso(NOW), "last": iso(NOW),
        }
        ar = [x for x in (it.get("areas") or []) if isinstance(x, str) and x != "all"]
        if ar:
            archive[it["id"]]["a"] = ar
        elif prev.get("a"):
            archive[it["id"]]["a"] = prev["a"]
        if sec == "councilwatch":
            archive[it["id"]].update({"council": it.get("council") or "", "councilName": it.get("councilName") or "", "cwKey": it.get("cwKey") or ""})

    # about page
    if write("about/index.html", about_page()):
        changed += 1

    # daily briefing
    uk_now = NOW.astimezone(UK)
    day = uk_now.date().isoformat()
    mins = uk_now.hour * 60 + uk_now.minute
    no_brief = os.environ.get("SEAX_NO_BRIEFING") == "1"  # desks other than the newsroom never make the day's briefing
    if not no_brief and (a.briefing_now or 390 <= mins < 720) and not os.path.exists(os.path.join(ROOT, "briefing", day, "index.html")):
        b = briefing(ed, NOW)
        write(f"briefing/{day}/index.html", briefing_page(b))
        bj_path = os.path.join(ROOT, "data", "briefings.json")
        bj = json.load(open(bj_path, encoding="utf-8")) if os.path.exists(bj_path) else []
        lead = b["lead"] or (b["stories"][0] if b["stories"] else None)
        bj = [x for x in bj if x["date"] != day]
        bj.insert(0, {"date": day, "label": b["label"], "made": iso(NOW), "headline": lead["headline"] if lead else "",
                      "html": briefing_html_inner(b, email=True)})
        write("data/briefings.json", json.dumps(bj[:14], ensure_ascii=False, indent=0))
        changed += 1
    bj_path = os.path.join(ROOT, "data", "briefings.json")
    briefs = json.load(open(bj_path, encoding="utf-8")) if os.path.exists(bj_path) else []
    latest = briefs[0]["date"] if briefs else ""
    if latest:
        page = open(os.path.join(ROOT, "briefing", latest, "index.html"), encoding="utf-8").read()
        changed += write("briefing/index.html", page)
    else:
        changed += write("briefing/index.html", head("Essex at 7 · The Seax", "The Seax morning briefing.", f"{SITE}/briefing/", "briefing") +
                         '<main class="wrap prose"><h1>Essex at 7</h1><p class="standfirst">The Seax morning briefing arrives here at about 7am every day: the Essex stories that matter, weather, travel and results.</p><p><a href="/">Read the latest on the front page</a>.</p></main>' + foot() + "</body></html>\n")
    changed += write("briefing.xml", rss("Essex at 7: The Seax morning briefing", f"{SITE}/briefing/",
                                         "The Essex stories that matter, weather, travel and results, every morning.", f"{SITE}/briefing.xml",
                                         [{"title": f"Essex at 7, {x['label']}" + (f": {x['headline']}" if x.get("headline") else ""),
                                           "link": f"{SITE}/briefing/{x['date']}/", "date": parse_t(x["made"]),
                                           "desc": f"The Seax morning briefing for {x['label']}.", "html": x["html"]} for x in briefs]))

    # archive file
    changed += write("data/archive.json", json.dumps(archive, ensure_ascii=False, sort_keys=True, indent=0))

    # Council Watch hub and council pages
    cw_urls, cw_changed = cw_pages(ed, archive)
    changed += cw_changed

    # local news pages, one per area
    area_urls, area_changed = area_pages(archive)
    changed += area_changed

    # RSS of latest stories
    feed_items = []
    for sec, it in sorted([x for x in items if x[0] in ("news", "sport", "courts", "official", "community", "councilwatch")],
                          key=lambda x: (parse_t(x[1].get("time")) or NOW - timedelta(days=30)), reverse=True)[:60]:
        u = f"{SITE}/story/{it['id']}/"
        feed_items.append({"title": it["headline"], "link": u, "date": parse_t(it.get("time")),
                           "cat": SECTION_LABEL.get(sec), "desc": it.get("summary") or it["headline"]})
    changed += write("feed.xml", rss("The Seax: Essex news, sport and life", SITE + "/",
                                     "The latest Essex news, sport and life, updated through the day.", f"{SITE}/feed.xml", feed_items))

    # sitemaps
    def lastmod(rec):
        return (rec.get("u") or rec.get("t") or rec.get("last") or iso(NOW))[:10]
    urls = [(SITE + "/", NOW.date().isoformat(), "hourly", "1.0"), (SITE + "/about/", None, "monthly", "0.4"),
            (SITE + "/briefing/", latest or None, "daily", "0.7"),
            (SITE + "/story/the-seax-launches/", "2026-11-09", None, "0.5")]  # owner's launch story, kept findable
    for sid, rec in sorted(archive.items(), key=lambda kv: kv[1].get("t") or kv[1].get("first") or "", reverse=True):
        urls.append((f"{SITE}/story/{sid}/", lastmod(rec), None, None))
    for x in briefs:
        urls.append((f"{SITE}/briefing/{x['date']}/", x["date"], None, None))
    for u, lm in area_urls:
        urls.append((u, lm, "hourly", "0.8"))
    for u, lm in cw_urls:
        urls.append((u, lm, "daily" if u.endswith("/council-watch/") else None, "0.7" if u.endswith("/council-watch/") else None))
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, lm, cf, pr in urls:
        sm.append("<url><loc>" + E(loc) + "</loc>" + (f"<lastmod>{lm}</lastmod>" if lm else "") +
                  (f"<changefreq>{cf}</changefreq>" if cf else "") + (f"<priority>{pr}</priority>" if pr else "") + "</url>")
    sm.append("</urlset>\n")
    changed += write("sitemap.xml", "\n".join(sm))
    ns = ['<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">']
    for sid, rec in archive.items():
        t = parse_t(rec.get("t"))
        if t and t >= NOW - timedelta(hours=48) and rec.get("sec") != "features":
            ns.append(f"<url><loc>{SITE}/story/{sid}/</loc><news:news><news:publication><news:name>The Seax</news:name>"
                      f"<news:language>en</news:language></news:publication><news:publication_date>{iso(t)}</news:publication_date>"
                      f"<news:title>{E(rec['h'])}</news:title></news:news></url>")
    ns.append("</urlset>\n")
    changed += write("news-sitemap.xml", "\n".join(ns))

    changed += bool(patch_index(latest))
    print(f"build: {len(seen)} story pages from this edition, {len(archive)} in archive, {len(briefs)} briefings, {changed} files changed")

if __name__ == "__main__":
    main()
