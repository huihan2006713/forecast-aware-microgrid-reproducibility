# -*- coding: utf-8 -*-
"""阶段A：从 C题附件重建处理后的数据 CSV。

输出（mg_repro/data/）：
- q1_processed.csv        附件1 单日分时电价/负载/光伏预测（144 段，右端点 0:10..24:00）
- actual_10min_processed.csv  2025 全年：date, load_kWh, pv_kWh, price_fixed, price_rt
                              （kW 值 /6 换算为 10 分钟电量；price_fixed=附件1 每日重复，
                               price_rt=附件4 实时电价）
- forecast_10min_causal.csv   附件3 小时光伏预报插值到 10 分钟边界（论文 4.1 节方法：
                              以最近完成的实际光伏观测为插值锚点，相邻边界功率平均后
                              换算为区间电量），列 interval_start, pv_forecast_kWh,
                              issue_time
"""
from pathlib import Path
import numpy as np
import pandas as pd
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
ATT = ROOT / "raw_data"
T = 144
H = 1.0 / 6.0  # 每段时长 10 min = 1/6 h

# ---------- 附件1：单日分时电价 ----------
wb = load_workbook(ATT / "附件1.xlsx", read_only=True, data_only=True)
ws = wb["Sheet1"]
rows = list(ws.iter_rows(min_row=2, values_only=True))
wb.close()
times = [r[0] for r in rows]
price1 = np.array([float(r[1]) for r in rows])      # 元/kWh
assert len(price1) == T, f"附件1 行数 {len(price1)} != {T}"
pd.DataFrame({"time": times, "price_yuan_kWh": price1}).to_csv(
    DATA / "q1_processed.csv", index=False)
print("q1_processed.csv:", len(price1), "段, 电价范围", price1.min(), "-", price1.max())

# ---------- 附件2：全年实际负载与光伏（kW → kWh） ----------
wb = load_workbook(ATT / "附件2.xlsx", read_only=True, data_only=True)
ws_l = wb["小区负载"]
ws_p = wb["光伏发电实际功率"]
dates = []
load_kWh = []
pv_kWh = []
for rl, rp in zip(ws_l.iter_rows(min_row=2, values_only=True),
                  ws_p.iter_rows(min_row=2, values_only=True)):
    dates.append(rl[0])
    load_kWh.append([float(v) * H for v in rl[1:]])
    pv_kWh.append([float(v) * H for v in rp[1:]])
wb.close()
dates = [d.strftime("%Y-%m-%d") if not isinstance(d, str) else d for d in dates]
load_kWh = np.array(load_kWh)
pv_kWh = np.array(pv_kWh)
NDAYS = len(dates)
assert load_kWh.shape == pv_kWh.shape == (NDAYS, T), load_kWh.shape
print("附件2:", NDAYS, "天, 形状", load_kWh.shape)

# ---------- 附件4：全年实时电价 ----------
wb = load_workbook(ATT / "附件4.xlsx", read_only=True, data_only=True)
ws = wb["Sheet1"]
price_rt = []
for row in ws.iter_rows(min_row=2, values_only=True):
    price_rt.append([float(v) for v in row[1:]])
wb.close()
price_rt = np.array(price_rt)
assert price_rt.shape == (NDAYS, T), price_rt.shape
print("附件4:", price_rt.shape, "电价范围", price_rt.min(), "-", price_rt.max())

rows_out = []
for d in range(NDAYS):
    for t in range(T):
        rows_out.append(dict(date=dates[d], seg=t + 1, load_kWh=load_kWh[d, t],
                             pv_kWh=pv_kWh[d, t], price_fixed=price1[t],
                             price_rt=price_rt[d, t]))
pd.DataFrame(rows_out).to_csv(DATA / "actual_10min_processed.csv", index=False)
print("actual_10min_processed.csv:", len(rows_out), "行")

# ---------- 附件3：光伏预报档案 → 10 分钟因果插值 ----------
wb = load_workbook(ATT / "附件3.xlsx", read_only=True, data_only=True)
ws = wb["Sheet1"]
raw = list(ws.iter_rows(min_row=2, values_only=True))
wb.close()
# 展开：每行 (日期, 时刻, 24 个小时值)，日期为空表示续上行
fc_rows = []
cur_date = None
for row in raw:
    if row[0]:
        cur_date = row[0]
    fc_rows.append((cur_date, row[1], [float(v) for v in row[2:]]))
assert len(fc_rows) == NDAYS * 4, f"附件3 行数 {len(fc_rows)} != {NDAYS * 4}"

def iso(d):
    s = str(d)
    y, m, dd = s.split("-")
    return f"{y}-{int(m):02d}-{int(dd):02d}"

date_idx = {d: i for i, d in enumerate(dates)}
ISSUE_SEG = {"0:00": 0, "6:00": 36, "12:00": 72, "18:00": 108}
out = []
for (dstr, issue, hvals) in fc_rows:
    d = date_idx.get(iso(dstr))
    if d is None:
        continue
    r = ISSUE_SEG[issue]
    hvals = np.array(hvals)
    # anchor = 发布时刻最近“已完成”的光伏观测：
    #   6:00/12:00/18:00 → 当天第 r-1 段（其区间在发布时刻刚好结束）
    #   0:00           → 前一天第 143 段（23:50–24:00）
    anchor_kW = pv_kWh[d - 1, T - 1] / H if r == 0 else pv_kWh[d, r - 1] / H
    # 当天整点序列：anchor + 其后 24 个整点预报（预报1小时=issue+1h）
    pts = np.zeros(25)
    pts[0] = anchor_kW
    for k in range(1, 25):
        pts[k] = hvals[k - 1]
    # 当天可用的整点数：issue 之后至 24:00 的整点个数 = (144-r)/6，加 anchor
    n_pts_day = (T - r) // 6 + 1
    for k in range(n_pts_day - 1):  # 每两个相邻整点之间 6 个 10 分钟段
        p0, p1 = pts[k], pts[k + 1]
        for j in range(6):
            seg = r + k * 6 + j
            # 线性插值到边界：p_start=p0+(p1-p0)*j/6, p_end=p0+(p1-p0)*(j+1)/6
            p_start = p0 + (p1 - p0) * j / 6.0
            p_end = p0 + (p1 - p0) * (j + 1) / 6.0
            energy = (p_start + p_end) / 2.0 * H  # 相邻边界平均 × 时长
            out.append(dict(interval_start=f"{dates[d]} {(seg*10)//60:02d}:{(seg*10)%60:02d}:00",
                            pv_forecast_kWh=energy, issue_time=f"{dates[d]} {issue}:00"))
fc = pd.DataFrame(out)
fc.to_csv(DATA / "forecast_10min_causal.csv", index=False)
print("forecast_10min_causal.csv:", len(fc), "行; 覆盖段数/天:",
      len(fc) // NDAYS)
print("全部数据重建完成 ->", DATA)
