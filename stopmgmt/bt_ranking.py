"""bt_ranking.py — اختبار ترتيب الإشارات حسب reports/2026-11-27/visual_review/arbitration/round2/BT_RANKING_SPEC.md.
يعيد استخدام الإشارات والمحاكاة من bt_readings.py كما هي (يُنفَّذ الجزء الأول منه)، ويضيف:
ميزات الترتيب، وسجل الحركة اليومي لكل صفقة، ومحفظة يومية بقيمة سوقية. لا يعدّل أي ملف قائم.
الاستخدام: python3 bt_ranking.py  → out/ranking_us_v1.1.json
v1.1 (2026-11-28): إصلاح تسرب زمني أشار إليه ChatGPT. في فترة الاختيار تُقطع كل صفقة عند إغلاق 2026-02-27، والمفتوح منها يُقيَّم بسعر ذلك اليوم.
فترة التحقق محفظة جديدة فارغة تبدأ من 2026-03-02.
"""
import os, sys, json, random
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.argv = [sys.argv[0], "us"]
exec(open(os.path.join(HERE, "bt_readings.py"), encoding="utf-8").read().split('out = {"market"')[0])

SPLIT_END, VAL_START = pd.Timestamp("2026-02-27"), pd.Timestamp("2026-03-02")

def feats(sg):
    """ميزات الترتيب ليوم الإشارة، من البيانات حتى يوم الإشارة فقط."""
    d = D[sg["sym"]]; i = sg["i"]; t = T.close.reindex(d.index)
    f = {"RS21": float(d.close.iloc[i] / d.close.iloc[i - 21] - t.iloc[i] / t.iloc[i - 21]),
         "RS63": float(d.close.iloc[i] / d.close.iloc[i - 63] - t.iloc[i] / t.iloc[i - 63]),
         "PROX": float((sg["pivot"] - d.close.iloc[i]) / sg["pivot"]), "VOL": None, "TIGHT": None}
    if sg["shape"] == "VCP":
        w = d.iloc[max(0, i - 129): i + 1]
        h, l, v = (w[x].tolist()[-120:] for x in ("high", "low", "volume"))
        piv = _pivots(h, l, 2)
        if piv and piv[0][1] == "L": piv = piv[1:]
        cons = [(piv[k], piv[k + 1], (piv[k][2] - piv[k + 1][2]) / piv[k][2]) for k in range(0, len(piv) - 1, 2)
                if piv[k][1] == "H" and piv[k + 1][1] == "L"]
        k = len(cons) - 1
        while k > 0 and cons[k - 1][2] > cons[k][2] and cons[k - 1][1][2] < cons[k][1][2]: k -= 1
        run = cons[k:]; lastH, lastL, lastD = run[-1]
        vavg50 = sum(v[-50:]) / 50
        f["VOL"] = (sum(v[lastH[0]:lastL[0] + 1]) / max(1, lastL[0] - lastH[0] + 1)) / vavg50
        f["TIGHT"] = lastD / run[-2][2] if len(run) >= 2 and run[-2][2] > 0 else None
    return f

def sim_daily(sg):
    """simulate() من bt_readings، مع سجل (يوم، تغير الكمية، تدفق نقدي). منطق الخروج نفسه."""
    t0 = simulate(sg)
    if t0 is None: return None
    s = sg["sym"]; d = D[s]; i0 = sg["i"] + 1; E, S0 = sg["entry"], sg["stop"]
    expl = (not sg["serve"]) and EXPLORE
    full = int(min(RISK / (E - S0), CAP / E)); q1 = int(full * 0.2) if expl else full
    buy = lambda px: px * (1 + SLIP) * (1 + COM); sell = lambda px: px * (1 - SLIP) * (1 - COM)
    ev = [(d.index[i0], q1, -buy(E) * q1)]; qty = q1
    stop, half, exit_next = S0, False, False
    hi, lo, cl, op, sma20, w30x = d.high.values, d.low.values, d.close.values, d.open.values, d.sma20.values, d.w30x.values
    n = len(d); t = i0
    while t < n:
        if t > i0:
            if exit_next: ev.append((d.index[t], -qty, sell(op[t]) * qty)); qty = 0; break
            if op[t] <= stop: ev.append((d.index[t], -qty, sell(op[t]) * qty)); qty = 0; break
            if lo[t] <= stop: ev.append((d.index[t], -qty, sell(stop) * qty)); qty = 0; break
            if not half and hi[t] >= E * 1.25:
                q = qty // 2; px = max(op[t], E * 1.25); ev.append((d.index[t], -q, sell(px) * q)); qty -= q; half = True
        else:
            if lo[t] <= stop: ev.append((d.index[t], -qty, sell(stop) * qty)); qty = 0; break
        if t == i0:
            if expl: stop = max(stop, lo[t] * 0.999)
            if cl[t] < lo[t - 1]: exit_next = True
        if half and cl[t] < sma20[t] and not exit_next: exit_next = True
        if w30x[t] and not exit_next: exit_next = True
        t += 1
    pnl = sum(c for _, _, c in ev) + (sell(cl[-1]) * qty if qty > 0 else 0)
    assert abs(pnl - t0["pnl"]) < 1.0, (s, pnl, t0["pnl"])   # تطابق مع simulate الأصلي
    t0["events"] = ev; t0["risk"] = q1 * (E - S0)
    return t0

def truncate(t, end):
    """يقطع الصفقة عند إغلاق end: الحركات بعده تُحذف، والكمية المتبقية تُقيَّم بإغلاق end مع تكلفة البيع."""
    if t["out"] != "open" and pd.Timestamp(t["out"]) <= end: return t
    ev = [e for e in t["events"] if e[0] <= end]
    if not ev: return None
    qty = sum(dq for _, dq, _ in ev); px = float(D[t["sym"]].close.loc[:end].iloc[-1])
    pnl = sum(c for _, _, c in ev) + px * (1 - SLIP) * (1 - COM) * qty
    u = dict(t); u.update({"events": ev, "pnl": round(pnl, 2), "R": round(pnl / t["risk"], 3), "out": "open", "cut": True})
    return u

def run_portfolio(sigs, key=None, rng=None, lo_day=None, hi_day=None):
    sigs = [s for s in sigs if (lo_day is None or s["day"] >= lo_day) and (hi_day is None or s["day"] <= hi_day)]
    byday = {}
    for s in sigs: byday.setdefault(s["day"], []).append(s)
    res = []
    for day in sorted(byday):
        cand = byday[day]
        if rng is not None: cand = sorted(cand, key=lambda x: rng.random())
        elif key is not None: cand = sorted(cand, key=key)
        else: cand = sorted(cand, key=lambda x: x["sym"])
        for sg in cand:
            day_in = D[sg["sym"]].index[sg["i"] + 1]
            live = [t for t in res if t["out"] == "open" or pd.Timestamp(t["out"]) >= day_in]
            if any(t["sym"] == sg["sym"] for t in live) or len(live) >= MAXP: continue
            t = SIM[(sg["sym"], sg["i"])]
            if t is None or sum(x["maxcost"] for x in live) + t["maxcost"] > MAXINV: continue
            res.append(t)
    if hi_day is not None: res = [x for x in (truncate(t, hi_day) for t in res) if x]
    return res

def metrics(tr, end=None):
    if not tr: return {"trades": 0}
    st = stats(tr)
    days = T.index[T.index >= min(e[0] for t in tr for e in t["events"])]
    if end is not None: days = days[days <= end]
    cash = pd.Series(0.0, index=days); pos = {}
    for t in tr:
        for (dt, dq, c) in t["events"]:
            cash.loc[dt] += c; pos.setdefault(t["sym"] + t["in"], []).append((dt, dq, t["sym"]))
    eq = cash.cumsum() + BAL
    for k, evs in pos.items():
        sym = evs[0][2]; q = pd.Series(0.0, index=days)
        for dt, dq, _ in evs: q.loc[dt] += dq
        q = q.cumsum(); px = D[sym].close.reindex(days).ffill()
        eq = eq + (q * px).fillna(0)
    peak = eq.cummax(); dd = (peak - eq); mdd = float(dd.max())
    under = (dd > 0).astype(int); longest = cur = 0
    for u in under: cur = cur + 1 if u else 0; longest = max(longest, cur)
    st.update({"mtm_maxDD": round(mdd), "dd_days": longest, "ret_to_dd": round((eq.iloc[-1] - BAL) / mdd, 2) if mdd > 0 else None,
               "end_equity": round(float(eq.iloc[-1])), "avg_risk": round(float(np.mean([t["risk"] for t in tr])))})
    return st

out = {"window": [str(START.date()), str(T.index[-1].date())], "split": [str(SPLIT_END.date()), str(VAL_START.date())], "pools": {}}
CRIT = {"RS21": lambda s: -s["f"]["RS21"], "RS63": lambda s: -s["f"]["RS63"], "PROX": lambda s: s["f"]["PROX"],
        "VOL": lambda s: s["f"]["VOL"] if s["f"]["VOL"] is not None else 9e9,
        "TIGHT": lambda s: s["f"]["TIGHT"] if s["f"]["TIGHT"] is not None else 9e9}
for pool in ("R0", "A"):
    minc, pm, sm = VARS[pool]; sigs = signals_for(minc, pm, sm)
    for s in sigs: s["f"] = feats(s)
    SIM = {(s["sym"], s["i"]): sim_daily(s) for s in sigs}
    sameday = pd.Series([s["day"] for s in sigs]).value_counts()
    P = {"signals": len(sigs), "days_with_2plus": int((sameday >= 2).sum()), "checkout_signals": sum(s["shape"] != "VCP" for s in sigs), "periods": {}}
    for per, lo_d, hi_d in (("all", None, None), ("select", None, SPLIT_END), ("validate", VAL_START, None)):
        R = {"ORDER": metrics(run_portfolio(sigs, lo_day=lo_d, hi_day=hi_d), hi_d)}
        for c, k in CRIT.items(): R[c] = metrics(run_portfolio(sigs, key=k, lo_day=lo_d, hi_day=hi_d), hi_d)
        rnd = [metrics(run_portfolio(sigs, rng=random.Random(j), lo_day=lo_d, hi_day=hi_d), hi_d) for j in range(300)]
        R["RANDOM"] = {m: {"p5": round(float(np.percentile([x.get(m) or 0 for x in rnd], 5)), 2),
                           "median": round(float(np.median([x.get(m) or 0 for x in rnd])), 2),
                           "p95": round(float(np.percentile([x.get(m) or 0 for x in rnd], 95)), 2)}
                       for m in ("net", "pf", "trades", "mtm_maxDD", "ret_to_dd")}
        P["periods"][per] = R
    out["pools"][pool] = P
json.dump(out, open(os.path.join(OUT, "ranking_us_v1.1.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
for pool, P in out["pools"].items():
    print(pool, "signals", P["signals"], "days>=2", P["days_with_2plus"], "checkout", P["checkout_signals"])
    for per, R in P["periods"].items():
        print(" ", per, "RANDOM", {m: R["RANDOM"][m] for m in ("net", "mtm_maxDD", "trades")})
        for c in ["ORDER"] + list(CRIT):
            x = R[c]; print("   ", c, {m: x.get(m) for m in ("trades", "net", "pf", "expR", "mtm_maxDD", "dd_days", "ret_to_dd", "avg_risk")})
