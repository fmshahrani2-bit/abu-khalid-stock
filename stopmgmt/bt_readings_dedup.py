"""bt_readings_dedup.py — يعيد إنتاج أرقام "بعد حذف التداخل" في BT_READINGS_RESULTS.md (تدقيق 2026-11-28).
القاعدة: تُرتب صفقات كل متغير حسب (الرمز، يوم الدخول). تُحذف أي صفقة يقع يوم دخولها قبل أو في يوم خروج صفقة سابقة لنفس السهم، أو أثناء صفقة ما زالت مفتوحة. لا سقف مراكز.
المدخل: out/readings_<mkt>.json. المخرج: out/readings_<mkt>_dedup.json وطباعة الجدول.
الاستخدام: python3 bt_readings_dedup.py us|sa
"""
import json, sys, os
import numpy as np
mkt = sys.argv[1] if len(sys.argv) > 1 else "us"
base = os.path.dirname(os.path.abspath(__file__))
V = json.load(open(os.path.join(base, "out", f"readings_{mkt}.json"), encoding="utf-8"))["variants"]
out = {}
for v, x in V.items():
    keep, last = [], {}
    for t in sorted(x["list"], key=lambda t: (t["sym"], t["in"])):
        o = last.get(t["sym"])
        if o and (o["out"] == "open" or t["in"] <= o["out"]): continue
        keep.append(t); last[t["sym"]] = t
    pn = [t["pnl"] for t in keep]; w = sum(p for p in pn if p > 0); l = -sum(p for p in pn if p <= 0)
    st = {"trades": len(keep), "net": round(sum(pn)), "expR": round(float(np.mean([t["R"] for t in keep])), 3) if keep else None,
          "pf": round(w / l, 2) if l else None, "removed": len(x["list"]) - len(keep)}
    out[v] = {"stats": st, "list": keep}
    print(mkt, v, st)
json.dump(out, open(os.path.join(base, "out", f"readings_{mkt}_dedup.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
