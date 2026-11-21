"""Recount for the Essex oysters story (owner's Seax Investigates story, 22 Nov 2026).
Counts the Essex harvesting zones graded for oysters (O. edulis, C. gigas) in the Food Standards Agency's list
(data/sources/fsa-shellfish-classification-2026-10-01.xlsx, from GOV.UK 'Shellfish classification', updated 1 October 2026)
and prints the figures the story uses. Exits 1 if any figure differs from the story."""
import openpyxl, collections, sys
wb = openpyxl.load_workbook("data/sources/fsa-shellfish-classification-2026-10-01.xlsx", read_only=True, data_only=True)
rows = list(wb.worksheets[0].iter_rows(values_only=True))
AREAS = {"Blackwater", "Colne", "Crouch", "Roach", "West Mersea", "Walton Backwaters", "Thames Estuary"}
KENT = ("Sheppey", "Cant", "Scrapsgate")
zones = collections.OrderedDict()
for r in rows:
    if r and r[0] == "Production" and r[1] in AREAS and not any(k in (r[2] or "") for k in KENT) and str(r[3]).strip() in ("O. edulis", "C. gigas"):
        zones.setdefault((r[1], " ".join(str(r[2]).split())), set()).add(str(r[4]).strip())
def grade(v):
    s = " ".join(sorted(v))
    return "A" if s == "A" else ("seasonal" if s == "Seasonal A/B" else "B")
tot = collections.Counter(grade(v) for v in zones.values())
by = collections.defaultdict(collections.Counter)
for (a, z), v in zones.items():
    by[a][grade(v)] += 1
print(len(zones), dict(tot)); [print(a, dict(c)) for a, c in by.items()]
want = {"total": 33, "B": 27, "seasonal": 2, "A": 4, "West Mersea": (6, 1, 0), "Blackwater": (3, 1, 3), "Colne": (3, 0, 0),
        "Crouch": (5, 0, 0), "Roach": (5, 0, 0), "Walton Backwaters": (3, 0, 0), "Thames Estuary": (2, 0, 1)}
ok = len(zones) == want["total"] and tot["B"] == want["B"] and tot["seasonal"] == want["seasonal"] and tot["A"] == want["A"]
for a in AREAS:
    ok &= (by[a]["B"], by[a]["seasonal"], by[a]["A"]) == want[a]
print("RECOUNT OK" if ok else "RECOUNT MISMATCH"); sys.exit(0 if ok else 1)
