# -*- coding: utf-8 -*-
"""D3 κ敏感性：κ_up ∈ {1.25,1.5,1.75} × κ_dn ∈ {−0.25,−0.5,−0.75}，
风险修正族 4 日程 × 334 天。逐日因果；0:00 计划与 κ 无关（跨 κ 缓存）。"""
import json
import itertools
import time as _time
from pathlib import Path
import numpy as np
import pandas as pd
import revision as rv

OUT = Path(__file__).resolve().parents[1] / "results"
OUT.mkdir(exist_ok=True)
K_UPS = (1.25, 1.5, 1.75)
K_DNS = (-0.25, -0.5, -0.75)

# 0:00 计划缓存（α=0.85 固定，与 κ 无关）
plan_cache = {}
orig_solve_plan = rv.solve_plan


def cached_plan(d, n_risk):
    key = (d, np.round(n_risk, 10).tobytes())
    if key not in plan_cache:
        plan_cache[key] = orig_solve_plan(d, n_risk)
    return plan_cache[key]


rv.solve_plan = cached_plan

libs = {r: [] for r in range(4)}
rows = []
t_start = _time.time()
for d in range(rv.NDAYS):
    if d >= 31:
        for ku, kd in itertools.product(K_UPS, K_DNS):
            rv.set_kappa(ku, kd)
            res = rv.run_day_4(d, True, libs)
            for sched, rec in res.items():
                rows.append(dict(k_up=ku, k_dn=kd, schedule=sched, **rec))
    if d >= 7:
        for r in range(4):
            F = np.nan_to_num(rv.F4[d, r], nan=0.0)
            pred_l = rv.predict_load_hist(d)
            res = rv.load[d] - rv.pv[d] - (pred_l - F)
            res[: (r if r > 0 else 0)] = 0.0
            libs[r].append(res)
    if (d + 1) % 30 == 0:
        print(f"  进度 {d+1}/{rv.NDAYS}", flush=True)

summary = {}
for ku, kd in itertools.product(K_UPS, K_DNS):
    for sched in ("none", "06", "0612", "061218"):
        rs = [x for x in rows if x["k_up"] == ku and x["k_dn"] == kd
              and x["schedule"] == sched]
        summary[f"{ku}|{kd}|{sched}"] = dict(
            total=round(sum(x["J"] for x in rs), 2),
            J_rev=round(sum(x["J_rev"] for x in rs), 2),
            J_emerg=round(sum(x["J_emerg"] for x in rs), 2))
pd.DataFrame(rows).to_csv(OUT / "sensitivity_kappa_daily.csv", index=False)
with open(OUT / "sensitivity_kappa.json", "w", encoding="utf-8") as fh:
    json.dump(summary, fh, indent=2)
print("\nκ 敏感性汇总（total）:")
for k, v in summary.items():
    print(f"  {k:24s} {v['total']:>14.2f}")
print("总用时 %.0f s，MILP 调用 %d" % (_time.time() - t_start, len(rv.solve_times)))
