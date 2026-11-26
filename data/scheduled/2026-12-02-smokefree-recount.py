"""Recount for the owner's smokefree generation story (scheduled for Wed 2 Dec 2026). Exits 1 if the copy and the raw ONS file disagree.
Raw file: data/sources/ons-cigarette-smokers-2021-25-essex.csv (ONS Explore Local Statistics, cigarette smokers, 2021-2025 five-year average)."""
import csv, json, sys
rows = {r["areanm"]: r for r in csv.DictReader(open("data/sources/ons-cigarette-smokers-2021-25-essex.csv"))}
eng = float(rows.pop("England")["value"])
v = {k: float(r["value"]) for k, r in rows.items()}
it = json.load(open("data/scheduled/2026-12-02-smokefree-generation.json"))["items"][0]
text = " ".join(it["body"])
ok = True
def need(cond, msg):
    global ok
    print(("OK  " if cond else "BAD ") + msg); ok &= bool(cond)
s = sorted(v.items(), key=lambda x: -x[1])
need(len(v) == 14, "14 Essex council areas")
need(eng == 10.9 and "England average of 10.9%" in text, "England 10.9%")
above = [k for k, x in v.items() if x > eng]
need(len(above) == 5 and "five Essex council areas were above" in text, f"five above England: {above}")
need(s[0][1] == s[1][1] == 13.4 and {s[0][0], s[1][0]} == {"Basildon", "Thurrock"} and "Basildon and Thurrock had the highest rates, both 13.4%" in text, "Basildon and Thurrock highest, 13.4%")
need(s[2] == ("Tendring", 13.3) and "Tendring on 13.3%" in text, "Tendring 13.3% third")
need(s[3] == ("Harlow", 13.0) and "Harlow on 13%" in text, "Harlow 13% fourth")
need(s[4] == ("Uttlesford", 11.9) and "Uttlesford on 11.9%" in text, "Uttlesford 11.9% fifth")
need(s[-1] == ("Rochford", 4.8) and "Rochford had the lowest rate in Essex, at 4.8%" in text, "Rochford lowest 4.8%")
need(s[-2] == ("Maldon", 7.1) and s[-3] == ("Brentwood", 7.3) and "Maldon on 7.1% and Brentwood on 7.3%" in text, "Maldon then Brentwood next lowest")
h = rows["Harlow"]
need(h["lci_95"] == "8" and h["uci_95"] == "17.9" and "between 8% and 17.9%" in text, "Harlow margin 8 to 17.9")
for c in json.load(open("data/scheduled/2026-12-02-smokefree-generation.json"))["items"][0]["charts"]:
    need(all(f"{n} {x:.1f}%" in c["alt"] for n, x in v.items()), "chart alt text matches every area")
sys.exit(0 if ok else 1)
