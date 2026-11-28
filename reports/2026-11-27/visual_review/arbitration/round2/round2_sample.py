"""round2_sample.py — جولة التحكيم الأعمى الثانية (2026-11-28). لا يحسب أي بيانات بعد يوم القرار.
العينة: 15 حالة لكل سوق من bt/hist و bt/hist_us. يوم القرار بين 2025-07-01 و2026-08-31.
طبقتان لكل سوق (تُختم في جدول الربط): A = 8 أيام وجد فيها الكاشف الآلي VCP أو شيك أوت والإغلاق بين -5% و+3% من نقطة الدخول؛
B = 7 أيام عشوائية اجتازت فلتر المرحلة 2. سهم واحد لكل حالة في السوق. تُستبعد أسهم الحالات الستين السابقة إن كان يوم القرار ضمن 180 يوماً من يومها."""
import os, sys, json, gzip, random, hashlib, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
REPO = "/home/claude/verify"; sys.path.insert(0, os.path.join(REPO, "scripts")); from vcp import detect
OUT = "/home/claude/round2"; rng = random.Random(20261128)
D0, D1 = pd.Timestamp("2025-07-01"), pd.Timestamp("2026-08-31")
prev = json.load(gzip.open("/home/claude/review/SEALED_key.json.gz", "rt"))
prev = [(v["sym"], pd.Timestamp(v["day"])) for v in prev.values()]
def prep(d, T):
    d = d[~d.index.duplicated()].reindex(T.index).dropna().copy()
    for k in (20, 50, 150, 200): d[f"s{k}"] = d.close.rolling(k).mean()
    t = T.close.reindex(d.index)
    d["ok"] = ((d.close / d.close.shift(250) - 1 > .20) & (d.close > d.s150) & (d.close > d.s200) & (d.close > d.s20)
               & (d.close / d.close.shift(21) - t / t.shift(21) > 0) & (d.close / d.close.shift(63) - t / t.shift(63) > 0))
    return d
def candles(ax, w):
    for k, (_, r) in enumerate(w.iterrows()):
        c = "#2e7d32" if r.close >= r.open else "#c62828"
        ax.plot([k, k], [r.low, r.high], c=c, lw=.6); ax.plot([k, k], [r.open, r.close], c=c, lw=2.2)
def blind(cid, d, T, i, mkt):
    w = d.iloc[max(0, i - 159):i + 1]; tw = T.loc[w.index]; x = range(len(w))
    fig = plt.figure(figsize=(12, 7)); g = fig.add_gridspec(4, 1, height_ratios=[4, 1, 1.2, .05], hspace=.25)
    ax = fig.add_subplot(g[0]); candles(ax, w)
    for k, c in ((20, "orange"), (50, "blue"), (150, "purple"), (200, "black")): ax.plot(x, w[f"s{k}"].values, c=c, lw=.9, label=f"SMA{k}")
    ax.legend(loc="upper left", fontsize=7); ax.grid(alpha=.3); ax.set_xlim(-1, len(w) + 3)
    ax.set_title(f"Case {cid} | market {mkt.upper()} | daily, last {len(w)} bars | LAST BAR = DECISION DAY (nothing after it)", fontsize=10)
    ax.yaxis.set_major_locator(plt.MaxNLocator(14)); ax.tick_params(labelsize=8)
    av = fig.add_subplot(g[1], sharex=ax); av.bar(x, w.volume.values, color="gray"); av.plot(x, w.volume.rolling(50).mean().values, c="blue", lw=.8); av.tick_params(labelsize=7); av.set_ylabel("vol", fontsize=7)
    ai = fig.add_subplot(g[2], sharex=ax); ai.plot(x, tw.close.values, c="k", lw=.9); ai.plot(x, tw.s50.values, c="blue", lw=.7); ai.plot(x, tw.s200.values, c="red", lw=.7)
    ai.set_ylabel("index", fontsize=7); ai.tick_params(labelsize=7); ai.set_xticks([])
    for a_ in (ax, av): a_.set_xticks([])
    fig.savefig(os.path.join(OUT, "charts", f"{cid}.png"), dpi=80, bbox_inches="tight"); plt.close()
cases = []
for mkt, H, IDX in (("sa", "hist", "TASI"), ("us", "hist_us", "SPX")):
    H = os.path.join(REPO, "bt", H); T = pd.read_csv(os.path.join(H, f"{IDX}.csv"), index_col=0, parse_dates=True)
    T = T[~T.index.duplicated()]; T["s50"] = T.close.rolling(50).mean(); T["s200"] = T.close.rolling(200).mean()
    pool = {}
    for f in sorted(os.listdir(H)):
        s = f[:-4]
        if not f.endswith(".csv") or s == IDX: continue
        try: d = prep(pd.read_csv(os.path.join(H, f), index_col=0, parse_dates=True), T)
        except Exception: continue
        if len(d) < 260: continue
        days = [dt for dt in d.index[d.ok] if D0 <= dt <= D1 and not any(ps == s and abs((dt - pdt).days) <= 180 for ps, pdt in prev)]
        if days: pool[s] = (d, days)
    syms = sorted(pool); rng.shuffle(syms); A, B = [], []
    for s in syms:
        d, days = pool[s]
        if len(A) < 8:
            hit = None
            for dt in rng.sample(days, min(12, len(days))):
                i = d.index.get_loc(dt); w = d.iloc[max(0, i - 129):i + 1]
                sh = detect(*(w[x].tolist() for x in ("open", "high", "low", "close", "volume")))
                if sh["shape"] in ("VCP", "شيك أوت") and sh.get("pivot") and -.05 <= d.close.iloc[i] / sh["pivot"] - 1 <= .03:
                    hit = dt; break
            if hit is not None: A.append((s, hit)); continue
        if len(B) < 7: B.append((s, rng.choice(days)))
        if len(A) == 8 and len(B) == 7: break
    print(mkt, "pool stocks", len(pool), "A", len(A), "B", len(B))
    cases += [(mkt, "A", s, dt, pool[s][0], T) for s, dt in A] + [(mkt, "B", s, dt, pool[s][0], T) for s, dt in B]
rng.shuffle(cases); mp = {}
for n, (mkt, st, s, dt, d, T) in enumerate(cases, 1):
    cid = f"R-{n:02d}"; blind(cid, d, T, d.index.get_loc(dt), mkt)
    mp[cid] = {"market": mkt.upper(), "stratum": st, "sym": s, "decision_day": str(dt.date())}
sealed = {"salt": hashlib.sha256(os.urandom(16)).hexdigest()[:16], "map": mp}
b = json.dumps(sealed, ensure_ascii=False, sort_keys=True).encode()
open(os.path.join(OUT, "round2_map_SEALED.json"), "wb").write(b)
print("map sha256", hashlib.sha256(b).hexdigest())
