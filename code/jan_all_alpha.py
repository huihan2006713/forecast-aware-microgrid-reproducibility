# -*- coding: utf-8 -*-
"""日前管线 7 个 α 的 1 月 22–31 校准费用（供图 1 重绘）。"""
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
    for alpha in (0.50, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90):
        t0 = _time.time()
        Jp, Je, _, _ = da.run_policy(alpha, True, "jan", "linear",
                                     eval_start=21, eval_end=31)
        out[str(alpha)] = dict(plan=round(Jp, 2), emerg=round(Je, 2),
                               total=round(Jp + Je, 2))
        print(f"α={alpha} 1月 {Jp+Je:>12.2f} (计划 {Jp:.2f} 应急 {Je:.2f}) "
              f"用时 {_time.time()-t0:.0f}s", flush=True)
    with open(RESULTS / "jan_all_alpha.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
