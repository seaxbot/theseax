#!/usr/bin/env python3
"""Town coverage check (20 Nov 2026): which Essex towns has The Seax not covered lately?

Reads data/archive.json (every story the site has run) and prints, for each town on the watch list, how many stories
named it in the last 7 days and when it was last covered, then the towns most overdue with a search to try.
The newsroom runs it three times a day (ops/newsroom.md, 3c TOWN BLIND SPOTS). No web requests, no tokens.

  python3 tools/coverage.py          the most overdue towns (short)
  python3 tools/coverage.py --all    every town with its count
"""
import json, os, re, sys
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = datetime.now(timezone.utc)
# town, district, other names that count as the town; ordered roughly by population so bigger gaps come first
TOWNS = [
    ("Southend", "Southend", ["westcliff", "prittlewell", "thorpe bay", "southchurch"]), ("Colchester", "Colchester", ["stanway", "lexden", "greenstead", "highwoods"]),
    ("Chelmsford", "Chelmsford", ["springfield", "moulsham", "chelmer village"]), ("Basildon", "Basildon", ["pitsea", "laindon", "vange"]),
    ("Harlow", "Harlow", []), ("Grays", "Thurrock", ["chafford hundred", "little thurrock"]), ("Brentwood", "Brentwood", ["warley", "pilgrims hatch"]),
    ("Clacton", "Tendring", ["jaywick", "holland-on-sea"]), ("Braintree", "Braintree", ["great notley", "bocking"]),
    ("Canvey Island", "Castle Point", ["canvey"]), ("Rayleigh", "Rochford", []), ("Billericay", "Basildon", []), ("Wickford", "Basildon", []),
    ("Loughton", "Epping Forest", ["debden"]), ("Witham", "Braintree", []), ("Benfleet", "Castle Point", ["thundersley", "hadleigh"]),
    ("Maldon", "Maldon", ["heybridge"]), ("South Ockendon", "Thurrock", ["aveley", "purfleet"]), ("Stanford-le-Hope", "Thurrock", ["corringham"]),
    ("Leigh-on-Sea", "Southend", ["leigh on sea"]), ("Waltham Abbey", "Epping Forest", []), ("Tilbury", "Thurrock", []),
    ("Harwich", "Tendring", ["dovercourt"]), ("Saffron Walden", "Uttlesford", []), ("South Woodham Ferrers", "Chelmsford", ["south woodham"]),
    ("Shoeburyness", "Southend", ["shoebury"]), ("Hockley", "Rochford", ["hullbridge"]), ("Rochford", "Rochford", ["great wakering"]),
    ("Epping", "Epping Forest", ["theydon bois", "north weald"]), ("Halstead", "Braintree", ["sible hedingham"]), ("Great Dunmow", "Uttlesford", ["dunmow"]),
    ("Chigwell", "Epping Forest", []), ("Buckhurst Hill", "Epping Forest", []), ("Frinton and Walton", "Tendring", ["frinton", "walton-on-the-naze", "walton on the naze"]),
    ("Tiptree", "Colchester", []), ("Brightlingsea", "Tendring", []), ("Burnham-on-Crouch", "Maldon", ["burnham on crouch", "southminster"]),
    ("Wivenhoe", "Colchester", []), ("West Mersea", "Colchester", ["mersea"]), ("Stansted Mountfitchet", "Uttlesford", ["stansted"]),
    ("Ongar", "Epping Forest", ["chipping ongar"]), ("Great Baddow", "Chelmsford", []), ("Shenfield", "Brentwood", ["hutton"]),
    ("Ingatestone", "Brentwood", []), ("Coggeshall", "Braintree", ["kelvedon"]), ("Manningtree", "Tendring", ["mistley", "lawford"]),
    ("Writtle", "Chelmsford", []), ("Thaxted", "Uttlesford", []), ("Tollesbury", "Maldon", ["tiptree heath"]), ("West Hanningfield", "Chelmsford", ["hanningfield"]),
]


def main():
    arc = json.load(open(os.path.join(ROOT, "data", "archive.json"), encoding="utf-8"))
    cut = (NOW - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = []
    for i, (town, district, alts) in enumerate(TOWNS):
        rx = re.compile(r"\b(" + "|".join(re.escape(x) for x in [town.lower()] + alts) + r")\b", re.I)
        hits = [r for r in arc.values() if rx.search(str(r.get("place") or "") + " " + str(r.get("h") or ""))]
        recent = [r for r in hits if (r.get("first") or r.get("t") or "") >= cut]
        last = max([(r.get("first") or r.get("t") or "") for r in hits], default="")
        rows.append((town, district, len(recent), last[:10], i))
    if "--all" in sys.argv:
        for town, district, n, last, _ in rows:
            print(f"{n:3d} in 7 days | last {last or 'never'} | {town} ({district})")
        return
    gaps = sorted([r for r in rows if r[2] == 0], key=lambda r: (r[3] or "0", r[4]))
    thin = sorted([r for r in rows if r[2] == 1], key=lambda r: r[4])
    print(f"TOWN BLIND SPOTS: {len(gaps)} of {len(rows)} watched towns have had no story in 7 days.")
    for town, district, n, last, _ in gaps[:8]:
        print(f"- {town} ({district}): last covered {last or 'never'} | try: \"{town} news this week\" or \"{town} council OR police OR school OR planning\"")
    if thin:
        print("One story only in 7 days: " + ", ".join(r[0] for r in thin[:12]))


if __name__ == "__main__":
    main()
