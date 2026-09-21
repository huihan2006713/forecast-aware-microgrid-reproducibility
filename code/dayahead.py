# -*- coding: utf-8 -*-
"""阶段B：论文日前管线复现（附件1 分时电价每日重复；334 天评估期）。

与论文一致：负荷 0.75×上周同日+0.25×同星期日均值；光伏 7 天指数加权（半衰期3天）；
残差分位数 α；28 天残差窗；MILP 一次主目标 + 字典序二次稳定；应急 5 倍电价。
验收：α=0.85 总计 14,748,456.68；α=0.50 总计 16,105,821.27；点预测 16,022,432.05。
"""
import json
import time as _time
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import coo_matrix

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RESULTS = ROOT / "results"
RESULTS.mkdir(exist_ok=True)
act = pd.read_csv(DATA / "actual_10min_processed.csv")
dates_all = list(act["date"].unique())
T, NDAYS = 144, len(dates_all)
load = act["load_kWh"].to_numpy().reshape(NDAYS, T)
pv = act["pv_kWh"].to_numpy().reshape(NDAYS, T)
price = act["price_fixed"].to_numpy().reshape(NDAYS, T)
ETA_C, ETA_B = 0.9, 0.9
E_MIN, E_MAX, P_SEG = 1200.0, 10800.0, 5000.0 / 6.0
EPS_TOL = 1e-3            # 字典序第二次求解的目标容差（CNY，绝对）
MIP_GAP = 1e-7
TIME_LIMIT = 30.0
_WINDOW = 28              # 残差窗默认 28 天；margin_search 可覆盖
_MODEL = "e"              # "e"：含预计应急变量的模型；"noe"：论文第 3 节纯平衡模型
_SECOND = True            # 是否做字典序第二次求解
_LOAD_VARIANT = "incl_d7"  # 同星期日均值是否包含 d-7
_WARMUP_RESID = True       # 热身日（d<7）的残差是否进入库
solve_times = []          # 每次 milp 调用的墙钟秒数（D4 统计用）


def set_window(w):
    global _WINDOW
    _WINDOW = w


def set_cfg(model=None, second=None):
    global _MODEL, _SECOND
    if model is not None:
        _MODEL = model
    if second is not None:
        _SECOND = second


def set_load_variant(v):
    global _LOAD_VARIANT
    _LOAD_VARIANT = v


def set_warmup_resid(v):
    global _WARMUP_RESID
    _WARMUP_RESID = v


def solve_day(n_risk, p_hat, with_storage=True):
    """一天的前日 MILP。返回 (q, c, b)。

    _MODEL="e"：平衡 q+e+b-c-w=n，目标 Σp(q+5e)（k_annual 结构）；
    _MODEL="noe"：平衡 q+b-c-w=n，目标 Σp·q（论文第 3 节）。
    _SECOND 控制是否做字典序第二次求解。"""
    use_e = _MODEL == "e"
    NV = 7 if use_e else 6
    nseg = T
    N = nseg * NV
    rows, cols, vals, lo_v, hi_v = [], [], [], [], []

    def add_row(ix, lo_, hi_):
        r = len(lo_v)
        for j, v in ix:
            rows.append(r)
            cols.append(j)
            vals.append(v)
        lo_v.append(lo_)
        hi_v.append(hi_)

    for i in range(nseg):
        base = i * NV
        q, c, b, E, z, w = base, base + 1, base + 2, base + 3, base + 4, base + 5
        e = base + 6 if use_e else None
        E_prev = (i - 1) * NV + 3 if i > 0 else None
        if use_e:
            add_row([(q, 1), (e, 1), (b, 1), (c, -1), (w, -1)], n_risk[i], n_risk[i])
        else:
            add_row([(q, 1), (b, 1), (c, -1), (w, -1)], n_risk[i], n_risk[i])
        if i == 0:
            add_row([(E, 1), (c, -ETA_C), (b, 1 / ETA_B)], 6000.0, 6000.0)
        else:
            add_row([(E, 1), (E_prev, -1), (c, -ETA_C), (b, 1 / ETA_B)], 0.0, 0.0)
        if with_storage:
            add_row([(c, 1), (z, -P_SEG)], -np.inf, 0.0)
            add_row([(b, 1), (z, P_SEG)], -np.inf, P_SEG)
            if i == 0:
                add_row([(c, 1)], -np.inf, (E_MAX - 6000.0) / ETA_C)
                add_row([(b, 1)], -np.inf, ETA_B * (6000.0 - E_MIN))
            else:
                add_row([(c, 1), (E_prev, 1 / ETA_C)], -np.inf, E_MAX / ETA_C)
                add_row([(b, 1), (E_prev, -ETA_B)], -np.inf, -ETA_B * E_MIN)
        else:
            add_row([(c, 1)], 0.0, 0.0)
            add_row([(b, 1)], 0.0, 0.0)
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

    def run_milp(c_obj, extra_rows=None, extra_lo=None, extra_hi=None):
        t0 = _time.perf_counter()
        if extra_rows is None:
            A_ = A
            lo_ = np.array(lo_v)
            hi_ = np.array(hi_v)
        else:
            A_ = coo_matrix((np.concatenate([vals, extra_rows[0]]),
                             (np.concatenate([rows, extra_rows[1]]),
                              np.concatenate([cols, extra_rows[2]]))),
                            shape=(len(lo_v) + extra_rows[3], N))
            lo_ = np.array(lo_v + extra_lo)
            hi_ = np.array(hi_v + extra_hi)
        res = milp(c_obj, integrality=integrality, bounds=Bounds(lb, ub),
                   constraints=LinearConstraint(A_, lo_, hi_),
                   options={"time_limit": TIME_LIMIT, "mip_rel_gap": MIP_GAP})
        solve_times.append(_time.perf_counter() - t0)
        if not res.success:
            raise RuntimeError(f"MILP 失败: {res.message}")
        return res

    c1 = np.zeros(N)
    c1[idx_q] = p_hat
    if use_e:
        c1[idx_q + 6] = 5.0 * p_hat
    res1 = run_milp(c1)
    if not _SECOND:
        x = res1.x
        return x[idx_q], x[idx_q + 1], x[idx_q + 2]
    J_star = res1.fun
    # 字典序第二次：在 J ≤ J* + ε 内最小化充放电总量
    c2 = np.zeros(N)
    c2[idx_q + 1] = 1.0
    c2[idx_q + 2] = 1.0
    res2 = run_milp(c2, extra_rows=(list(c1), [len(lo_v)] * N, list(np.arange(N)), 1),
                    extra_lo=[-np.inf], extra_hi=[J_star + EPS_TOL])
    x = res2.x if res2.success else res1.x
    return x[idx_q], x[idx_q + 1], x[idx_q + 2]


def run_policy(alpha, with_storage=True, tag="", qmethod="linear", eval_start=31,
               eval_end=None):
    """alpha=None 表示点预测不加残差。返回 (Jp_out, Je_out, daily_list, 观测覆盖率)。
    累计窗口为 [eval_start, eval_end)（1月校准=[21,31)，评估期=[31,NDAYS)）。"""
    if eval_end is None:
        eval_end = NDAYS
    resid_lib = []
    Jp_out = Je_out = 0.0
    daily = []
    covered = []
    for d in range(NDAYS):
        if d >= 7:
            last_week = load[d - 7]
            if _LOAD_VARIANT == "excl_d7":
                wd = np.arange(d - 14, max(-1, d - 36), -7)
            else:
                wd = np.arange(d - 7, max(-1, d - 29), -7)
            wd = wd[wd >= 0]
            same_mean = load[wd].mean(axis=0) if len(wd) > 0 else last_week
            pred_l = 0.75 * last_week + 0.25 * same_mean
        elif d > 0:
            pred_l = load[:d].mean(axis=0)
        else:
            pred_l = np.zeros(T)
        if d == 0:
            pred_g = np.zeros(T)
        else:
            j = np.arange(1, min(d, 7) + 1)
            w = np.exp(-np.log(2.0) * j / 3.0)
            pred_g = (pv[d - j] * w[:, None]).sum(axis=0) / w.sum()
        n_hat = pred_l - pred_g
        if alpha is None:
            margin = np.zeros(T)
        else:
            lo_r = max(0, len(resid_lib) - _WINDOW)
            margin = (np.quantile(np.asarray(resid_lib[lo_r:]), alpha, axis=0,
                                  method=qmethod)
                      if resid_lib else np.zeros(T))
        p_hat = price[0]  # 附件1 分时电价每日相同
        q, c, b = solve_day(n_hat + margin, p_hat, with_storage)
        e_real = np.maximum(load[d] + c - q - pv[d] - b, 0.0)
        jp = np.dot(price[d], q)
        je = 5.0 * np.dot(price[d], e_real)
        if eval_start <= d < eval_end:
            Jp_out += jp
            Je_out += je
            daily.append(dict(date=dates_all[d], J_plan=jp, J_emerg=je, J=jp + je,
                              e_kWh=float(e_real.sum())))
        if _WARMUP_RESID or d >= 7:
            resid_lib.append(load[d] - pv[d] - n_hat)
        covered.append(float(np.mean(n_hat + margin >= load[d] - pv[d])))
    cov = float(np.mean(covered[eval_start:eval_end]))
    return Jp_out, Je_out, daily, cov


if __name__ == "__main__":
    import sys
    qmethod = sys.argv[1] if len(sys.argv) > 1 else "linear"
    report = {}
    daily_store = {}
    for tag, alpha, storage in [("alpha0.85", 0.85, True),
                                ("alpha0.50", 0.50, True),
                                ("point", None, True),
                                ("nostorage_a85", 0.85, False)]:
        t0 = _time.time()
        Jp, Je, daily, cov = run_policy(alpha, storage, tag, qmethod)
        el = _time.time() - t0
        total = Jp + Je
        report[tag] = dict(Jp=round(Jp, 2), Je=round(Je, 2), total=round(total, 2),
                           coverage=round(cov, 4), wall_s=round(el, 1))
        daily_store[tag] = daily
        print(f"{tag:15s} 计划费 {Jp:>14.2f} + 应急费 {Je:>12.2f} = {total:>14.2f}"
              f"  覆盖率 {cov*100:.2f}%  用时 {el:.0f}s")
    suffix = "final" if qmethod == "linear" else qmethod
    with open(RESULTS / f"output_dayahead_{suffix}.json", "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    pd.DataFrame([dict(policy=k, **d) for k, v in daily_store.items() for d in v]).to_csv(
        RESULTS / f"dayahead_daily_{suffix}.csv", index=False)
    # 期望值验收
    exp = {"alpha0.85": 14748456.68, "alpha0.50": 16105821.27,
           "point": 16022432.05, "nostorage_a85": 18525961.72}
    for tag, e in exp.items():
        got = report[tag]["total"]
        print(f"  验收 {tag}: 期望 {e:>14.2f} 得到 {got:>14.2f} "
              f"差 {abs(got-e):.2f} {'OK' if abs(got - e) < 0.01 else 'MISMATCH'}")
    print("MILP 调用次数:", len(solve_times))
