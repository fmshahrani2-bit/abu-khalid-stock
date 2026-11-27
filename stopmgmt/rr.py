"""rr.py v1.0 — مواصفات analysis/2026-11-27_BT_RR_nextres_SPEC_v1.0.md
يحسب المقاومة التالية متعددة الملامسات لكل إشارة V0 من نتائج v1.0.1_long، ببيانات حتى يوم الإشارة فقط. لا يغيّر أي صفقة."""
import os, sys, json, gzip, pandas as pd, numpy as np
REPO = os.environ["REPO"]; sys.path.insert(0, os.path.join(REPO, "scripts")); from vcp import detect
MKT = sys.argv[1]
H, IDX = (os.path.join(REPO, "bt", "hist_us_long"), "SPX") if MKT == "us" else (os.path.join(REPO, "bt", "hist_long"), "TASI")
T = pd.read_csv(os.path.join(H, f"{IDX}.csv"), index_col=0, parse_dates=True); T0 = T.index[0]
o = json.load(gzip.open(os.path.join(REPO, "stopmgmt", "out", f"{MKT}_v1.0.1_long.json.gz")))
P = o["signal_level"]["V0_P"]["list"]; last = o["window"][1]
keep, busy = set(), {}
for i, t in sorted(enumerate(P), key=lambda x: (x[1]["in"], x[1]["sym"])):
    end = t["out"] if t["out"] != "open" else last
    if t["sym"] in busy and t["in"] <= busy[t["sym"]]: continue
    keep.add(i); busy[t["sym"]] = end
cache = {}
def load(s):
    if s not in cache:
        raw = pd.read_csv(os.path.join(H, f"{s}.csv"), index_col=0, parse_dates=True)
        cache[s] = (raw.reindex(T.index).dropna(), raw.index[0])
    return cache[s]
def nextres(h, i, ref, tol):
    js = [j for j in range(1, i) if h[j] > h[j - 1] and h[j] > h[j + 1]]   # قمة مؤكدة: j+1 <= i
    lv = []
    for j in js:
        if h[j] <= ref: continue
        if any(abs(h[k] / h[j] - 1) <= tol and abs(k - j) >= 5 for k in js if k != j): lv.append(h[j])
    return min(lv) if lv else None
out = []
for n, t in enumerate(P):
    d, first = load(t["sym"]); ie = d.index.get_loc(pd.Timestamp(t["in"])); i = ie - 1
    w = d.iloc[max(0, i - 129): i + 1]
    sh = detect(*(w[x].tolist() for x in ("open", "high", "low", "close", "volume")))
    piv = sh.get("pivot"); h = d.high.values
    trig = max(piv, h[i] * 1.001) if piv else None
    e_chk = max(d.open.iloc[ie], trig) if trig else None
    trunc = bool(first <= T0 + pd.Timedelta(days=10))
    rec = {"n": n, "sym": t["sym"], "in": t["in"], "dedup": n in keep, "pivot": piv, "stop0": t["stop0"], "entry": t["entry"],
           "entry_match": bool(e_chk is not None and abs(e_chk / t["entry"] - 1) < 1e-4), "truncated": trunc}
    for tol in (0.01, 0.02):
        r = nextres(h, i, piv, tol) if piv else None
        k = "1" if tol == 0.01 else "2"
        rec["res" + k] = r
        rec["rr" + k] = (r - piv) / (piv - t["stop0"]) if r else None
        rec["rr" + k + "_entry"] = (r - t["entry"]) / (t["entry"] - t["stop0"]) if r else None
    out.append(rec)
os.makedirs(os.path.join(REPO, "stopmgmt", "out"), exist_ok=True)
json.dump(out, open(os.path.join(REPO, "stopmgmt", "out", f"rr_{MKT}_v1.0.json"), "w"), indent=0, default=float)
print(MKT, len(out), "entry_match", sum(r["entry_match"] for r in out), "dedup", sum(r["dedup"] for r in out),
      "no_res", sum(r["res1"] is None for r in out if r["dedup"]), "trunc_nores", sum(r["res1"] is None and r["truncated"] for r in out if r["dedup"]))
