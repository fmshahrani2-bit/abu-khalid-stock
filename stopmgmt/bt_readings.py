"""bt_readings.py — اختبار القراءات الثلاث حسب reports/2026-11-27/visual_review/arbitration/round2/BT_READINGS_SPEC.md.
لا يعدّل scripts/vcp.py ولا stopmgmt/bt_stopmgmt.py. ينسخ منطق detect() وsimulate(V0, P) ويضيف مفاتيح القراءات فقط.
الاستخدام: python3 bt_readings.py sa|us  → out/readings_<mkt>.json
"""
import os, sys, json, glob, math
import numpy as np, pandas as pd

REPO = os.environ.get("REPO", "/home/claude/verify")
sys.path.insert(0, os.path.join(REPO, "scripts"))
from vcp import _pivots, MAX_STOP, ALIGN_TOL

MKT = sys.argv[1] if len(sys.argv) > 1 else "sa"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"); os.makedirs(OUT, exist_ok=True)
if MKT == "us":
    H, IDX, COM, WK, EXPLORE = os.path.join(REPO, "bt", "hist_us"), "SPX", 0.0005, "W-FRI", False
else:
    H, IDX, COM, WK, EXPLORE = os.path.join(REPO, "bt", "hist"), "TASI", 0.00178, "W-THU", True
BAL, RISK, CAP, MAXP, MAXINV, SLIP = 100_000, 2_000, 100_000 / 6, 6, 80_000, 0.001
VARS = {"R0": (3, "basetop", "last"), "A": (2, "basetop", "last"), "B1": (3, "lastc", "last"),
        "B2": (3, "twostage", "last"), "C": (3, "basetop", "base"), "A+B1": (2, "lastc", "last")}

T = pd.read_csv(os.path.join(H, f"{IDX}.csv"), index_col=0, parse_dates=True); T = T[~T.index.duplicated()]
T["sma50"] = T.close.rolling(50).mean(); serve = (T.close > T.sma50)

def prep(d):   # منسوخ من bt_stopmgmt.prep دون تغيير
    d = d[~d.index.duplicated()].reindex(T.index).dropna().copy()
    d["sma20"] = d.close.rolling(20).mean(); d["sma150"] = d.close.rolling(150).mean(); d["sma200"] = d.close.rolling(200).mean()
    t = T.close.reindex(d.index)
    d["ok"] = ((d.close / d.close.shift(250) - 1 > .20) & (d.close > d.sma150) & (d.close > d.sma200) & (d.close > d.sma20)
               & (d.close / d.close.shift(21) - t / t.shift(21) > 0) & (d.close / d.close.shift(63) - t / t.shift(63) > 0))
    wk = d.close.resample(WK).last().dropna(); w30 = wk.rolling(30).mean()
    last_day = d.index.to_series().resample(WK).last().dropna()
    flag = pd.Series(False, index=d.index)
    for wend, day in last_day.items():
        if wend in w30.index and not math.isnan(w30.loc[wend]) and wk.loc[wend] < w30.loc[wend]: flag.loc[day] = True
    d["w30x"] = flag
    return d

def detect_p(o, h, l, c, v, minc, pmode, smode, window=120, K=2):
    """detect() من vcp.py حرفياً، مع ثلاثة مفاتيح: minc (الحد الأدنى للانكماشات)، pmode (basetop/lastc/twostage)، smode (last/base)."""
    n = len(c)
    if n < 60: return None
    o, h, l, c, v = [x[-window:] for x in (o, h, l, c, v)]
    n = len(c); vavg50 = sum(v[-50:]) / 50
    piv = _pivots(h, l, K)
    if piv and piv[0][1] == "L": piv = piv[1:]
    cons = [(piv[i], piv[i + 1], (piv[i][2] - piv[i + 1][2]) / piv[i][2]) for i in range(0, len(piv) - 1, 2)
            if piv[i][1] == "H" and piv[i + 1][1] == "L"]
    if cons:
        k = len(cons) - 1
        while k > 0 and cons[k - 1][2] > cons[k][2] and cons[k - 1][1][2] < cons[k][1][2]: k -= 1
        run = cons[k:]; d = [x[2] for x in run]
        lastH, lastL, lastD = run[-1]; top = run[0][0][2]
        base_top = max(x[0][2] for x in run)
        aligned = lastH[2] >= base_top * (1 - ALIGN_TOL)
        entry_ref = (lastH[2] if aligned else base_top) if pmode == "basetop" else lastH[2]
        vol_last = sum(v[lastH[0]:lastL[0] + 1]) / max(1, lastL[0] - lastH[0] + 1)
        intact = min(l[lastL[0]:]) >= lastL[2]
        not_far = c[-1] <= entry_ref * 1.03
        under_top = all(x[0][2] <= top * 1.03 for x in run)
        low_ref = lastL[2] if smode == "last" else min(x[1][2] for x in run)
        pivot, stop = entry_ref * 1.004, low_ref * 0.999
        stop_ok = (pivot - stop) / pivot <= MAX_STOP
        if len(run) >= minc and lastD < 0.10 and vol_last < vavg50 and intact and not_far and under_top and stop_ok:
            return {"shape": "VCP", "pivot": pivot, "stop": stop, "add": (base_top * 1.004 if (pmode == "twostage" and not aligned) else None),
                    "ncons": len(run)}
    for j in range(n - 15, n - 1):   # شيك أوت: كما هو
        base_low = min(l[j - 20:j]) if j >= 20 else None
        if base_low and l[j] < base_low and v[j] >= 1.5 * vavg50:
            back = [k for k in range(j, min(n, j + 4)) if c[k] > base_low]
            top = max(h[j - 20:j])
            if back and min(l[j:]) >= l[j] and (top * 1.004 - l[j] * 0.999) / (top * 1.004) <= MAX_STOP:
                return {"shape": "شيك أوت", "pivot": top * 1.004, "stop": l[j] * 0.999, "add": None, "ncons": 0}
    return None

D = {}
for f in sorted(glob.glob(os.path.join(H, "*.csv"))):
    s = os.path.basename(f)[:-4]
    if s == IDX: continue
    d = pd.read_csv(f, index_col=0, parse_dates=True)
    if len(d) < 260: continue
    D[s] = prep(d)
START = pd.Timestamp("2025-07-01")

def signals_for(minc, pmode, smode):   # منطق الإشارة من bt_stopmgmt دون تغيير
    out = []
    for s, d in D.items():
        idx = d.index
        for i in range(250, len(d) - 1):
            if idx[i] < START or not d.ok.iloc[i]: continue
            w = d.iloc[max(0, i - 129): i + 1]
            sh = detect_p(*(w[x].tolist() for x in ("open", "high", "low", "close", "volume")), minc, pmode, smode)
            if not sh: continue
            piv, stop = sh["pivot"], sh["stop"]
            if not (d.close.iloc[i] < piv and (piv - stop) / piv < 0.10): continue
            trig = max(piv, d.high.iloc[i] * 1.001)
            if trig > piv * 1.03: continue
            r = d.iloc[i + 1]
            if r.high >= trig and r.open <= piv * 1.03:
                entry = max(r.open, trig)
                if entry > stop:
                    out.append({"sym": s, "i": i, "day": idx[i], "pivot": piv, "stop": stop, "entry": entry, "shape": sh["shape"],
                                "add": sh["add"], "ncons": sh["ncons"], "serve": bool(serve.loc[idx[i]])})
    out.sort(key=lambda x: (x["day"], x["sym"])); return out

def simulate(sg):   # V0 بناء P من bt_stopmgmt، مع إضافة المرحلة الثانية في B2 فقط
    s = sg["sym"]; d = D[s]; i0 = sg["i"] + 1; E, S0, piv = sg["entry"], sg["stop"], sg["pivot"]
    expl = (not sg["serve"]) and EXPLORE
    if (not sg["serve"]) and not EXPLORE: return None
    full = int(min(RISK / (E - S0), CAP / E))
    two = sg["add"] is not None and not expl
    q1 = int(full * 0.2) if expl else (full // 2 if two else full)
    if q1 <= 0: return None
    buy = lambda px: px * (1 + SLIP) * (1 + COM); sell = lambda px: px * (1 - SLIP) * (1 - COM)
    qty, cost, proceeds, maxq = q1, buy(E) * q1, 0.0, q1
    stop, half, exit_next, reason, added = S0, False, False, None, False
    hi, lo, cl, op, sma20, w30x = d.high.values, d.low.values, d.close.values, d.open.values, d.sma20.values, d.w30x.values
    n = len(d); t = i0; out_t = None
    while t < n:
        if t > i0:
            if exit_next:
                proceeds += sell(op[t]) * qty; qty = 0; out_t = t; break
            if op[t] <= stop:
                proceeds += sell(op[t]) * qty; qty = 0; reason = "stop"; out_t = t; break
            if lo[t] <= stop:
                proceeds += sell(stop) * qty; qty = 0; reason = "stop"; out_t = t; break
            if two and not added and not half and hi[t] >= sg["add"]:
                px = max(op[t], sg["add"]); q2 = full - q1
                if q2 > 0: cost += buy(px) * q2; qty += q2; maxq = qty
                added = True; stop = max(stop, E)
            if not half and hi[t] >= E * 1.25:
                q = qty // 2; px = max(op[t], E * 1.25); proceeds += sell(px) * q; qty -= q; half = True
        else:
            if lo[t] <= stop:
                proceeds += sell(stop) * qty; qty = 0; reason = "stop"; out_t = t; break
        if t == i0:
            if expl: stop = max(stop, lo[t] * 0.999)
            if cl[t] < lo[t - 1]: exit_next = True; reason = "bday"
        if half and cl[t] < sma20[t] and not exit_next: exit_next = True; reason = "ma20"
        if w30x[t] and not exit_next: exit_next = True; reason = "w30"
        t += 1
    if qty > 0: proceeds += sell(cl[-1]) * qty; reason = "open"; out_t = n - 1
    pnl = proceeds - cost; r0 = (full if two else q1) * (E - S0)
    return {"sym": s, "i": sg["i"], "in": str(d.index[i0].date()), "out": "open" if reason == "open" else str(d.index[out_t].date()),
            "entry": round(E, 4), "stop0": round(S0, 4), "shape": sg["shape"], "ncons": sg["ncons"], "two": two, "added": added,
            "reason": reason, "pnl": round(pnl, 2), "R": round(pnl / r0, 3), "maxcost": round(maxq * max(E, sg["add"] or E), 2), "serve": sg["serve"]}

def stats(tr):
    if not tr: return {"trades": 0}
    w = [t for t in tr if t["pnl"] > 0]; gl = -sum(t["pnl"] for t in tr if t["pnl"] <= 0)
    eq = peak = dd = 0
    for t in sorted(tr, key=lambda x: x["out"]): eq += t["pnl"]; peak = max(peak, eq); dd = max(dd, peak - eq)
    return {"trades": len(tr), "win%": round(100 * len(w) / len(tr), 1), "expR": round(float(np.mean([t["R"] for t in tr])), 3),
            "net": round(sum(t["pnl"] for t in tr)), "pf": round(sum(t["pnl"] for t in w) / gl, 2) if gl > 0 else None, "maxDD": round(dd)}

def portfolio(sigs):
    res = []
    for sg in sigs:
        day_in = D[sg["sym"]].index[sg["i"] + 1]
        live = [t for t in res if t["out"] == "open" or pd.Timestamp(t["out"]) >= day_in]
        if any(t["sym"] == sg["sym"] for t in live) or len(live) >= MAXP: continue
        t = simulate(sg)
        if t is None or sum(x["maxcost"] for x in live) + t["maxcost"] > MAXINV: continue
        res.append(t)
    return res

out = {"market": MKT, "window": [str(START.date()), str(T.index[-1].date())], "universe": len(D), "variants": {}}
base_lvl = None
for v, (minc, pm, sm) in VARS.items():
    sigs = signals_for(minc, pm, sm)
    lvl = [t for t in (simulate(sg) for sg in sigs) if t]
    port = portfolio(sigs)
    out["variants"][v] = {"signals": len(sigs), "signal_level": stats(lvl), "portfolio": stats(port), "list": lvl}
    if v == "R0": base_lvl = {(t["sym"], t["i"]): t for t in lvl}
    else:
        cur = {(t["sym"], t["i"]): t for t in lvl}
        changed = [t for k, t in cur.items() if k not in base_lvl or (base_lvl[k]["entry"], base_lvl[k]["stop0"], base_lvl[k]["two"]) != (t["entry"], t["stop0"], t["two"])]
        dropped = [t for k, t in base_lvl.items() if k not in cur]
        out["variants"][v]["changed"] = stats(changed); out["variants"][v]["dropped_from_R0"] = stats(dropped)
json.dump(out, open(os.path.join(OUT, f"readings_{MKT}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
print(MKT, out["window"], "universe", out["universe"])
for v, x in out["variants"].items():
    print(v, "sig", x["signals"], "| LVL", x["signal_level"], "| PORT", x["portfolio"], "| CHG", x.get("changed"), "| DROP", x.get("dropped_from_R0"))
