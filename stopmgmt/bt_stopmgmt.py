"""bt_stopmgmt.py v1.0.1 (v1.0 + مسار البيانات الطويلة ونقطة البداية فقط، بلا تغيير في القواعد) — اختبار إدارة الوقف V0–V4 حسب analysis/2026-11-27_BT_stop_mgmt_SPEC_v1.0.md
مبني على scripts/bt_2026.py (الفلترة) وscripts/vcp.py (الشكل والدخول والوقف) من commit b33695b دون تعديلهما.
الاستخدام: python3 bt_stopmgmt.py sa|us  → out/<mkt>_*.json
"""
import os, sys, json, glob, math, random
import numpy as np, pandas as pd

REPO = os.environ.get("REPO", "/home/claude/abu-khalid-stock")
SUF = os.environ.get("BT_SUFFIX", "")
VER = "v1.0.1" + SUF
sys.path.insert(0, os.path.join(REPO, "scripts"))
from vcp import detect

MKT = sys.argv[1] if len(sys.argv) > 1 else "sa"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out"); os.makedirs(OUT, exist_ok=True)
if MKT == "us":
    H, IDX, COM, WK, EXPLORE = os.path.join(REPO, "bt", "hist_us" + SUF), "SPX", 0.0005, "W-FRI", False
else:
    H, IDX, COM, WK, EXPLORE = os.path.join(REPO, "bt", "hist" + SUF), "TASI", 0.00178, "W-THU", True
BAL, RISK, CAP, MAXP, MAXINV = 100_000, 2_000, 100_000 / 6, 6, 80_000
VARIANTS, BUILDS = ["V0", "V1", "V2", "V3", "V4"], ["P", "Q"]

T = pd.read_csv(os.path.join(H, f"{IDX}.csv"), index_col=0, parse_dates=True)
T["sma50"] = T.close.rolling(50).mean()
serve = (T.close > T.sma50)

def prep(d):
    d = d.reindex(T.index).dropna().copy()
    d["sma20"] = d.close.rolling(20).mean(); d["sma150"] = d.close.rolling(150).mean(); d["sma200"] = d.close.rolling(200).mean()
    t = T.close.reindex(d.index)
    d["ok"] = ((d.close / d.close.shift(250) - 1 > .20) & (d.close > d.sma150) & (d.close > d.sma200) & (d.close > d.sma20)
               & (d.close / d.close.shift(21) - t / t.shift(21) > 0) & (d.close / d.close.shift(63) - t / t.shift(63) > 0))
    pc = d.close.shift(1)
    tr = pd.concat([d.high - d.low, (d.high - pc).abs(), (d.low - pc).abs()], axis=1).max(axis=1)
    d["atr14"] = tr.ewm(alpha=1 / 14, adjust=False).mean()           # Wilder
    wk = d.close.resample(WK).last().dropna(); w30 = wk.rolling(30).mean()
    last_day = d.index.to_series().resample(WK).last().dropna()        # آخر جلسة فعلية في كل أسبوع
    flag = pd.Series(False, index=d.index)
    for wend, day in last_day.items():
        if wend in w30.index and not math.isnan(w30.loc[wend]) and wk.loc[wend] < w30.loc[wend]: flag.loc[day] = True
    d["w30x"] = flag
    return d

D = {}
for f in sorted(glob.glob(os.path.join(H, "*.csv"))):
    s = os.path.basename(f)[:-4]
    if s == IDX: continue
    d = pd.read_csv(f, index_col=0, parse_dates=True)
    if len(d) < 260: continue
    D[s] = prep(d)
START = T.index[250] if SUF else pd.Timestamp("2025-07-01"); days = [x for x in T.index if x >= START]

# ---------- 1) الإشارات (ثابتة في كل النسخ) ----------
signals = []   # (يوم الإشارة، السهم، pivot، stop، shape)
for s, d in D.items():
    idx = d.index
    for i in range(250, len(d) - 1):
        if idx[i] < START or not d.ok.iloc[i]: continue
        w = d.iloc[max(0, i - 129): i + 1]
        sh = detect(*(w[x].tolist() for x in ("open", "high", "low", "close", "volume")))
        if sh["shape"] not in ("VCP", "شيك أوت"): continue
        piv, stop = sh["pivot"], sh["stop"]
        if not (d.close.iloc[i] < piv and (piv - stop) / piv < 0.10): continue
        trig = max(piv, d.high.iloc[i] * 1.001)
        if trig > piv * 1.03: continue
        r = d.iloc[i + 1]
        if r.high >= trig and r.open <= piv * 1.03:
            entry = max(r.open, trig)
            if entry > stop:
                signals.append({"sym": s, "i": i, "day": idx[i], "pivot": piv, "stop": stop, "entry": entry, "shape": sh["shape"],
                                "serve": bool(serve.loc[idx[i]])})
signals.sort(key=lambda x: (x["day"], x["sym"]))

# ---------- 2) محاكاة صفقة واحدة ----------
def simulate(sg, variant, build, slip):
    s = sg["sym"]; d = D[s]; i0 = sg["i"] + 1; E, S0, piv = sg["entry"], sg["stop"], sg["pivot"]
    expl = (not sg["serve"]) and EXPLORE
    if (not sg["serve"]) and not EXPLORE: return None             # الأمريكي: لا دخول تحت متوسط 50
    full = int(min(RISK / (E - S0), CAP / E))
    q1 = int(full * 0.2) if (build == "Q" or expl) else full
    if q1 <= 0: return None
    buy = lambda px: px * (1 + slip) * (1 + COM); sell = lambda px: px * (1 - slip) * (1 - COM)
    legs = [("B", d.index[i0], E, q1)]; qty, cost, proceeds = q1, buy(E) * q1, 0.0
    stop, half, adds, exit_next, reason = S0, False, 0, False, None
    hi, lo, cl, op = d.high.values, d.low.values, d.close.values, d.open.values
    sma20, atr, w30x = d.sma20.values, d.atr14.values, d.w30x.values
    maxq, moved = q1, []
    # V2 state
    p1, retest, hpre = False, False, None
    # V3/V4 state
    pend = []    # [(index, L, high_before)]
    n = len(d); t = i0
    while t < n:
        if t > i0:
            if exit_next:
                px = sell(op[t]); legs.append(("S", d.index[t], op[t], qty)); proceeds += px * qty; qty = 0; break
            if op[t] <= stop:
                legs.append(("S", d.index[t], op[t], qty)); proceeds += sell(op[t]) * qty; qty = 0; reason = "stop"; break
            if lo[t] <= stop:
                legs.append(("S", d.index[t], stop, qty)); proceeds += sell(stop) * qty; qty = 0; reason = "stop"; break
            if build == "Q" and not expl and not half and serve.loc[d.index[t - 1]]:
                for lvl in (1.10, 1.20):
                    k = 1 if lvl == 1.10 else 2
                    if adds < k and hi[t] >= E * lvl:
                        px = max(op[t], E * lvl); q = int(full * 0.2)
                        if q > 0: legs.append(("B", d.index[t], px, q)); cost += buy(px) * q; qty += q; maxq = max(maxq, qty)
                        adds = k
            if not half and hi[t] >= E * 1.25:
                q = qty // 2; px = max(op[t], E * 1.25)
                legs.append(("S", d.index[t], px, q)); proceeds += sell(px) * q; qty -= q; half = True
        else:   # يوم الدخول: الوقف أثناء الجلسة بعد الدخول
            if lo[t] <= stop:
                legs.append(("S", d.index[t], stop, qty)); proceeds += sell(stop) * qty; qty = 0; reason = "stop"; break
        # ---- إغلاق اليوم t ----
        if t == i0:
            if expl: stop = max(stop, lo[t] * 0.999)
            if cl[t] < lo[t - 1]: exit_next = True; reason = "bday"          # يوم الاختراق يغلق تحت قاع اليوم السابق
        if half and cl[t] < sma20[t] and not exit_next: exit_next = True; reason = "ma20"
        if w30x[t] and not exit_next: exit_next = True; reason = "w30"
        old = stop
        if variant == "V1" and cl[t] > piv * 1.03: stop = max(stop, E)
        if variant == "V2":
            if not p1 and hi[t] >= piv * 1.03: p1 = True; hmax = hi[t]
            elif p1 and not retest:
                if lo[t] <= piv * 1.03: retest = True; hpre = hmax
                else: hmax = max(hmax, hi[t])
            if retest and hpre is not None and cl[t] > hpre: stop = max(stop, E)
        if variant in ("V3", "V4"):
            m = t - 1
            if m - 1 >= i0 and lo[m] < lo[m - 1] and lo[m] < lo[t]:          # قاع مؤكد (S11-01) بعد إغلاق الشمعة التالية
                pend.append((m, lo[m], hi[i0:m + 1].max()))
            keep = []
            for (m_, L, hb) in pend:
                if lo[t] < L: continue                                         # كُسر القاع فيُلغى
                if t > m_ and cl[t] > hb:
                    stop = max(stop, L * 0.999 if variant == "V3" else L - atr[t])
                else: keep.append((m_, L, hb))
            pend = keep
        if stop > old: moved.append((str(d.index[t].date()), round(stop, 4)))
        t += 1
    out_day = legs[-1][1] if qty == 0 else None
    if qty > 0:  # مفتوح: تقييم بآخر إغلاق
        proceeds += sell(cl[-1]) * qty; reason = "open"
    pnl = proceeds - cost; r0 = q1 * (E - S0)
    j_exit = d.index.get_loc(out_day) if out_day is not None else n - 1
    after25 = bool(reason == "stop" and hi[j_exit + 1: j_exit + 21].max(initial=0) >= E * 1.25) if j_exit + 1 < n else False
    return {"sym": s, "in": str(d.index[i0].date()), "out": str(out_day.date()) if out_day is not None else "open", "entry": round(E, 4),
            "stop0": round(S0, 4), "stop_last": round(stop, 4), "q1": q1, "maxq": maxq, "adds": adds, "half": half, "reason": reason,
            "pnl": round(pnl, 2), "R": round(pnl / r0, 3), "days": j_exit - i0, "stop_then_25": after25, "serve": sg["serve"],
            "maxcost": round(maxq * E, 2), "moves": moved, "legs": [(a, str(b.date()), round(c, 4), q) for a, b, c, q in legs]}

def stats(tr):
    if not tr: return {"trades": 0}
    w = [t for t in tr if t["pnl"] > 0]; l = [t for t in tr if t["pnl"] <= 0]
    eq = peak = dd = 0
    for t in sorted(tr, key=lambda x: x["out"]): eq += t["pnl"]; peak = max(peak, eq); dd = max(dd, peak - eq)
    gl = -sum(t["pnl"] for t in l)
    per = {}
    for t in tr:
        y = t["in"][:4] + ("H1" if int(t["in"][5:7]) <= 6 else "H2"); per.setdefault(y, []).append(t)
    return {"trades": len(tr), "win%": round(100 * len(w) / len(tr), 1), "expR": round(np.mean([t["R"] for t in tr]), 3),
            "net": round(sum(t["pnl"] for t in tr)), "ret%": round(100 * sum(t["pnl"] for t in tr) / BAL, 2),
            "pf": round(sum(t["pnl"] for t in w) / gl, 2) if gl > 0 else None, "maxDD": round(dd), "avg_days": round(np.mean([t["days"] for t in tr]), 1),
            "stop_exits": sum(t["reason"] == "stop" for t in tr), "stop_then_25": sum(t["stop_then_25"] for t in tr),
            "adds": sum(t["adds"] for t in tr), "open": sum(t["out"] == "open" for t in tr),
            "periods": {k: [len(v), round(np.mean([t["R"] for t in v]), 3), round(sum(t["pnl"] for t in v))] for k, v in sorted(per.items())}}

def portfolio(variant, build, slip):
    trades = {}; res = []
    for sg in signals:
        if sg["sym"] in trades and trades[sg["sym"]]["out"] in ("open",) : continue
        day_in = D[sg["sym"]].index[sg["i"] + 1]
        live = [t for t in res if t["out"] == "open" or pd.Timestamp(t["out"]) >= day_in]
        if any(t["sym"] == sg["sym"] for t in live): continue
        if len(live) >= MAXP: continue
        t = simulate(sg, variant, build, slip)
        if t is None: continue
        if sum(x["maxcost"] for x in live) + t["maxcost"] > MAXINV: continue
        res.append(t)
    return res

def boot(a, b, n=10000, seed=7):
    rng = np.random.default_rng(seed); dlt = np.array(a) - np.array(b)
    if len(dlt) == 0: return None
    m = rng.choice(dlt, (n, len(dlt)), replace=True).mean(axis=1)
    return [round(float(dlt.mean()), 3), round(float(np.percentile(m, 2.5)), 3), round(float(np.percentile(m, 97.5)), 3)]

out = {"market": MKT, "window": [str(START.date()), str(T.index[-1].date())], "universe": len(D), "signals": len(signals),
       "signals_serve": sum(s["serve"] for s in signals), "idx": [round(T.close.loc[days[0]], 2), round(T.close.iloc[-1], 2)],
       "idx_serve_days": int(serve.loc[days].sum()), "days": len(days), "portfolio": {}, "signal_level": {}, "paired": {}, "sensitivity": {}}
for b in BUILDS:
    for v in VARIANTS:
        tr = portfolio(v, b, 0.001); out["portfolio"][f"{v}_{b}"] = {"stats": stats(tr), "list": tr}
    lvl = {v: [simulate(sg, v, b, 0.001) for sg in signals] for v in VARIANTS}
    for v in VARIANTS:
        tr = [t for t in lvl[v] if t]; out["signal_level"][f"{v}_{b}"] = {"stats": stats(tr), "list": tr}
    base = [t["R"] for t in lvl["V0"] if t]
    for v in VARIANTS[1:]:
        out["paired"][f"{v}_{b}"] = boot([t["R"] for t in lvl[v] if t], base)
for slip in (0.0, 0.0025):
    for v in VARIANTS:
        out["sensitivity"][f"{v}_P_slip{slip}"] = stats(portfolio(v, "P", slip))
json.dump(out, open(os.path.join(OUT, f"{MKT}_{VER}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
print(json.dumps({k: v for k, v in out.items() if k not in ("portfolio", "signal_level", "sensitivity")}, ensure_ascii=False))
for k in ("portfolio", "signal_level"):
    for kk, vv in out[k].items():
        st = {x: y for x, y in vv["stats"].items() if x != "periods"}; print(k, kk, st, vv["stats"].get("periods"))
for kk, vv in out["sensitivity"].items(): print("sens", kk, {x: vv.get(x) for x in ("trades", "expR", "net", "pf", "maxDD")})
