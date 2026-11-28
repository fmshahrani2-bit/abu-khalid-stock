"""diag_path.py — تحليل حركة السعر بعد الدخول حسب reports/.../round2/DIAG_PATH_SPEC.md. وصفي فقط.
الاستخدام: python3 diag_path.py → out/diag_path_us_v1.1.json
v1.1 (2026-11-28): بعد مراجعة ChatGPT:
(1) صفقات فترة الاختيار تُقطع عند إغلاق 2026-02-27، وما بعده لا يدخل في MFE/MAE ولا في التصنيف (المفتوحة عنده "مفتوحة").
(2) ما بعد الوقف بأفقين ثابتين 20 و40 جلسة، مع وسم الصفقات التي لم يكتمل أفقها.
(3) أيام اجتمع فيها بلوغ +25% (هدف البيع الجزئي) والوقف في الشمعة نفسها، لأن ترتيبهما داخل الجلسة غير معروف.
(4) الخاسرة التي بلغت +1R تُعرض صفقةً صفقة.
"""
import os, sys, json
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sys.argv = [sys.argv[0], "us"]
exec(open(os.path.join(HERE, "bt_readings.py"), encoding="utf-8").read().split('out = {"market"')[0])
SEL_END, VAL_START = "2026-02-27", "2026-03-02"
DED = json.load(open(os.path.join(OUT, "readings_us_dedup.json"), encoding="utf-8"))

def path(t, piv, cut=None):
    d = D[t["sym"]]; e = d.index.get_loc(pd.Timestamp(t["in"]))
    x = d.index.get_loc(pd.Timestamp(t["out"])) if t["out"] != "open" else len(d) - 1
    status = "closed" if t["out"] != "open" else "open"
    if cut is not None and d.index[x] > pd.Timestamp(cut):
        x = d.index.get_indexer([pd.Timestamp(cut)], method="ffill")[0]; status = "open_at_cut"
    seg = d.iloc[e:x + 1]; E, S = t["entry"], t["stop0"]; r = E - S
    hi_before = seg.high.values; lo = seg.low.values
    mfe = (hi_before.max() - E) / r; mae = (lo.min() - E) / r
    first5 = d.close.iloc[e:e + 5]
    if cut is not None: first5 = first5[first5.index <= pd.Timestamp(cut)]
    stopped = status == "closed" and t["reason"] == "stop"
    a20, a40 = d.iloc[x + 1:x + 21], d.iloc[x + 1:x + 41]
    both = int(((seg.high >= E * 1.25) & (seg.low <= S)).sum())
    return {"status": status, "MFE": round(float(mfe), 2), "MAE": round(float(mae), 2), "days": x - e, "stopped": stopped,
            "back_in_base5": bool((first5 < piv).any()), "entry_vs_pivot%": round((E / piv - 1) * 100, 2),
            "rec25_20": bool(stopped and len(a20) and a20.high.max() >= E * 1.25), "full20": len(a20) == 20,
            "rec25_40": bool(stopped and len(a40) and a40.high.max() >= E * 1.25), "full40": len(a40) == 40,
            "back_to_entry40": bool(stopped and len(a40) and a40.high.max() >= E), "same_bar_25_and_stop": both}

def summ(g):
    if not g: return {"n": 0}
    L = [t for t in g if t["stopped"]]
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
            "open_or_cut": sum(t["status"] != "closed" for t in g),
            "after_stop": {"rec25_20": sum(t["rec25_20"] for t in L), "full20": sum(t["full20"] for t in L),
                           "rec25_40": sum(t["rec25_40"] for t in L), "full40": sum(t["full40"] for t in L),
                           "back_to_entry40": sum(t["back_to_entry40"] for t in L)},
            "same_bar_25_and_stop_trades": sum(t["same_bar_25_and_stop"] > 0 for t in g),
            "losers_reached_1R_list": [{k: t[k] for k in ("sym", "in", "out", "MFE", "R", "days")} for t in L if t["MFE"] >= 1],
            "MFE_buckets": {b: sum(lo_ <= t["MFE"] < hi_ for t in g) for b, (lo_, hi_) in
                            {"<0.5R": (-9, .5), "0.5–1R": (.5, 1), "1–2R": (1, 2), "2–4R": (2, 4), "≥4R": (4, 99)}.items()}}

out = {}
for pool in ("R0", "A"):
    minc, pm, sm = VARS[pool]
    piv = {(s["sym"], s["i"]): s["pivot"] for s in signals_for(minc, pm, sm)}
    L = []
    for t in DED[pool]["list"]:
        x = dict(t); x.update(path(t, piv[(t["sym"], t["i"])], cut=SEL_END if t["in"] <= SEL_END else None)); L.append(x)
    per = {"select": [t for t in L if t["in"] <= SEL_END], "validate": [t for t in L if t["in"] >= VAL_START]}
    out[pool] = {p: summ(g) for p, g in per.items()}
    out[pool]["validate_trades"] = [{k: t[k] for k in ("sym", "in", "out", "status", "reason", "R", "MFE", "MAE", "days", "back_in_base5", "entry_vs_pivot%", "rec25_20", "full20", "rec25_40", "full40", "same_bar_25_and_stop")}
                                    for t in per["validate"]]
json.dump(out, open(os.path.join(OUT, "diag_path_us_v1.1.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
for pool in out:
    for p in ("select", "validate"): print(pool, p, json.dumps(out[pool][p], ensure_ascii=False))
