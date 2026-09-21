# -*- coding: utf-8 -*-
"""D3 α敏感性：α ∈ {0.80,0.85,0.90}，风险修正族 4 日程 × 334 天。
逐日因果：残差库随天数推进，只含已完成日（d<当天且 d≥7）。"""
import json
import time as _time
from pathlib import Path
import numpy as np
import pandas as pd
import revision as rv

OUT = Path(__file__).resolve().parents[1] / "results"
OUT.mkdir(exist_ok=True)
ALPHAS = (0.80, 0.85, 0.90)
libs = {r: [] for r in range(4)}
rows = []
t_start = _time.time()
for d in range(rv.NDAYS):
    if d >= 31:
        for alpha in ALPHAS:
            rv.set_alpha(alpha)
            res = rv.run_day_4(d, True, libs)
            for sched, rec in res.items():
                rows.append(dict(alpha=alpha, schedule=sched, **rec))
    if d >= 7:
        for r in range(4):
            F = np.nan_to_num(rv.F4[d, r], nan=0.0)
            pred_l = rv.predict_load_hist(d)
            res = rv.load[d] - rv.pv[d] - (pred_l - F)
            res[: (r if r > 0 else 0)] = 0.0
            libs[r].append(res)
    if (d + 1) % 60 == 0:
        print(f"  进度 {d+1}/{rv.NDAYS}", flush=True)

summary = {}
for alpha in ALPHAS:
    for sched in ("none", "06", "0612", "061218"):
        rs = [x for x in rows if x["alpha"] == alpha and x["schedule"] == sched]
        summary[f"{alpha}|{sched}"] = dict(
            total=round(sum(x["J"] for x in rs), 2),
            J_rev=round(sum(x["J_rev"] for x in rs), 2),
            J_emerg=round(sum(x["J_emerg"] for x in rs), 2))
pd.DataFrame(rows).to_csv(OUT / "sensitivity_alpha_daily.csv", index=False)
with open(OUT / "sensitivity_alpha.json", "w", encoding="utf-8") as fh:
    json.dump(summary, fh, indent=2)
print("\nα 敏感性汇总（total）:")
for k, v in summary.items():
    print(f"  {k:16s} {v['total']:>14.2f}")
print("总用时 %.0f s" % (_time.time() - t_start))
