"""فحص اكتمال البيانات الطويلة قبل الاختبار (ملحق المواصفات). بيانات فقط."""
import glob, os, json, collections, numpy as np, pandas as pd
REPO = os.environ["REPO"]; out = {}
for d, idx, cur in [("hist_long", "TASI", "hist"), ("hist_us_long", "SPX", "hist_us")]:
    D = os.path.join(REPO, "bt", d); T = pd.read_csv(os.path.join(D, f"{idx}.csv"), index_col=0, parse_dates=True)
    fs = glob.glob(os.path.join(D, "*.csv")); short = 0; st = collections.Counter(); en = collections.Counter(); diff = []; nanrows = 0
    for f in fs:
        x = pd.read_csv(f, index_col=0, parse_dates=True); short += len(x) < 260; st[str(x.index[0].year)] += 1; en[str(x.index[-1].date())] += 1
        nanrows += int(x.isna().any(axis=1).sum())
        c = os.path.join(REPO, "bt", cur, os.path.basename(f))
        if os.path.exists(c):
            y = pd.read_csv(c, index_col=0, parse_dates=True); j = x.close.reindex(y.index).dropna()
            if len(j) > 100: diff.append(float((j / y.close.reindex(j.index) - 1).abs().median()))
    out[d] = {"index": idx, "index_first": str(T.index[0].date()), "index_last": str(T.index[-1].date()), "index_bars": len(T),
              "signal_start": str(T.index[250].date()), "files": len(fs), "under_260": short, "nan_rows": nanrows,
              "start_years": dict(sorted(st.items())), "last_dates_top": en.most_common(3),
              "vs_repo_600bar_median_abs_close_diff": float(np.median(diff)) if diff else None, "vs_repo_max": max(diff) if diff else None, "vs_repo_n": len(diff)}
os.makedirs(os.path.join(REPO, "stopmgmt", "out"), exist_ok=True)
json.dump(out, open(os.path.join(REPO, "stopmgmt", "out", "datacheck.json"), "w"), indent=1)
print(json.dumps(out, indent=1))
