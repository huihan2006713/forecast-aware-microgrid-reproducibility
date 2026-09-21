# -*- coding: utf-8 -*-
"""两发布策略（06:00+12:00）专属求解统计：334 天 × 3 实例 × 2 次字典序
= 2,004 次 MILP 调用。"""
import json
import numpy as np
from pathlib import Path
import revision as rv

RESULTS = Path(__file__).resolve().parents[1] / "results"
RESULTS.mkdir(exist_ok=True)

rv.solve_times = []          # 清空，只统计本次
libs = {r: [] for r in range(4)}
recs = []
for d in range(rv.NDAYS):
    if d >= 31:
        recs.append(rv.run_day_4(d, True, libs, up_to=2))
    if d >= 7:
        for r in range(4):
            F = np.nan_to_num(rv.F4[d, r], nan=0.0)
            pred_l = rv.predict_load_hist(d)
            res = rv.load[d] - rv.pv[d] - (pred_l - F)
            res[: (r if r > 0 else 0)] = 0.0
            libs[r].append(res)

times = np.array(rv.solve_times)
stats = dict(
    n_calls=int(len(times)),
    median_s=float(np.median(times)),
    p95_s=float(np.percentile(times, 95)),
    p99_s=float(np.percentile(times, 99)),
    max_s=float(times.max()),
    n_over_30s=int((times >= 30.0 - 1e-9).sum()),
)
print("两发布策略求解统计:", json.dumps(stats, indent=2))
with open(RESULTS / "solve_stats_2rel.json", "w", encoding="utf-8") as fh:
    json.dump(stats, fh, indent=2)
