"""diag_portfolio.py — تحليل مخاطر محفظة الستة مراكز حسب reports/.../round2/DIAG_PORTFOLIO_SPEC.md. وصفي فقط.
يعيد استخدام bt_ranking.py (المحفظة والمحاكاة اليومية) دون تغيير.
الاستخدام: python3 diag_portfolio.py → out/diag_portfolio_us.json
"""
import os, sys, json
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
src = open(os.path.join(HERE, "bt_ranking.py"), encoding="utf-8").read().split('out = {"window"')[0]
exec(src)

def daily(tr, end=None):
    days = T.index[T.index >= min(e[0] for t in tr for e in t["events"])]
    if end is not None: days = days[days <= end]
    cash = pd.Series(0.0, index=days); eq_pos = pd.DataFrame(0.0, index=days, columns=range(len(tr)))
    risk0 = pd.Series(0.0, index=days); risk_now = pd.Series(0.0, index=days); npos = pd.Series(0, index=days)
    for j, t in enumerate(tr):
        q = pd.Series(0.0, index=days)
        for dt, dq, c in t["events"]:
            if dt in cash.index: cash.loc[dt] += c; q.loc[dt] += dq
        q = q.cumsum(); px = D[t["sym"]].close.reindex(days).ffill()
        val = (q * px).fillna(0); eq_pos[j] = val
        flow = pd.Series(0.0, index=days)
        for dt, dq, c in t["events"]:
            if dt in flow.index: flow.loc[dt] += c
        eq_pos[j] = val + flow.cumsum()          # مساهمة الصفقة في رأس المال (نقد + قيمة)
        held = q > 0
        risk0 += held * t["risk"]
        risk_now += (q * (px - t["stop0"])).clip(lower=0).fillna(0)
        npos += held.astype(int)
    eq = BAL + eq_pos.sum(axis=1)
    return days, eq, eq_pos, risk0, risk_now, npos

def analyze(tr, end=None):
    if not tr: return {"trades": 0}
    days, eq, eq_pos, risk0, risk_now, npos = daily(tr, end)
    peak = eq.cummax(); dd = peak - eq; t_trough = dd.idxmax(); t_peak = eq.loc[:t_trough].idxmax()
    contrib = (eq_pos.loc[t_trough] - eq_pos.loc[t_peak]).sort_values()
    top = [{"sym": tr[j]["sym"], "in": tr[j]["in"], "out": tr[j]["out"], "change": round(float(v))} for j, v in contrib.head(5).items()]
    stops = [t for t in tr if t["reason"] == "stop" and t["out"] != "open"]   # المقطوعة عند نهاية الفترة ليست وقفاً بعد
    wk = pd.Series([pd.Timestamp(t["out"]).to_period("W-FRI") for t in stops])
    cnt = wk.value_counts(); clustered = set(cnt[cnt >= 2].index)
    loss_all = -sum(t["pnl"] for t in stops); loss_cl = -sum(t["pnl"] for t, w in zip(stops, wk) if w in clustered)
    idxw = T.close.resample("W-FRI").last().pct_change() * 100
    cl_weeks = [{"week": str(w), "stops": int(cnt[w]), "loss": round(-sum(t["pnl"] for t, ww in zip(stops, wk) if ww == w)),
                 "index_week%": round(float(idxw.loc[w.end_time.normalize()]), 2) if w.end_time.normalize() in idxw.index else None}
                for w in sorted(clustered)]
    return {"trades": len(tr), "net": round(float(eq.iloc[-1] - BAL)), "mtm_maxDD": round(float(dd.max())),
            "dd_peak": str(t_peak.date()), "dd_trough": str(t_trough.date()),
            "risk0_%_mean": round(float(risk0[npos > 0].mean() / BAL * 100), 2), "risk0_%_max": round(float(risk0.max() / BAL * 100), 2),
            "risk_now_%_mean": round(float(risk_now[npos > 0].mean() / BAL * 100), 2), "risk_now_%_max": round(float(risk_now.max() / BAL * 100), 2),
            "positions_mean": round(float(npos.mean()), 2), "days_full(6)": int((npos >= MAXP).sum()), "days": len(days),
            "stops": len(stops), "stop_loss_total": round(loss_all), "clustered_weeks": len(clustered),
            "stop_loss_in_clustered_weeks": round(loss_cl), "clustered_share%": round(loss_cl / loss_all * 100, 1) if loss_all else None,
            "clustered_detail": cl_weeks, "top5_dd_contributors": top}

out = {}
for pool in ("R0", "A"):
    minc, pm, sm = VARS[pool]; sigs = signals_for(minc, pm, sm)
    SIM = {(s["sym"], s["i"]): sim_daily(s) for s in sigs}
    out[pool] = {"all": analyze(run_portfolio(sigs)),
                 "select": analyze(run_portfolio(sigs, hi_day=SPLIT_END), SPLIT_END),
                 "validate": analyze(run_portfolio(sigs, lo_day=VAL_START))}
json.dump(out, open(os.path.join(OUT, "diag_portfolio_us.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
for pool, P in out.items():
    for per, r in P.items(): print(pool, per, json.dumps(r, ensure_ascii=False))
