# -*- coding: utf-8 -*-
"""阶段C/D：论文修订管线（确定性 MILP + 增量结算），已用论文 1 月数字精确验收。

关键规格（与论文一致）：
- 附件3 发布预报替换历史光伏预测，10 分钟插值（锚点=发布时刻最近已完成观测）；
- 残差按“发布时间+区间”分库（net 设计），α 分位数，28 天窗，热身日不入库；
- 增量结算 ΔJ = κ_up·p·a⁺ + κ_dn·p·a⁻（基准 κ_up=1.5, κ_dn=−0.5）；
- 预计应急 e 进入预测平衡（5 倍电价）；字典序第二次：Σ(c+b)+1e-5·|a|+1e-6·e；
- run_day_4：一次求解得到四种嵌套日程（none/06/0612/061218）的结算。
"""
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import coo_matrix
import time as _time

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
act = pd.read_csv(DATA / "actual_10min_processed.csv")
dates_all = list(act["date"].unique())
T, NDAYS = 144, len(dates_all)
load = act["load_kWh"].to_numpy().reshape(NDAYS, T)
pv = act["pv_kWh"].to_numpy().reshape(NDAYS, T)
price = act["price_fixed"].to_numpy().reshape(NDAYS, T)
ETA_C, ETA_B = 0.9, 0.9
E_MIN, E_MAX, P_SEG = 1200.0, 10800.0, 5000.0 / 6.0
ALPHA = 0.85
ADJ_UP, ADJ_DN = 1.5, -0.5
EPS_TOL = 1e-3
MIP_GAP = 1e-7
TIME_LIMIT = 30.0
solve_times = []


def set_alpha(a):
    global ALPHA
    ALPHA = a


def set_kappa(k_up, k_dn):
    global ADJ_UP, ADJ_DN
    ADJ_UP, ADJ_DN = k_up, k_dn


fc = pd.read_csv(DATA / "forecast_10min_causal.csv")
fc["date"] = fc["interval_start"].str[:10]
fc["seg"] = (pd.to_datetime(fc["interval_start"]).dt.hour * 6
             + pd.to_datetime(fc["interval_start"]).dt.minute // 10)
fc["round"] = pd.to_datetime(fc["issue_time"]).dt.hour // 6
date_idx = {d: i for i, d in enumerate(dates_all)}
F4 = np.full((NDAYS, 4, T), np.nan)
for _, row in fc.iterrows():
    d = date_idx.get(row["date"])
    if d is None:
        continue
    F4[d, int(row["round"]), int(row["seg"])] = row["pv_forecast_kWh"]


def predict_load_hist(d):
    if d >= 7:
        last_week = load[d - 7]
        wd = np.arange(d - 7, max(-1, d - 29), -7)
        wd = wd[wd >= 0]
        same_mean = load[wd].mean(axis=0) if len(wd) > 0 else last_week
        return 0.75 * last_week + 0.25 * same_mean
    return load[:d].mean(axis=0) if d > 0 else np.zeros(T)


def hist_forecast_pv(d):
    if d == 0:
        return np.zeros(T)
    j = np.arange(1, min(d, 7) + 1)
    w = np.exp(-np.log(2.0) * j / 3.0)
    return (pv[d - j] * w[:, None]).sum(axis=0) / w.sum()


def corrected_forecast(d, r, risk_adjusted, lib_r):
    """第 d 天第 r 轮（r∈0..3）的修正净需求（kWh）。net 设计：n̂ + Q_α(该轮残差)。"""
    F = np.nan_to_num(F4[d, r], nan=0.0)
    pred_l = predict_load_hist(d)
    n_hat = pred_l - F
    if not risk_adjusted:
        return n_hat
    lo = max(0, len(lib_r) - 28)
    if not lib_r:
        return n_hat
    return n_hat + np.quantile(np.asarray(lib_r[lo:]), ALPHA, axis=0)


def _milp(c_obj, A, lo_v, hi_v, integrality, lb, ub):
    t0 = _time.perf_counter()
    res = milp(c_obj, integrality=integrality, bounds=Bounds(lb, ub),
               constraints=LinearConstraint(A, np.array(lo_v), np.array(hi_v)),
               options={"time_limit": TIME_LIMIT, "mip_rel_gap": MIP_GAP})
    solve_times.append(_time.perf_counter() - t0)
    if not res.success:
        raise RuntimeError(f"MILP 失败: {res.message}")
    return res


def solve_plan(d, n_risk):
    """0:00 计划：q, c, b 全 144 段。目标 Σp(q+5e)。"""
    nseg = T
    NV, N = 8, nseg * 8
    rows, cols, vals, lo_v, hi_v = [], [], [], [], []

    def add_row(ix, lo_, hi_):
        rr = len(lo_v)
        for j, v in ix:
            rows.append(rr)
            cols.append(j)
            vals.append(v)
        lo_v.append(lo_)
        hi_v.append(hi_)

    for i in range(nseg):
        q, c, b, E, z, w, e, _ = (i * NV, i * NV + 1, i * NV + 2, i * NV + 3,
                                  i * NV + 4, i * NV + 5, i * NV + 6, i * NV + 7)
        E_prev = (i - 1) * NV + 3 if i > 0 else None
        add_row([(q, 1), (e, 1), (b, 1), (c, -1), (w, -1)], n_risk[i], n_risk[i])
        if i == 0:
            add_row([(E, 1), (c, -ETA_C), (b, 1 / ETA_B)], 6000.0, 6000.0)
        else:
            add_row([(E, 1), (E_prev, -1), (c, -ETA_C), (b, 1 / ETA_B)], 0.0, 0.0)
        add_row([(c, 1), (z, -P_SEG)], -np.inf, 0.0)
        add_row([(b, 1), (z, P_SEG)], -np.inf, P_SEG)
        if i == 0:
            add_row([(c, 1)], -np.inf, (E_MAX - 6000.0) / ETA_C)
            add_row([(b, 1)], -np.inf, ETA_B * (6000.0 - E_MIN))
        else:
            add_row([(c, 1), (E_prev, 1 / ETA_C)], -np.inf, E_MAX / ETA_C)
            add_row([(b, 1), (E_prev, -ETA_B)], -np.inf, -ETA_B * E_MIN)
    add_row([((nseg - 1) * NV + 3, 1)], 6000.0, 6000.0)
    A = coo_matrix((vals, (rows, cols)), shape=(len(lo_v), N))
    idx_q = np.arange(nseg) * NV
    integrality = np.zeros(N)
    integrality[idx_q + 4] = 1
    lb = np.zeros(N)
    ub = np.full(N, np.inf)
    lb[idx_q + 3] = E_MIN
    ub[idx_q + 3] = E_MAX
    lb[idx_q + 4] = 0
    ub[idx_q + 4] = 1
    c1 = np.zeros(N)
    c1[idx_q] = price[d]
    c1[idx_q + 6] = 5.0 * price[d]
    res1 = _milp(c1, A, lo_v, hi_v, integrality, lb, ub)
    J_star = res1.fun
    c2 = np.zeros(N)
    c2[idx_q + 1] = 1.0
    c2[idx_q + 2] = 1.0
    c2[idx_q + 6] += 1e-6
    rows2 = rows + [len(lo_v)] * N
    cols2 = cols + list(np.arange(N))
    vals2 = vals + list(c1)
    A2 = coo_matrix((vals2, (rows2, cols2)), shape=(len(lo_v) + 1, N))
    res2 = _milp(c2, A2, lo_v + [-np.inf], hi_v + [J_star + EPS_TOL],
                 integrality, lb, ub)
    x = res2.x if res2.success else res1.x
    return x[idx_q], x[idx_q + 1], x[idx_q + 2]


def solve_revision(d, seg, q_old, E_cur, n_risk):
    """seg 起的修订：返回 ap, an, c, b（前 seg 段填 0）。"""
    nseg = T - seg
    NV, N = 8, nseg * 8
    rows, cols, vals, lo_v, hi_v = [], [], [], [], []

    def add_row(ix, lo_, hi_):
        rr = len(lo_v)
        for j, v in ix:
            rows.append(rr)
            cols.append(j)
            vals.append(v)
        lo_v.append(lo_)
        hi_v.append(hi_)

    for i in range(nseg):
        t = seg + i
        ap, an, c, b, E, z, e, w = (i * NV, i * NV + 1, i * NV + 2, i * NV + 3,
                                    i * NV + 4, i * NV + 5, i * NV + 6, i * NV + 7)
        E_prev = (i - 1) * NV + 4 if i > 0 else None
        add_row([(ap, 1), (an, -1), (e, 1), (b, 1), (c, -1), (w, -1)],
                n_risk[t] - q_old[t], n_risk[t] - q_old[t])
        add_row([(ap, 1), (an, -1)], -q_old[t], np.inf)
        if i == 0:
            add_row([(E, 1), (c, -ETA_C), (b, 1 / ETA_B)], E_cur, E_cur)
        else:
            add_row([(E, 1), (E_prev, -1), (c, -ETA_C), (b, 1 / ETA_B)], 0.0, 0.0)
        add_row([(c, 1), (z, -P_SEG)], -np.inf, 0.0)
        add_row([(b, 1), (z, P_SEG)], -np.inf, P_SEG)
        if i == 0:
            add_row([(c, 1)], -np.inf, (E_MAX - E_cur) / ETA_C)
            add_row([(b, 1)], -np.inf, ETA_B * (E_cur - E_MIN))
        else:
            add_row([(c, 1), (E_prev, 1 / ETA_C)], -np.inf, E_MAX / ETA_C)
            add_row([(b, 1), (E_prev, -ETA_B)], -np.inf, -ETA_B * E_MIN)
    add_row([((nseg - 1) * NV + 4, 1)], 6000.0, 6000.0)
    A = coo_matrix((vals, (rows, cols)), shape=(len(lo_v), N))
    idx = np.arange(nseg) * NV
    integrality = np.zeros(N)
    integrality[idx + 5] = 1
    lb = np.zeros(N)
    ub = np.full(N, np.inf)
    lb[idx + 4] = E_MIN
    ub[idx + 4] = E_MAX
    lb[idx + 5] = 0
    ub[idx + 5] = 1
    c1 = np.zeros(N)
    c1[idx] = ADJ_UP * price[d, seg:]
    c1[idx + 1] = ADJ_DN * price[d, seg:]
    c1[idx + 6] = 5.0 * price[d, seg:]
    res1 = _milp(c1, A, lo_v, hi_v, integrality, lb, ub)
    J_star = res1.fun
    c2 = np.zeros(N)
    c2[idx + 2] = 1.0
    c2[idx + 3] = 1.0
    c2[idx] += 1e-5
    c2[idx + 1] += 1e-5
    c2[idx + 6] += 1e-6
    rows2 = rows + [len(lo_v)] * N
    cols2 = cols + list(np.arange(N))
    vals2 = vals + list(c1)
    A2 = coo_matrix((vals2, (rows2, cols2)), shape=(len(lo_v) + 1, N))
    res2 = _milp(c2, A2, lo_v + [-np.inf], hi_v + [J_star + EPS_TOL],
                 integrality, lb, ub)
    x = res2.x if res2.success else res1.x
    ap = np.zeros(T)
    an = np.zeros(T)
    c = np.zeros(T)
    b = np.zeros(T)
    ap[seg:] = x[idx]
    an[seg:] = x[idx + 1]
    c[seg:] = x[idx + 2]
    b[seg:] = x[idx + 3]
    return ap, an, c, b


def run_day_4(d, risk_adjusted, libs, up_to=3):
    """一次求解得到四种嵌套日程的日结算。返回 dict(schedule -> 结算 dict)。
    up_to=2 时跳过 18:00 修订（用于两发布策略的精确求解计数）。"""
    n0 = corrected_forecast(d, 0, risk_adjusted, libs[0])
    q0, c0, b0 = solve_plan(d, n0)
    J_plan = float(np.dot(price[d], q0))

    def realize(q_eff, c_exec, b_exec, J_rev, a_up_kWh):
        u = np.maximum(load[d] + c_exec - q_eff - pv[d] - b_exec, 0.0)
        J_emerg = 5.0 * float(np.dot(price[d], u))
        return dict(date=dates_all[d], J_plan=J_plan, J_rev=J_rev, J_emerg=J_emerg,
                    J=J_plan + J_rev + J_emerg, e_kWh=float(u.sum()),
                    a_up_kWh=float(a_up_kWh))

    out = {"none": realize(q0, c0, b0, 0.0, 0.0)}

    # 06:00 修订
    nr = corrected_forecast(d, 1, risk_adjusted, libs[1])
    E1 = 6000.0
    for t in range(36):
        E1 = E1 + ETA_C * c0[t] - b0[t] / ETA_B
    ap1, an1, c1, b1 = solve_revision(d, 36, q0, E1, nr)
    q1 = q0 + ap1 - an1
    J_rev1 = float(np.sum(ADJ_UP * price[d, 36:] * ap1[36:]
                          + ADJ_DN * price[d, 36:] * an1[36:]))
    c06 = c0.copy()
    b06 = b0.copy()
    c06[36:] = c1[36:]
    b06[36:] = b1[36:]
    out["06"] = realize(q1, c06, b06, J_rev1, float(np.maximum(q1 - q0, 0).sum()))

    # 12:00 修订
    nr = corrected_forecast(d, 2, risk_adjusted, libs[2])
    E2 = 6000.0
    for t in range(72):
        E2 = E2 + ETA_C * c06[t] - b06[t] / ETA_B
    ap2, an2, c2, b2 = solve_revision(d, 72, q1, E2, nr)
    q2 = q1 + ap2 - an2
    J_rev2 = J_rev1 + float(np.sum(ADJ_UP * price[d, 72:] * ap2[72:]
                                   + ADJ_DN * price[d, 72:] * an2[72:]))
    c12 = c06.copy()
    b12 = b06.copy()
    c12[72:] = c2[72:]
    b12[72:] = b2[72:]
    out["0612"] = realize(q2, c12, b12, J_rev2, float(np.maximum(q2 - q0, 0).sum()))

    # 18:00 修订
    if up_to < 3:
        return out
    nr = corrected_forecast(d, 3, risk_adjusted, libs[3])
    E3 = 6000.0
    for t in range(108):
        E3 = E3 + ETA_C * c12[t] - b12[t] / ETA_B
    ap3, an3, c3, b3 = solve_revision(d, 108, q2, E3, nr)
    q3 = q2 + ap3 - an3
    J_rev3 = J_rev2 + float(np.sum(ADJ_UP * price[d, 108:] * ap3[108:]
                                   + ADJ_DN * price[d, 108:] * an3[108:]))
    c18 = c12.copy()
    b18 = b12.copy()
    c18[108:] = c3[108:]
    b18[108:] = b3[108:]
    out["061218"] = realize(q3, c18, b18, J_rev3, float(np.maximum(q3 - q0, 0).sum()))
    return out


def run_window_4(days, risk_adjusted, libs=None):
    """目标天数上运行，返回 {schedule: [日记录]}。残差库从 Jan 1 起因果构建。"""
    if libs is None:
        libs = {r: [] for r in range(4)}
    days_set = set(days)
    out = {"none": [], "06": [], "0612": [], "061218": []}
    for d in range(max(days) + 1):
        if d in days_set:
            res = run_day_4(d, risk_adjusted, libs)
            for sched, rec in res.items():
                out[sched].append(rec)
        if d >= 7:
            for r in range(4):
                F = np.nan_to_num(F4[d, r], nan=0.0)
                pred_l = predict_load_hist(d)
                res = load[d] - pv[d] - (pred_l - F)
                res[: (r if r > 0 else 0)] = 0.0
                libs[r].append(res)
    return out
