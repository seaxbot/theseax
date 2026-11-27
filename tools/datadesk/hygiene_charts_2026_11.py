# Reference chart script for the 27 Nov 2026 hygiene weekend feature (grid of 100, shaded Essex map, dot pairs).
# Run from the repo root. Reuse its map and grid code for future weekend features (ops/weekend.md).
import json, re, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import PathPatch, Rectangle, Patch
from matplotlib.path import Path
from matplotlib import font_manager as fm
for f in fm.findSystemFonts():
    if "Inter" in f: fm.fontManager.addfont(f)
plt.rcParams["font.family"] = "Inter"
D = json.load(open("data/hygiene/essex-2026-11.json")); A = D["areas"]; E = D["essex"]
BG = "#fbfbf9"; INK = "#1a1a1a"; MUTE = "#666"
SEQ = ["#e3f1e7", "#b5dcc0", "#7fbf93", "#3f9a63", "#1e6b45"]
RED = "#c8102e"
SRC = "Source: The Seax analysis of Food Standards Agency hygiene ratings for Essex's 14 councils, 27 November 2026, Open Government Licence"
def frame(title, sub, size=(16, 10.6)):
    fig = plt.figure(figsize=size, dpi=100); fig.patch.set_facecolor(BG)
    fig.text(0.035, 0.925, title, fontsize=30, fontweight="bold", color="#111")
    fig.text(0.035, 0.875, sub, fontsize=17, color="#555")
    fig.text(0.035, 0.03, SRC, fontsize=11.5, color="#888")
    return fig

# ---- 1. Waffle: out of every 100
def per100(m, keys):
    n = sum(m.values()); raw = [m[k] * 100 / n for k in keys]
    fl = [int(x) for x in raw]; rem = 100 - sum(fl)
    for i in sorted(range(len(raw)), key=lambda i: -(raw[i] - fl[i]))[:rem]: fl[i] += 1
    return fl
def bands(mix):
    return {"5": mix["5"], "4": mix["4"], "3": mix["3"], "low": mix["2"] + mix["1"] + mix["0"]}
BT = D["byType"]
groups = [("Takeaways and sandwich shops", bands(BT["Takeaway/sandwich shop"]["mix"])),
          ("Restaurants and cafes", bands(BT["Restaurant/Cafe/Canteen"]["mix"]))]
cols = {"5": SEQ[4], "4": SEQ[2], "3": SEQ[1], "low": RED}
labs = {"5": "Rated 5, very good", "4": "Rated 4, good", "3": "Rated 3, generally satisfactory", "low": "Rated 2 or below"}
fig = frame("Out of every 100 takeaways, 33 miss the top rating", "How Essex takeaways compare with restaurants and cafes, each square one in every hundred rated places")
for gi, (name, m) in enumerate(groups):
    keys = ["5", "4", "3", "low"]; cnt = per100(m, keys)
    seq = [k for k, c in zip(keys, cnt) for _ in range(c)]
    ax = fig.add_axes([0.06 + gi * 0.46, 0.2, 0.38, 0.58]); ax.set_facecolor(BG)
    for i, k in enumerate(seq):
        col, row = i % 10, i // 10
        ax.add_patch(Rectangle((col, 9 - row), 0.86, 0.86, color=cols[k], lw=0))
    ax.set_xlim(-0.1, 10); ax.set_ylim(-0.1, 10); ax.set_aspect("equal"); ax.axis("off")
    fig.text(0.06 + gi * 0.46, 0.80, name, fontsize=19, fontweight="bold", color=INK)
    fig.text(0.06 + gi * 0.46, 0.155, "  ·  ".join(f"{c} {lab}" for c, lab in zip(cnt, ["rated 5", "rated 4", "rated 3", "rated 2 or below"])), fontsize=14.5, color=INK)
fig.legend(handles=[Patch(color=cols[k], label=labs[k]) for k in ["5", "4", "3", "low"]], loc="lower left", bbox_to_anchor=(0.05, 0.065), ncol=4, frameon=False, fontsize=14)
fig.savefig("essex-hygiene-waffle-takeaways-restaurants-2026-11.png", facecolor=BG); plt.close(fig)

# ---- 2. Map: takeaways rated 5 by council area
src = open("index.html", encoding="utf-8").read()
M = json.loads(re.search(r"^const ESSEX_MAP = (.*?);\s*$", src, re.M).group(1))
NM = {"Southend-on-Sea": "Southend"}
def path_of(d):
    verts, codes = [], []
    for cmd, xs, ys in re.findall(r"([MLZ])\s*(-?[\d.]+)?\s*(-?[\d.]+)?", d):
        if cmd == "Z": verts.append(verts[-1] if verts else (0, 0)); codes.append(Path.CLOSEPOLY)
        else: verts.append((float(xs), float(ys))); codes.append(Path.MOVETO if cmd == "M" else Path.LINETO)
    return Path(verts, codes)
bins = [(0, 50, "Under 50%"), (50, 65, "50 to 64%"), (65, 75, "65 to 74%"), (75, 85, "75 to 84%"), (85, 101, "85% or more")]
def colour(p):
    for i, (lo, hi, _) in enumerate(bins):
        if lo <= p < hi: return SEQ[i]
fig = frame("Takeaway hygiene, mapped", "Share of each council area's rated takeaways and sandwich shops with the top food hygiene rating of 5", size=(16, 13))
ax = fig.add_axes([0.03, 0.15, 0.94, 0.70]); ax.set_facecolor(BG)
cent = M.get("centroids", {})
for dn, d in M["districts"].items():
    nm = NM.get(dn, dn); a = A[nm]; p = a["twMix"]["5"] / a["twRated"] * 100
    ax.add_patch(PathPatch(path_of(d), facecolor=colour(p), edgecolor=BG, lw=2.2))
xs = []; ys = []
for dn, d in M["districts"].items():
    for x, y in re.findall(r"(-?[\d.]+)\s+(-?[\d.]+)", d): xs.append(float(x)); ys.append(float(y))
ax.set_xlim(min(xs) - 10, max(xs) + 10); ax.set_ylim(max(ys) + 10, min(ys) - 10); ax.set_aspect("equal"); ax.axis("off")
OFF = {"Castle Point": (0, 0), "Southend-on-Sea": (14, 12), "Rochford": (10, -16), "Harlow": (0, -6), "Brentwood": (0, 0), "Maldon": (-25, 52)}
for dn in M["districts"]:
    nm = NM.get(dn, dn); a = A[nm]; p = a["twMix"]["5"] / a["twRated"] * 100
    c = cent.get(dn)
    if not c: continue
    cx, cy = (c[0], c[1]) if isinstance(c, list) else (c["x"], c["y"])
    dx, dy = OFF.get(dn, (0, 0)); dark = colour(p) in SEQ[3:]
    if dn == "Castle Point":   # too small to hold a label: put it in the estuary with a leader line
        ax.annotate(f"Castle Point\n{p:.0f}%", xy=(cx, cy), xytext=(cx + 70, cy + 58), ha="center", va="center", fontsize=12.5, fontweight="bold", color=INK,
                    arrowprops=dict(arrowstyle="-", color="#555", lw=1.2), linespacing=1.15)
        continue
    ax.text(cx + dx, cy + dy, f"{nm}\n{p:.0f}%", ha="center", va="center", fontsize=13 if nm not in ("Harlow", "Castle Point", "Southend") else 11.5,
            fontweight="bold", color="#fff" if dark else INK, linespacing=1.15)
fig.legend(handles=[Patch(color=SEQ[i], label=b[2]) for i, b in enumerate(bins)], loc="lower left", bbox_to_anchor=(0.05, 0.06), ncol=5, frameon=False, fontsize=14,
           title=f"Takeaways rated 5 (Essex {E['twMix']['5'] / E['twRated'] * 100:.0f}%)", title_fontsize=14)
fig.savefig("essex-hygiene-map-takeaways-2026-11.png", facecolor=BG); plt.close(fig)

# ---- 3. Dumbbell: all places to eat v takeaways, by area
rows = sorted(((n, a["eatMix"]["5"] / a["eatRated"] * 100, a["twMix"]["5"] / a["twRated"] * 100) for n, a in A.items()), key=lambda r: r[1])
fig = frame("In every area, takeaways trail the rest", "Share rated 5 for food hygiene: all places to eat out compared with takeaways and sandwich shops, by council area")
ax = fig.add_axes([0.17, 0.12, 0.76, 0.7]); ax.set_facecolor(BG)
DARK, LIGHT = SEQ[4], SEQ[2]
for i, (n, e, t) in enumerate(rows):
    ax.plot([t, e], [i, i], color="#cfcfcf", lw=3, zorder=1, solid_capstyle="round")
    ax.scatter([e], [i], s=170, color=DARK, zorder=3, edgecolor=BG, linewidth=2)
    ax.scatter([t], [i], s=170, color=LIGHT, zorder=3, edgecolor=BG, linewidth=2)
    ax.text(e + 1.4, i, f"{e:.0f}%", va="center", fontsize=12.5, color=INK)
    ax.text(t - 1.4, i, f"{t:.0f}%", va="center", ha="right", fontsize=12.5, color=MUTE)
ax.set_yticks(range(len(rows))); ax.set_yticklabels([r[0] for r in rows], fontsize=16)
ax.set_xlim(35, 100); ax.set_xticks([40, 50, 60, 70, 80, 90, 100]); ax.set_xticklabels([f"{v}%" for v in [40, 50, 60, 70, 80, 90, 100]], fontsize=13, color=MUTE)
ax.grid(axis="x", color="#e6e6e6", lw=1); ax.set_axisbelow(True)
[s.set_visible(False) for s in ax.spines.values()]; ax.tick_params(length=0, pad=10)
fig.legend(handles=[plt.Line2D([], [], marker="o", ls="", ms=13, color=DARK, label="All places to eat out"),
                    plt.Line2D([], [], marker="o", ls="", ms=13, color=LIGHT, label="Takeaways and sandwich shops")],
           loc="upper left", bbox_to_anchor=(0.03, 0.865), ncol=2, frameon=False, fontsize=14.5)
fig.savefig("essex-hygiene-dumbbell-areas-2026-11.png", facecolor=BG); plt.close(fig)
print("done", type(cent), list(cent.items())[:2] if isinstance(cent, dict) else cent[:2])
