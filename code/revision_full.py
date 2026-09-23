# -*- coding: utf-8 -*-
"""阶段C/D：修订管线全量 334 天运行（两个族 × 4 日程），逐日 CSV、汇总 JSON、
求解统计与环境信息。"""
import json
import platform
import time as _time
from pathlib import Path
import numpy as np
import pandas as pd
import scipy
import revision as rv


def cpu_model():
    value = platform.processor()
    if value and value.lower() not in {"x86_64", "amd64"}:
        return value
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.lower().startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return value or "unknown"

OUT = Path(__file__).resolve().parents[1] / "results"
OUT.mkdir(exist_ok=True)
runs = {}
daily_all = []
t_start = _time.time()

for fam, risk in (("ra", True), ("pt", False)):
    t0 = _time.time()
    recs = rv.run_window_4(list(range(31, rv.NDAYS)), risk)
    el = _time.time() - t0
    for sched, rs in recs.items():
        tot = sum(x["J"] for x in rs)
        runs[f"{fam}|{sched}"] = dict(
            total=round(tot, 2),
            J_plan=round(sum(x["J_plan"] for x in rs), 2),
            J_rev=round(sum(x["J_rev"] for x in rs), 2),
            J_emerg=round(sum(x["J_emerg"] for x in rs), 2),
            e_kWh=round(sum(x["e_kWh"] for x in rs), 2),
            a_up_kWh=round(sum(x["a_up_kWh"] for x in rs), 2),
            wall_s=round(el, 1))
        daily_all += [dict(family=fam, schedule=sched, **x) for x in rs]
        print(f"{fam} {sched:8s} 总计 {tot:>14.2f} 计划 {sum(x['J_plan'] for x in rs):>13.2f} "
              f"调整 {sum(x['J_rev'] for x in rs):>11.2f} 应急 {sum(x['J_emerg'] for x in rs):>11.2f} "
              f"用时 {el:.0f}s", flush=True)

pd.DataFrame(daily_all).to_csv(OUT / "revision_daily.csv", index=False)
with open(OUT / "revision_summary.json", "w", encoding="utf-8") as fh:
    json.dump(runs, fh, indent=2)

times = np.array(rv.solve_times)
stats = dict(
    n_calls=int(len(times)),
    median_s=float(np.median(times)),
    p95_s=float(np.percentile(times, 95)),
    max_s=float(times.max()),
    n_over_30s=int((times >= 30.0 - 1e-9).sum()),
    total_wall_s=float(_time.time() - t_start),
)
print("\n求解统计:", json.dumps(stats, indent=2), flush=True)
with open(OUT / "solve_stats.json", "w", encoding="utf-8") as fh:
    json.dump(stats, fh, indent=2)

try:
    from scipy.optimize._highspy import _core as highs_core
    highs_ver = ".".join(str(x) for x in (
        highs_core.HIGHS_VERSION_MAJOR,
        highs_core.HIGHS_VERSION_MINOR,
        highs_core.HIGHS_VERSION_PATCH,
    ))
except Exception:
    highs_ver = "unknown"
env = dict(
    platform=platform.platform(),
    machine=platform.machine(),
    cpu=cpu_model(),
    python=platform.python_version(),
    numpy=np.__version__,
    pandas=pd.__version__,
    scipy=scipy.__version__,
    highs=highs_ver,
    eps_tol=rv.EPS_TOL,
    mip_gap=rv.MIP_GAP,
    time_limit=rv.TIME_LIMIT,
    alpha=rv.ALPHA,
)
with open(OUT / "environment.json", "w", encoding="utf-8") as fh:
    json.dump(env, fh, indent=2)
print("\n环境:", json.dumps(env, indent=2))
print("全部完成，总用时 %.0f s" % (_time.time() - t_start))
