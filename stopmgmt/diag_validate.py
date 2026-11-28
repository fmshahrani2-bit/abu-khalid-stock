"""diag_validate.py — تشخيص وصفي لخسارة فترة التحقق حسب reports/.../round2/DIAG_VALIDATE_SPEC.md.
لا يغيّر أي صفقة ولا يحذف أي خاسرة. يقرأ out/readings_us_dedup.json ويضيف خصائص يوم الإشارة فقط.
الاستخدام: python3 diag_validate.py → out/diag_validate_us.json وطباعة الجداول.
"""
import os, sys, json
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.argv = [sys.argv[0], "us"]
exec(open(os.path.join(HERE, "bt_readings.py"), encoding="utf-8").read().split('out = {"market"')[0])
T["sma200"] = T.close.rolling(200).mean()
SEL_END, VAL_START = "2026-02-27", "2026-03-02"
DED = json.load(open(os.path.join(OUT, "readings_us_dedup.json"), encoding="utf-8"))

def enrich(t):
    d = D[t["sym"]]; i = t["i"]; day = d.index[i]; t_ = T.close.reindex(d.index)
    e = d.index[i + 1]; trig_open = float(d.open.iloc[i + 1])
    x = dict(t)
    x.update({"month": str(e)[:7], "stop_pct": (t["entry"] - t["stop0"]) / t["entry"] * 100,
              "idx_vs50": float(T.close.loc[day] / T.sma50.loc[day] - 1) * 100, "idx_above200": bool(T.close.loc[day] > T.sma200.loc[day]),
              "idx_r21": float(T.close.loc[day] / T.close.iloc[T.index.get_loc(day) - 21] - 1) * 100,
              "RS21": float(d.close.iloc[i] / d.close.iloc[i - 21] - t_.iloc[i] / t_.iloc[i - 21]) * 100,
              "RS63": float(d.close.iloc[i] / d.close.iloc[i - 63] - t_.iloc[i] / t_.iloc[i - 63]) * 100,
              "px_vs50": float(d.close.iloc[i] / d.close.iloc[max(0, i - 49): i + 1].mean() - 1) * 100,
              "gap_entry": bool(trig_open >= t["entry"] - 1e-9 and trig_open > d.high.iloc[i] * 1.001),
              "days_held": (len(d.loc[e:]) if t["out"] == "open" else len(d.loc[e:t["out"]])) - 1})
    return x

def st(g):
    if not g: return {"n": 0}
    R = [t["R"] for t in g]; P = [t["pnl"] for t in g]; w = [r for r in R if r > 0]; l = [r for r in R if r <= 0]
    gl = -sum(p for p in P if p <= 0); eq = pk = dd = 0
    for t in sorted(g, key=lambda t: (t["out"] == "open", t["out"])): eq += t["pnl"]; pk = max(pk, eq); dd = max(dd, pk - eq)
    return {"n": len(g), "win": len(w), "loss": len(l), "net": round(sum(P)), "expR": round(float(np.mean(R)), 2),
            "pf": round(sum(p for p in P if p > 0) / gl, 2) if gl > 0 else None, "avgW": round(float(np.mean(w)), 2) if w else None,
            "avgL": round(float(np.mean(l)), 2) if l else None, "maxDD": round(dd), "small": len(g) < 10}

def tert(vals):
    return np.percentile(vals, [33.3, 66.7]) if len(vals) >= 3 else [np.nan, np.nan]

AXES = {
    "shape": lambda t: t["shape"],
    "ncons": lambda t: "شيك أوت" if t["shape"] != "VCP" else ("2" if t["ncons"] == 2 else "3" if t["ncons"] == 3 else "4+"),
    "stop_pct": lambda t: "<4%" if t["stop_pct"] < 4 else "4–6%" if t["stop_pct"] < 6 else "≥6%",
    "idx_above200": lambda t: "فوق 200" if t["idx_above200"] else "تحت 200",
    "idx_r21": lambda t: "سالب" if t["idx_r21"] < 0 else "0–3%" if t["idx_r21"] <= 3 else ">3%",
    "idx_vs50": lambda t: "<2%" if t["idx_vs50"] < 2 else "2–4%" if t["idx_vs50"] < 4 else "≥4%",
    "month": lambda t: t["month"],
    "gap_entry": lambda t: "دخول بفجوة" if t["gap_entry"] else "دون فجوة",
    "reason": lambda t: t["reason"],
}
out = {}
for pool in ("R0", "A"):
    L = [enrich(t) for t in DED[pool]["list"]]
    per = {"select": [t for t in L if t["in"] <= SEL_END], "validate": [t for t in L if t["in"] >= VAL_START]}
    # أثلاث القوة النسبية والبعد عن متوسط 50 تُحسب من الفترتين معاً حتى تكون الحدود واحدة
    cuts = {k: tert([t[k] for t in L]) for k in ("RS21", "RS63", "px_vs50")}
    axes = dict(AXES)
    for k, (a, b) in cuts.items():
        axes[k] = (lambda k, a, b: lambda t: f"أدنى ثلث (<{a:.1f})" if t[k] < a else f"الأوسط" if t[k] < b else f"أعلى ثلث (≥{b:.1f})")(k, a, b)
    res = {"cuts": {k: [round(float(v), 2) for v in c] for k, c in cuts.items()}}
    for pname, g in per.items():
        r = {"all": st(g), "big_loss_gt1R": sum(t["R"] < -1.05 for t in g),
             "avg_days_held": round(float(np.mean([t["days_held"] for t in g])), 1) if g else None,
             "idx_mean": {k: round(float(np.mean([t[k] for t in g])), 2) for k in ("idx_vs50", "idx_r21", "RS21", "RS63", "px_vs50", "stop_pct")} if g else {}}
        for ax, f in axes.items():
            grp = {}
            for t in g: grp.setdefault(f(t), []).append(t)
            r[ax] = {k: st(v) for k, v in sorted(grp.items())}
        res[pname] = r
    res["validate_trades"] = [{k: (round(v, 2) if isinstance(v, float) else v) for k, v in t.items()
                               if k in ("sym", "in", "out", "shape", "ncons", "reason", "R", "pnl", "stop_pct", "idx_vs50", "idx_r21", "RS21", "RS63", "gap_entry", "days_held")}
                              for t in per["validate"]]
    out[pool] = res
json.dump(out, open(os.path.join(OUT, "diag_validate_us.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
for pool, res in out.items():
    print("=====", pool, "cuts", res["cuts"])
    for p in ("select", "validate"):
        r = res[p]; print("--", p, r["all"], "big<-1R", r["big_loss_gt1R"], "days", r["avg_days_held"], r["idx_mean"])
        for ax in AXES.keys() | {"RS21", "RS63", "px_vs50"}:
            print("   ", ax, {k: (v["n"], v["win"], v["net"], v["expR"], v["pf"]) for k, v in r[ax].items()})
