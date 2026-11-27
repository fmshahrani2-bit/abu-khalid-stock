"""review_sample.py — بروتوكول analysis/2026-11-27_visual_review_PROTOCOL.md. بلا تعديل لأي قاعدة. ينتج شارتات عمياء ومفتاحاً مختوماً."""
import os, sys, json, gzip, random, pandas as pd, numpy as np
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
REPO = os.environ["REPO"]; sys.path.insert(0, os.path.join(REPO, "scripts")); from vcp import detect
OUT = os.path.join(REPO, "stopmgmt", "review"); os.makedirs(OUT, exist_ok=True)
rng = random.Random(20261127); key = {}
def prep(d, T):
    d = d.reindex(T.index).dropna().copy()
    for k in (20, 50, 150, 200): d[f"s{k}"] = d.close.rolling(k).mean()
    t = T.close.reindex(d.index)
    d["ok"] = ((d.close / d.close.shift(250) - 1 > .20) & (d.close > d.s150) & (d.close > d.s200) & (d.close > d.s20)
               & (d.close / d.close.shift(21) - t / t.shift(21) > 0) & (d.close / d.close.shift(63) - t / t.shift(63) > 0))
    return d
def nextres(h, i, ref, tol=0.01):
    js = [j for j in range(1, i) if h[j] > h[j - 1] and h[j] > h[j + 1]]; lv = []
    for j in js:
        if h[j] <= ref: continue
        if any(abs(h[k] / h[j] - 1) <= tol and abs(k - j) >= 5 for k in js if k != j): lv.append(h[j])
    return min(lv) if lv else None
def candles(ax, w, x0=0):
    for k, (_, r) in enumerate(w.iterrows()):
        c = "#2e7d32" if r.close >= r.open else "#c62828"; x = x0 + k
        ax.plot([x, x], [r.low, r.high], c=c, lw=.6); ax.plot([x, x], [r.open, r.close], c=c, lw=2.2)
def blind(cid, d, T, i, mkt):
    a = max(0, i - 159); w = d.iloc[a:i + 1]; tw = T.loc[w.index]
    fig = plt.figure(figsize=(12, 7)); g = fig.add_gridspec(4, 1, height_ratios=[4, 1, 1.2, .05], hspace=.25)
    ax = fig.add_subplot(g[0]); candles(ax, w); x = range(len(w))
    for k, c in ((20, "orange"), (50, "blue"), (150, "purple"), (200, "black")): ax.plot(x, w[f"s{k}"].values, c=c, lw=.9, label=f"SMA{k}")
    ax.legend(loc="upper left", fontsize=7); ax.grid(alpha=.3); ax.set_xlim(-1, len(w) + 3)
    ax.set_title(f"Case {cid} | market {mkt.upper()} | daily, last {len(w)} bars | LAST BAR = DECISION DAY (nothing after it)", fontsize=10)
    ax.yaxis.set_major_locator(plt.MaxNLocator(14)); ax.tick_params(labelsize=8)
    av = fig.add_subplot(g[1], sharex=ax); av.bar(x, w.volume.values, color="gray"); av.plot(x, w.volume.rolling(50).mean().values, c="blue", lw=.8); av.tick_params(labelsize=7); av.set_ylabel("vol", fontsize=7)
    ai = fig.add_subplot(g[2], sharex=ax); ai.plot(x, tw.close.values, c="k", lw=.9); ai.plot(x, tw.s50.values, c="blue", lw=.7); ai.plot(x, tw.s200.values, c="red", lw=.7)
    ai.set_ylabel("index", fontsize=7); ai.tick_params(labelsize=7); ai.set_xticks([])
    for a_ in (ax, av): a_.set_xticks([])
    fig.savefig(os.path.join(OUT, f"{cid}.png"), dpi=80, bbox_inches="tight"); plt.close()
def reveal(cid, d, i, j_end, info):
    a = max(0, i - 100); b = min(len(d) - 1, j_end); w = d.iloc[a:b + 1]
    fig, ax = plt.subplots(figsize=(12, 5)); candles(ax, w); x = range(len(w))
    for k, c in ((20, "orange"), (50, "blue"), (200, "black")): ax.plot(x, w[f"s{k}"].values, c=c, lw=.8)
    ax.axvline(i - a, c="gray", ls="--", lw=.8)
    for k_, c_ in (("pivot", "green"), ("stop", "red"), ("res", "purple")):
        if info.get(k_): ax.axhline(info[k_], c=c_, ls=":", lw=1, label=f"system {k_} {info[k_]:.4g}")
    for s, dt, px, q in info.get("legs", []):
        xx = w.index.get_indexer([pd.Timestamp(dt)])[0]
        if xx >= 0: ax.scatter(xx, px, marker="^" if s == "B" else "v", c="k", s=50, zorder=5)
    ax.legend(fontsize=7, loc="upper left"); ax.grid(alpha=.3); ax.set_title(f"REVEAL {cid} | {info['sym']} | decision {info['day']} | {info['type']} | {info.get('outcome','')}", fontsize=9)
    fig.savefig(os.path.join(OUT, f"{cid}_reveal.png"), dpi=80, bbox_inches="tight"); plt.close()
for mkt, H, IDX in (("sa", "hist_long", "TASI"), ("us", "hist_us_long", "SPX")):
    H = os.path.join(REPO, "bt", H); T = pd.read_csv(os.path.join(H, f"{IDX}.csv"), index_col=0, parse_dates=True)
    T["s50"] = T.close.rolling(50).mean(); T["s200"] = T.close.rolling(200).mean(); START = T.index[250]
    o = json.load(gzip.open(os.path.join(REPO, "stopmgmt", "out", f"{mkt}_v1.0.1_long.json.gz"))); P = o["signal_level"]["V0_P"]["list"]; Q = o["signal_level"]["V0_Q"]["list"]
    RR = {(r["sym"], r["in"]): r for r in json.load(open(os.path.join(REPO, "stopmgmt", "out", f"rr_{mkt}_v1.0.json")))}
    ent = [(n, t) for n, t in enumerate(P) if RR[(t["sym"], t["in"])]["dedup"]]
    D = {}
    def ld(s):
        if s not in D: D[s] = prep(pd.read_csv(os.path.join(H, f"{s}.csv"), index_col=0, parse_dates=True), T)
        return D[s]
    sig_days = {(t["sym"], t["in"]) for t in P}
    # rejected pool: screen-passed stock-days without a system entry, one random day per (stock, month)
    pool = {}
    syms = sorted(f[:-4] for f in os.listdir(H) if f.endswith(".csv") and f[:-4] != IDX)
    for s in syms:
        d = ld(s)
        if len(d) < 260: continue
        okd = d.index[(d.ok) & (d.index >= START)]
        for dt in okd[:-1]:
            nxt = d.index[d.index.get_loc(dt) + 1]
            if (s, str(nxt.date())) in sig_days: continue
            pool.setdefault((s, dt.strftime("%Y-%m")), []).append(dt)
    rej_keys = sorted(pool); rng.shuffle(rej_keys)
    pick_e = rng.sample(ent, 15); pick_r = [(k[0], rng.choice(pool[k])) for k in rej_keys[:15]]
    cases = [("E", n, t["sym"], None) for n, t in pick_e] + [("R", None, s, dt) for s, dt in pick_r]
    rng.shuffle(cases)
    for c, (typ, n, s, dt) in enumerate(cases, 1):
        cid = f"{mkt.upper()}-{c:02d}"; d = ld(s)
        if typ == "E":
            t = P[n]; q = Q[n]; i = d.index.get_loc(pd.Timestamp(t["in"])) - 1; r = RR[(s, t["in"])]
            j_end = d.index.get_loc(pd.Timestamp(t["out"])) + 20 if t["out"] != "open" else len(d) - 1
            info = {"type": "SYSTEM ENTERED", "sym": s, "day": str(d.index[i].date()), "pivot": r["pivot"], "stop": t["stop0"], "res": r["res1"], "entry": t["entry"],
                    "rr": r["rr1"], "truncated": r["truncated"], "legs": t["legs"], "legs_Q": q["legs"], "R": t["R"], "R_Q": q["R"], "pnl": t["pnl"], "half": t["half"], "reason": t["reason"],
                    "out": t["out"], "serve": t["serve"], "outcome": f"R={t['R']} exit={t['reason']}"}
        else:
            i = d.index.get_loc(dt); w = d.iloc[max(0, i - 129): i + 1]
            sh = detect(*(w[x].tolist() for x in ("open", "high", "low", "close", "volume")))
            piv = sh.get("pivot"); res = nextres(d.high.values, i, piv) if piv else None
            why = sh["shape"] + ("; " + sh.get("note", "") if sh.get("note") else "")
            if sh["shape"] in ("VCP", "شيك أوت"):
                why += f"; close {d.close.iloc[i]:.4g} vs pivot {piv:.4g}; next day high {d.high.iloc[i+1]:.4g} open {d.open.iloc[i+1]:.4g}"
            j_end = min(len(d) - 1, i + 60); fut = d.iloc[i + 1:j_end + 1]
            info = {"type": "SYSTEM REJECTED", "sym": s, "day": str(d.index[i].date()), "pivot": piv, "stop": sh.get("stop"), "res": res, "why": why,
                    "max_up_60d%": round((fut.high.max() / d.close.iloc[i] - 1) * 100, 1), "max_dn_60d%": round((fut.low.min() / d.close.iloc[i] - 1) * 100, 1),
                    "outcome": f"next60d max +{(fut.high.max()/d.close.iloc[i]-1)*100:.0f}% / min {(fut.low.min()/d.close.iloc[i]-1)*100:.0f}%"}
        info["serve50"] = bool(T.close.loc[d.index[i]] > T.s50.loc[d.index[i]]); info["year"] = d.index[i].year
        blind(cid, d, T, i, mkt); reveal(cid, d, i, j_end, info); key[cid] = info
    print(mkt, "entered pool", len(ent), "rejected pool (stock-months)", len(pool))
json.dump(key, gzip.open(os.path.join(OUT, "SEALED_key.json.gz"), "wt"), default=str)
print("cases", len(key))
