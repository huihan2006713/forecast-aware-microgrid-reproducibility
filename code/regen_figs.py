# -*- coding: utf-8 -*-
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
OUT = ROOT / "figures"
OUT.mkdir(exist_ok=True)

C_PLAN = "#4C72B0"
C_REV = "#DD8452"
C_EMERG = "#C44E52"
C_NET = "#55A868"
plt.rcParams.update({"font.size": 10, "axes.spines.top": False,
                     "axes.spines.right": False})

# ---------------- 图 1：1 月校准折线 + 三策略堆叠条形 ----------------
with open(RESULTS / "jan_all_alpha.json", encoding="utf-8") as fh:
    jan = json.load(fh)
alphas = [0.50, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90]
vals = [jan[str(a)]["total"] / 1e3 for a in alphas]

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8.8, 2.55))
ax1.plot(alphas, vals, "o-", color=C_PLAN, lw=1.6, ms=4)
ax1.plot(0.85, jan["0.85"]["total"] / 1e3, "D", color=C_EMERG, ms=6, zorder=5)
ax1.set_xlabel("Residual quantile \u03b1")
ax1.set_ylabel("January validation cost\n(thousand CNY)")
ax1.set_xticks(alphas)
ax1.ticklabel_format(style="plain")

with open(RESULTS / "output_dayahead_final.json", encoding="utf-8") as fh:
    da_fin = json.load(fh)
policies = [("Point", da_fin["point"]["Jp"], da_fin["point"]["Je"],
             da_fin["point"]["total"]),
            ("Median", da_fin["alpha0.50"]["Jp"], da_fin["alpha0.50"]["Je"],
             da_fin["alpha0.50"]["total"]),
            ("Risk adjusted", da_fin["alpha0.85"]["Jp"], da_fin["alpha0.85"]["Je"],
             da_fin["alpha0.85"]["total"])]
names = [p[0] for p in policies]
plan = np.array([p[1] / 1e6 for p in policies])
emerg = np.array([p[2] / 1e6 for p in policies])
tot = np.array([p[3] / 1e6 for p in policies])
y = np.arange(len(policies))[::-1]
b1 = ax2.barh(y, plan, color=C_PLAN, label="Planned")
b2 = ax2.barh(y, emerg, left=plan, color=C_EMERG, label="Emergency")
for yi, t in zip(y, tot):
    ax2.text(t + 0.12, yi, f"{t:.4f}", va="center", fontsize=9)
ax2.set_yticks(y)
ax2.set_yticklabels(names)
ax2.set_xlabel("Evaluation cost (CNY million)")
ax2.set_xlim(0, 19.0)
ax2.legend(loc="upper center", ncol=2, frameon=False, fontsize=8,
           bbox_to_anchor=(0.5, 1.18))
fig.tight_layout()
fig.savefig(OUT / "risk_results.png", dpi=220)
plt.close(fig)
print("图1 完成")

# ---------------- 图 2：两发布成本 + 18:00 增量分解 ----------------
with open(RESULTS / "revision_summary.json", encoding="utf-8") as fh:
    rev = json.load(fh)
pt = (rev["pt|0612"]["J_plan"], rev["pt|0612"]["J_rev"], rev["pt|0612"]["J_emerg"])
ra = (rev["ra|0612"]["J_plan"], rev["ra|0612"]["J_rev"], rev["ra|0612"]["J_emerg"])
d_rev = round(rev["ra|061218"]["J_rev"] - rev["ra|0612"]["J_rev"], 2)
d_em = round(rev["ra|061218"]["J_emerg"] - rev["ra|0612"]["J_emerg"], 2)
d_tot = round(rev["ra|061218"]["total"] - rev["ra|0612"]["total"], 2)

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8.8, 2.55))
x = np.array([0, 1])
p_plan = np.array([pt[0], ra[0]]) / 1e6
p_rev = np.array([pt[1], ra[1]]) / 1e6
p_em = np.array([pt[2], ra[2]]) / 1e6
w = 0.55
b1 = ax1.bar(x, p_plan, w, color=C_PLAN, label="Planned")
b2 = ax1.bar(x, p_rev, w, bottom=p_plan, color=C_REV, label="Revision")
b3 = ax1.bar(x, p_em, w, bottom=p_plan + p_rev, color=C_EMERG, label="Emergency")
for xi, t in zip(x, [sum(pt) / 1e6, sum(ra) / 1e6]):
    ax1.text(xi, t + 0.15, f"{t:.4f}", ha="center", fontsize=9)
ax1.set_xticks(x)
ax1.set_xticklabels(["Point forecast", "Risk adjusted"])
ax1.set_ylabel("Evaluation cost (CNY million)")
ax1.set_ylim(0, 18.5)

labels = ["Revision\ncharges", "Emergency\ncost", "Net\nchange"]
vals = [d_rev, d_em, d_tot]
colors = [C_REV, C_EMERG, C_NET]
bars = ax2.bar(range(3), vals, 0.55, color=colors)
for bi, v in zip(bars, vals):
    ax2.text(bi.get_x() + bi.get_width() / 2, v + (60 if v >= 0 else -140),
             f"{v:+,.2f}", ha="center", fontsize=9)
ax2.axhline(0, color="black", lw=0.8)
ax2.set_xticks(range(3))
ax2.set_xticklabels(labels, fontsize=9)
ax2.set_ylabel("Cost change of adding\n18:00 revision (CNY)")
ax2.set_ylim(-700, 2300)
# 图例放整张图上方中央、三列横排
fig.legend([b1, b2, b3], ["Planned", "Revision", "Emergency"],
           loc="upper center", ncol=3, frameon=False, fontsize=8,
           bbox_to_anchor=(0.5, 1.02))
fig.tight_layout(rect=(0, 0, 1, 0.93))
fig.savefig(OUT / "update_results.png", dpi=220)
plt.close(fig)
print("图2 完成")
