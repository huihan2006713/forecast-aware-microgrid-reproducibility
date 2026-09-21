# -*- coding: utf-8 -*-
"""D3 日前 α 敏感性：α∈{0.80,0.85,0.90} 的 1 月校准（1/22–31）与 334 天评估。"""
import json
import time as _time
from pathlib import Path
import dayahead as da

RESULTS = Path(__file__).resolve().parents[1] / "results"
RESULTS.mkdir(exist_ok=True)

if __name__ == "__main__":
    da.set_warmup_resid(False)
    da.set_cfg(model="e", second=True)
    da.set_load_variant("incl_d7")
    da.set_window(28)
    out = {}
    for alpha in (0.80, 0.85, 0.90):
        t0 = _time.time()
        Jp_jan, Je_jan, _, cov_jan = da.run_policy(alpha, True, "jan", "linear",
                                                   eval_start=21, eval_end=31)
        Jp, Je, daily, cov = da.run_policy(alpha, True, "eval", "linear",
                                           eval_start=31, eval_end=365)
        out[str(alpha)] = dict(
            jan_total=round(Jp_jan + Je_jan, 2), jan_plan=round(Jp_jan, 2),
            jan_emerg=round(Je_jan, 2),
            eval_total=round(Jp + Je, 2), eval_plan=round(Jp, 2), eval_emerg=round(Je, 2),
            coverage=round(cov, 4), wall_s=round(_time.time() - t0, 1))
        print(f"α={alpha} 1月 {Jp_jan+Je_jan:>12.2f} (计划 {Jp_jan:.2f} 应急 {Je_jan:.2f})"
              f" | 334天 {Jp+Je:>14.2f} (计划 {Jp:.2f} 应急 {Je:.2f})"
              f" 覆盖 {cov*100:.2f}% 用时 {_time.time()-t0:.0f}s", flush=True)
    with open(RESULTS / "da_alpha_sweep.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
