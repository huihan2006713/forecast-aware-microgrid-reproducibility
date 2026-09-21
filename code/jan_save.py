# -*- coding: utf-8 -*-
"""保存 1 月重跑数字（两族 × 4 日程）。"""
import json
from pathlib import Path
import revision as rv

RESULTS = Path(__file__).resolve().parents[1] / "results"
RESULTS.mkdir(exist_ok=True)

out = {}
for fam, risk in (("ra", True), ("pt", False)):
    recs = rv.run_window_4(list(range(21, 31)), risk)
    for sched, rs in recs.items():
        out[f"{fam}|{sched}"] = dict(total=round(sum(x["J"] for x in rs), 2),
                                     J_plan=round(sum(x["J_plan"] for x in rs), 2),
                                     J_rev=round(sum(x["J_rev"] for x in rs), 2),
                                     J_emerg=round(sum(x["J_emerg"] for x in rs), 2))
print(json.dumps(out, indent=2))
with open(RESULTS / "revision_jan.json", "w", encoding="utf-8") as fh:
    json.dump(out, fh, indent=2)
