"""بيانات اليوم لكل سهم ذكره أبو خالد (picks/mentions.json) لمفاضلتها بمعاييره هو — بطلب المستخدم 2026-11-22.
يجمع الحقائق فقط (لا يرتّب): المرحلة الثانية، المتوسطات ونظرات العين (S80)، القوة النسبية، شروط درس الفلترة S16
(المبيعات، الربحية، الهامش، متوسط 20، 200، الحجم، القيمة السوقية، تاريخ الطرح)، البيتا (S31)، قوة القطاع أسبوعياً (S16 41:38)،
وشكل القاعدة (vcp.py). الحدود الرقمية لنظرات العين تقريب آلي معلن؛ الكورس يقول "بالنظر".
المخرج: picks/ranking_data.json"""
import json, os, sys, time, statistics, datetime as dt
import requests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vcp import detect
import tvDatafeed as tvd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
M = json.load(open(os.path.join(ROOT, "picks", "mentions.json"), encoding="utf-8"))
tv = tvd.TvDatafeed()

def r2(x):
    try: return None if x is None else round(float(x), 2)
    except Exception: return None

def hist(sym, ex, n=1500):
    for _ in range(2):
        try:
            d = tv.get_hist(sym, ex, tvd.Interval.in_daily, n_bars=n)
            if d is not None and len(d) > 30:
                d.index = d.index.normalize(); return d
        except Exception: pass
        time.sleep(1)
    return None

def bars(sym, market):
    for e in (["TADAWUL"] if market == "sa" else ["NASDAQ", "NYSE", "AMEX", "CBOE"]):
        d = hist(sym, e)
        if d is not None: return e, d
        time.sleep(0.3)
    return None, None

IDX = {"sa": hist("TASI", "TADAWUL"), "us": hist("SPX", "SP")}

def swing_lows(lo, k=3, n=90):
    lo = lo.iloc[-n:]
    vals = lo.tolist(); idx = lo.index.tolist()
    return [(idx[i], vals[i]) for i in range(k, len(vals) - k) if vals[i] == min(vals[i - k:i + k + 1])]

def perf(c, k): return (c.iloc[-1] / c.iloc[-1 - k] - 1) * 100 if len(c) > k else None

def features(d, idx):
    c, h, l, v, o = d["close"], d["high"], d["low"], d["volume"], d["open"]
    ma = {k: c.rolling(k).mean() for k in (9, 20, 21, 50, 150, 200)}
    last = lambda s, i=-1: (None if len(s) < abs(i) or s.iloc[i] != s.iloc[i] else float(s.iloc[i]))
    slope = lambda k, back: (None if last(ma[k]) is None or last(ma[k], -1 - back) is None else (last(ma[k]) / last(ma[k], -1 - back) - 1) * 100)
    x = float(c.iloc[-1])
    f = {"date": str(d.index[-1].date()), "close": r2(x), "bars": len(d), "first_bar": str(d.index[0].date()),
         **{f"sma{k}": r2(last(ma[k])) for k in ma},
         **{f"slope{k}": r2(slope(k, 5)) for k in (9, 21, 50, 200)}, "slope150_20d": r2(slope(150, 20)),
         "high52": r2(h.iloc[-252:].max()), "low52": r2(l.iloc[-252:].min())}
    f["from52h"] = r2((x / h.iloc[-252:].max() - 1) * 100)
    f["perf1m"], f["perf3m"], f["perfY"] = r2(perf(c, 21)), r2(perf(c, 63)), r2(perf(c, 252))
    if idx is not None:
        ic = idx["close"]
        f["idx_perf1m"], f["idx_perf3m"] = r2(perf(ic, 21)), r2(perf(ic, 63))
        f["idx_above50"] = bool(ic.iloc[-1] > ic.rolling(50).mean().iloc[-1])
        sl, il = swing_lows(l), swing_lows(idx["low"])
        f["stock_lows"] = [[str(a.date()), r2(b)] for a, b in sl[-3:]]
        f["index_lows"] = [[str(a.date()), r2(b)] for a, b in il[-3:]]
        f["higher_lows"] = bool(len(sl) >= 2 and sl[-1][1] > sl[-2][1])
        f["index_lower_lows"] = bool(len(il) >= 2 and il[-1][1] < il[-2][1])
        st_low, ix_low = l.iloc[-60:].idxmin(), idx["low"].iloc[-60:].idxmin()
        f["low60_date"], f["idx_low60_date"] = str(st_low.date()), str(ix_low.date())
        f["low_before_index"] = bool(st_low < ix_low)
        # كم نزل السهم من قمة 3 أشهر مقابل المؤشر (التعريف S26: المؤشر −5% والسهم −1–2%)
        f["dd3m"] = r2((x / h.iloc[-63:].max() - 1) * 100)
        f["idx_dd3m"] = r2((ic.iloc[-1] / idx["high"].iloc[-63:].max() - 1) * 100)
    chg = c.diff().iloc[-20:]; vv = v.iloc[-20:]
    upv, dnv = vv[chg > 0].mean(), vv[chg < 0].mean()
    f["upvol_dnvol"] = r2(upv / dnv) if upv == upv and dnv == dnv and dnv else None
    rng = lambda n: float(((h - l) / c).iloc[-n:].mean())
    f["range10_vs_50"] = r2(rng(10) / rng(50))
    f["avgvol50"] = r2(v.iloc[-50:].mean()); f["relvol"] = r2(v.iloc[-1] / v.iloc[-51:-1].mean())
    f["avg_dollar_vol50"] = r2((v * c).iloc[-50:].mean())
    try: f["shape"] = detect(o.tolist(), h.tolist(), l.tolist(), c.tolist(), v.tolist())
    except Exception as e: f["shape"] = {"shape": "خطأ", "note": str(e)[:80]}
    return f

syms = sorted({(m["sym"], m["market"]) for m in M})
out = {"computed": dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), "stocks": {}}
for s, mk in syms:
    ex, d = bars(s, mk)
    rec = {"sym": s, "market": mk, "exchange": ex, "mentions": [{"date": m["date"], "words": m["words"]} for m in M if m["sym"] == s and m["market"] == mk]}
    if d is None or len(d) < 60:
        rec["error"] = "بيانات سعرية غير كافية"
    else:
        try: rec.update(features(d, IDX[mk]))
        except Exception as e: rec["error"] = str(e)[:120]
    out["stocks"][f"{s}|{mk}"] = rec
    print(s, mk, rec.get("close"), rec.get("error", ""))

# من سكنر TradingView: البيتا، القيمة السوقية، الأرقام المالية الثلاثة، القطاع، موعد النتائج
FC = ["beta_1_year", "market_cap_basic", "total_revenue_yoy_growth_fq", "earnings_per_share_diluted_yoy_growth_fq", "gross_margin_ttm",
      "gross_margin", "net_margin_ttm", "earnings_release_date", "earnings_release_next_date", "sector", "industry", "Perf.W", "type", "description"]
ts = lambda t: dt.datetime.utcfromtimestamp(t).strftime("%Y-%m-%d") if t else None
URL = {"sa": "https://scanner.tradingview.com/ksa/scan", "us": "https://scanner.tradingview.com/america/scan"}
for mk in ("sa", "us"):
    tick = [f"{v['exchange']}:{v['sym']}" for v in out["stocks"].values() if v["market"] == mk and v.get("exchange")]
    try:
        r = requests.post(URL[mk], json={"symbols": {"tickers": tick}, "columns": FC}, timeout=60).json()
        got = {x["s"].split(":")[1]: dict(zip(FC, x["d"])) for x in r.get("data", [])}
    except Exception as e:
        print("scan err", e); got = {}
    for v in out["stocks"].values():
        g = got.get(v["sym"])
        if v["market"] != mk or not g: continue
        v["fund"] = {"beta": r2(g["beta_1_year"]), "mcap": g["market_cap_basic"], "salesG_q": r2(g["total_revenue_yoy_growth_fq"]),
                     "epsG_q": r2(g["earnings_per_share_diluted_yoy_growth_fq"]), "gm_ttm": r2(g["gross_margin_ttm"]), "gm_fq": r2(g["gross_margin"]),
                     "net_margin": r2(g["net_margin_ttm"]), "last_results": ts(g["earnings_release_date"]), "next_results": ts(g["earnings_release_next_date"]),
                     "sector": g["sector"], "industry": g["industry"], "perfW": r2(g["Perf.W"]), "type": g["type"], "name": g["description"]}

# قوة القطاعات هذا الأسبوع (S16 41:38–43:50) والتصحيح داخل القطاع (S36 53:53–55:11): وسيط أداء الأسبوع والبعد عن قمة السنة لكل قطاع
SC = ["sector", "Perf.W", "close", "price_52_week_high"]
flt = {"sa": [], "us": [{"left": "exchange", "operation": "in_range", "right": ["NYSE", "NASDAQ", "AMEX"]},
                        {"left": "close", "operation": "egreater", "right": 10},
                        {"left": "average_volume_30d_calc", "operation": "greater", "right": 200000}]}
out["sectors"] = {}
for mk in ("sa", "us"):
    try:
        r = requests.post(URL[mk], json={"filter": [{"left": "type", "operation": "equal", "right": "stock"}] + flt[mk],
                                         "columns": SC, "range": [0, 6000]}, timeout=60).json()
        secs = {}
        for x in r.get("data", []):
            s, w, c, hh = x["d"]
            if s and w is not None and c and hh: secs.setdefault(s, []).append((w, (c / hh - 1) * 100))
        stats = {k: {"n": len(v), "perfW_med": r2(statistics.median(a for a, _ in v)), "from52h_med": r2(statistics.median(b for _, b in v))}
                 for k, v in secs.items() if len(v) >= 5}
        top = [k for k, _ in sorted(stats.items(), key=lambda kv: -kv[1]["perfW_med"])[:3]]
        out["sectors"][mk] = {"stats": stats, "top3_week": top}
    except Exception as e:
        print("sector err", e)

json.dump(out, open(os.path.join(ROOT, "picks", "ranking_data.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("saved", len(out["stocks"]))
