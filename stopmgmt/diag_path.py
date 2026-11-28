"""diag_path.py — تحليل حركة السعر بعد الدخول حسب reports/.../round2/DIAG_PATH_SPEC.md. وصفي فقط.
الاستخدام: python3 diag_path.py → out/diag_path_us.json
"""
import os, sys, json
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.argv = [sys.argv[0], "us"]
exec(open(os.path.join(HERE, "bt_readings.py"), encoding="utf-8").read().split('out = {"market"')[0])
SEL_END, VAL_START = "2026-02-27", "2026-03-02"
DED = json.load(open(os.path.join(OUT, "readings_us_dedup.json"), encoding="utf-8"))

def path(t, piv):
    d = D[t["sym"]]; e = d.index.get_loc(pd.Timestamp(t["in"]))
    x = d.index.get_loc(pd.Timestamp(t["out"])) if t["out"] != "open" else len(d) - 1
    seg = d.iloc[e:x + 1]; E, S = t["entry"], t["stop0"]; r = E - S
    hi_before = seg.high.values; lo = seg.low.values
    mfe = (hi_before.max() - E) / r; mae = (lo.min() - E) / r
    first5 = d.close.iloc[e:e + 5]
    after = d.iloc[x + 1:x + 41]
    return {"MFE": round(float(mfe), 2), "MAE": round(float(mae), 2), "days": x - e,
            "back_in_base5": bool((first5 < piv).any()), "entry_vs_pivot%": round((E / piv - 1) * 100, 2),
            "stop_then_25": bool(t["reason"] == "stop" and len(after) and after.high.max() >= E * 1.25)}

def summ(g):
    if not g: return {"n": 0}
    L = [t for t in g if t["reason"] == "stop"]
    med = lambda k, G: round(float(np.median([t[k] for t in G])), 2) if G else None
    mean = lambda k, G: round(float(np.mean([t[k] for t in G])), 2) if G else None
    return {"n": len(g), "stops": len(L),
            "MFE_med_all": med("MFE", g), "MFE_mean_all": mean("MFE", g), "MAE_med_all": med("MAE", g),
            "losers_MFE_med": med("MFE", L), "losers_immediate(<0.5R)": sum(t["MFE"] < 0.5 for t in L),
            "losers_reached_1R": sum(t["MFE"] >= 1 for t in L), "losers_reached_2R": sum(t["MFE"] >= 2 for t in L),
            "losers_days_to_stop_med": med("days", L), "losers_days_to_stop_mean": mean("days", L),
            "back_in_base5_all": sum(t["back_in_base5"] for t in g), "back_in_base5_losers": sum(t["back_in_base5"] for t in L),
            "back_in_base5_winners_R": mean("R", [t for t in g if t["back_in_base5"]]),
            "no_back_in_base5_R": mean("R", [t for t in g if not t["back_in_base5"]]),
            "entry_vs_pivot_med%": med("entry_vs_pivot%", g),
            "entry_far(>1.5%)_R": mean("R", [t for t in g if t["entry_vs_pivot%"] > 1.5]), "entry_far_n": sum(t["entry_vs_pivot%"] > 1.5 for t in g),
            "entry_near(<=1.5%)_R": mean("R", [t for t in g if t["entry_vs_pivot%"] <= 1.5]),
            "stop_then_25": sum(t["stop_then_25"] for t in L),
            "MFE_buckets": {b: sum(lo_ <= t["MFE"] < hi_ for t in g) for b, (lo_, hi_) in
                            {"<0.5R": (-9, .5), "0.5–1R": (.5, 1), "1–2R": (1, 2), "2–4R": (2, 4), "≥4R": (4, 99)}.items()}}

out = {}
for pool in ("R0", "A"):
    minc, pm, sm = VARS[pool]
    piv = {(s["sym"], s["i"]): s["pivot"] for s in signals_for(minc, pm, sm)}
    L = []
    for t in DED[pool]["list"]:
        x = dict(t); x.update(path(t, piv[(t["sym"], t["i"])])); L.append(x)
    per = {"select": [t for t in L if t["in"] <= SEL_END], "validate": [t for t in L if t["in"] >= VAL_START]}
    out[pool] = {p: summ(g) for p, g in per.items()}
    out[pool]["validate_trades"] = [{k: t[k] for k in ("sym", "in", "out", "reason", "R", "MFE", "MAE", "days", "back_in_base5", "entry_vs_pivot%", "stop_then_25")}
                                    for t in per["validate"]]
json.dump(out, open(os.path.join(OUT, "diag_path_us.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
for pool in out:
    for p in ("select", "validate"): print(pool, p, json.dumps(out[pool][p], ensure_ascii=False))
