"""يجلب بيانات الأسعار اليومية والأسبوعية لتاسي وقائمة المتابعة ويحفظها في data/ مع شارتات PNG.
لا يصدر أي إشارة شراء أو بيع؛ الحكم (العين) يبقى لمهمة Claude وفق منهج أبو خالد."""
import json, os, datetime as dt
import pandas as pd, yfinance as yf, requests
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WL = json.load(open(os.path.join(ROOT, "scripts", "watchlist.json"), encoding="utf-8"))
OUT = os.path.join(ROOT, "data"); os.makedirs(os.path.join(OUT, "charts"), exist_ok=True)
summary = {"run_utc": dt.datetime.utcnow().isoformat(timespec="seconds"), "items": [], "errors": []}

def enrich(df):
    for n in (10, 20, 50, 150, 200): df[f"sma{n}"] = df["Close"].rolling(n).mean()
    df["vol_avg50"] = df["Volume"].rolling(50).mean()
    return df

_TV = None
def load_daily(key, ysym, period="max"):
    """المصدر الأول: TradingView عبر tvDatafeed (يحوي كل جلسات تداول بما فيها الأحد، ومعدّل للتجزئة).
    البديل: Yahoo. يعيد (DataFrame, اسم المصدر)."""
    global _TV
    try:
        import tvDatafeed as tvd
        if _TV is None: _TV = tvd.TvDatafeed()
        d = _TV.get_hist(key, "TADAWUL", tvd.Interval.in_daily, n_bars=5000)
        if d is not None and len(d) > 30:
            d = d.rename(columns=str.capitalize); d.index = pd.to_datetime(d.index).normalize()
            if getattr(d.index, "tz", None) is not None: d.index = d.index.tz_localize(None)
            return d[["Open", "High", "Low", "Close", "Volume"]].copy(), "tradingview"
    except Exception as e:
        summary.setdefault("tv_errors", {})[key] = str(e)[:120]
    d = yf.Ticker(ysym).history(period=period, interval="1d", auto_adjust=False)
    if d.empty: raise RuntimeError("no daily data")
    d.index = d.index.tz_localize(None)
    return d[["Open", "High", "Low", "Close", "Volume"]].copy(), "yahoo"

def chart(df, title, path, levels=(), weekly=False):
    d = df.tail(260 if not weekly else 400)
    fig, ax = plt.subplots(2, 1, figsize=(12, 7), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    ax[0].plot(d.index, d["Close"], lw=1.2, color="black", label="Close")
    for n, c in ((10, "tab:blue"), (50, "tab:orange"), (200, "tab:red")) if not weekly else ((10, "tab:blue"), (30, "tab:orange")):
        ax[0].plot(d.index, d["Close"].rolling(n).mean(), lw=0.9, color=c, label=f"MA{n}")
    for lv in levels: ax[0].axhline(lv, ls="--", lw=0.8, color="gray"); ax[0].text(d.index[0], lv, f" {lv}", va="bottom", fontsize=8)
    ax[0].set_title(title); ax[0].legend(loc="upper left", fontsize=8); ax[0].grid(alpha=.3)
    ax[1].bar(d.index, d["Volume"], width=1 if not weekly else 5, color="gray"); ax[1].grid(alpha=.3)
    fig.tight_layout(); fig.savefig(path, dpi=110); plt.close(fig)

items = [dict(WL["index"], is_index=True)] + WL["stocks"]
for it in items:
    s = it["sym"]; key = s.replace("^", "").replace(".SR", "")
    try:
        d, src = load_daily("TASI" if it.get("is_index") else key, s)
        summary.setdefault("sources", {})[key] = src; d = enrich(d)
        d.round(4).to_csv(os.path.join(OUT, f"{key}_daily.csv"))
        w = d[["Open", "High", "Low", "Close", "Volume"]].resample("W-THU").agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}).dropna()
        w.round(4).to_csv(os.path.join(OUT, f"{key}_weekly.csv"))
        chart(d, f"{key} {it['name']} daily", os.path.join(OUT, "charts", f"{key}_daily.png"), it.get("levels", ()))
        chart(w, f"{key} {it['name']} weekly (since listing)", os.path.join(OUT, "charts", f"{key}_weekly.png"), it.get("levels", ()), weekly=True)
        last = d.iloc[-1]
        summary["items"].append({"sym": key, "name": it["name"], "date": str(d.index[-1].date()), "close": round(float(last.Close), 4),
            "high": round(float(last.High), 4), "low": round(float(last.Low), 4),
            "sma50": None if pd.isna(last.sma50) else round(float(last.sma50), 4),
            "vol_vs_avg50": None if pd.isna(last.vol_avg50) or not last.vol_avg50 else round(float(last.Volume / last.vol_avg50), 2),
            "high_52w": round(float(d["High"].tail(252).max()), 4), "low_52w": round(float(d["Low"].tail(252).min()), 4),
            "high_all": round(float(d["High"].max()), 4), "high_all_date": str(d["High"].idxmax().date())})
    except Exception as e:
        summary["errors"].append(f"{s}: {e}")

# فلترة الكورس (نقل حرفي لـ claude/build/screen_course.js في المشروع؛ Screening_Method المراحل 1-2)
SCAN = "https://scanner.tradingview.com/ksa/scan"
def post(body):
    r = requests.post(SCAN, json=body, timeout=30); r.raise_for_status(); return r.json()
try:
    cols = ['name','description','sector','close','Perf.W','Perf.1M','Perf.3M','Perf.Y','SMA20','SMA50','SMA200',
            'SMA10|1W','SMA30|1W','price_52_week_high','Value.Traded','average_volume_30d_calc',
            'total_revenue_yoy_growth_fq','earnings_per_share_diluted_yoy_growth_fq','gross_margin_ttm']
    keys = ['sym','name','sector','close','PerfW','Perf1M','Perf3M','PerfY','SMA20','SMA50','SMA200','SMA10W','SMA30W','hi52','valTraded','avgVol','salesG','epsQoQ','grossM']
    allr = post({"filter":[{"left":"type","operation":"equal","right":"stock"},{"left":"exchange","operation":"equal","right":"TADAWUL"}],
                 "options":{"lang":"en"},"markets":["ksa"],"columns":cols,"range":[0,500]})
    tcols = ['close','Perf.W','Perf.1M','Perf.3M','Perf.Y','SMA20','SMA50','SMA200','SMA10|1W','SMA30|1W']
    t = post({"symbols":{"tickers":["TADAWUL:TASI"]},"columns":tcols})["data"][0]["d"]
    T = dict(zip(['close','PerfW','Perf1M','Perf3M','PerfY','SMA20','SMA50','SMA200','SMA10W','SMA30W'], t))
    import re, statistics
    rows = [dict(zip(keys, x["d"])) for x in allr["data"]]
    rows = [r for r in rows if re.fullmatch(r"[1-8]\d{3}", str(r["sym"])) and r["close"] is not None]
    json.dump({"tasi": T, "rows": rows}, open(os.path.join(OUT, "tasi_scan.json"), "w", encoding="utf-8"), ensure_ascii=False)
    bySec = {}
    for r in rows: bySec.setdefault(r["sector"], []).append(r["PerfW"] or 0)
    med = lambda a: sorted(a)[len(a)//2]
    secRank = sorted(((s, med(a)) for s, a in bySec.items()), key=lambda x: -x[1])
    secScore = {s: {"rank": i+1, "medW": v} for i, (s, v) in enumerate(secRank)}
    gt = lambda a, b: a is not None and b is not None and a > b
    steps = {"main": len(rows)}
    L = [r for r in rows if gt(r["PerfY"], 20)]; steps["F2_yr20"] = len(L)
    L = [r for r in L if gt(r["close"], r["SMA30W"])]; steps["F3_w30"] = len(L)
    L = [r for r in L if gt(r["close"], r["SMA50"])]; steps["F4_sma50"] = len(L)
    below20 = [r for r in L if not gt(r["close"], r["SMA20"])]
    L = [r for r in L if gt(r["close"], r["SMA20"])]; steps["F5_sma20"] = len(L)
    rs = lambda r: gt(r["Perf1M"], T["Perf1M"]) and gt(r["Perf3M"], T["Perf3M"])
    watch = [r for r in L if rs(r)]; steps["F6_rs"] = len(watch)
    fin = lambda r: {"salesOK": None if r["salesG"] is None else r["salesG"] >= 25, "epsOK": None if r["epsQoQ"] is None else r["epsQoQ"] >= 25,
                     "gmOK": None if r["grossM"] is None else r["grossM"] > 0}
    def fmt(r):
        return {"sym": r["sym"], "name": (r["name"] or "")[:26], "sector": r["sector"], "sectorRank": secScore.get(r["sector"], {}).get("rank"),
                "close": r["close"], "yr": round(r["PerfY"], 1), "m1_vs_tasi": round(r["Perf1M"]-T["Perf1M"], 1), "m3_vs_tasi": round(r["Perf3M"]-T["Perf3M"], 1),
                "above200": gt(r["close"], r["SMA200"]), "from52H": round((r["close"]/r["hi52"]-1)*100, 1) if r["hi52"] else None,
                "ext10W": round((r["close"]/r["SMA10W"]-1)*100, 1) if r["SMA10W"] else None, **fin(r)}
    order = lambda r: (secScore.get(r["sector"], {}).get("rank", 99), -((r["Perf3M"] or 0)-T["Perf3M"]))
    screen = {"when": summary["run_utc"], "tasi": T, "steps": steps, "topSectors": secRank[:5],
              "watchlist": [fmt(r) for r in sorted(watch, key=order)],
              "pullbacks_above50_below20": [fmt(r) for r in sorted([r for r in below20 if rs(r)], key=order)],
              "breadth_above50": sum(gt(r["close"], r["SMA50"]) for r in rows), "breadth_above200": sum(gt(r["close"], r["SMA200"]) for r in rows),
              "universe": len(rows)}
    json.dump(screen, open(os.path.join(OUT, "screen.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    summary["screen_steps"] = steps; summary["screen_watchlist"] = [w["sym"] for w in screen["watchlist"]]
    # تاريخ أسعار مرشحي الفلترة الجدد أيضاً حتى تقرأ مهمة Claude شارتاتهم
    have = {i["sym"].replace(".SR", "") for i in WL["stocks"]}
    for w in screen["watchlist"] + screen["pullbacks_above50_below20"]:
        if str(w["sym"]) in have: continue
        try:
            d, src = load_daily(str(w["sym"]), f"{w['sym']}.SR", "2y")
            summary.setdefault("sources", {})[str(w["sym"])] = src; d = enrich(d)
            d.round(4).to_csv(os.path.join(OUT, f"{w['sym']}_daily.csv"))
            chart(d, f"{w['sym']} daily", os.path.join(OUT, "charts", f"{w['sym']}_daily.png"))
        except Exception as e:
            summary["errors"].append(f"{w['sym']}: {e}")
except Exception as e:
    summary["errors"].append(f"screen: {e}")

# تاريخ مؤشر تاسي: تجربة رموز بديلة (Yahoo أعاد يوماً واحداً لـ ^TASI.SR)
best = None
for cand in ["^TASI.SR", "^TASI", "TASI.SR", "^TASISR"]:
    try:
        d = yf.Ticker(cand).history(period="max", interval="1d", auto_adjust=False)
        n = len(d); summary.setdefault("tasi_candidates", {})[cand] = n
        if n > (len(best[1]) if best else 0): best = (cand, d)
    except Exception as e:
        summary.setdefault("tasi_candidates", {})[cand] = str(e)[:80]
if not best or len(best[1]) <= 300:
    # بديل: بيانات TradingView التاريخية عبر tvDatafeed (بلا تسجيل دخول)
    for src, fn in (("stooq", lambda: pd.read_csv("https://stooq.com/q/d/l/?s=^tasi&i=d", index_col=0, parse_dates=True)),
                    ("tvdatafeed", lambda: __import__("tvDatafeed").TvDatafeed().get_hist("TASI", "TADAWUL", __import__("tvDatafeed").Interval.in_daily, n_bars=3000))):
        try:
            d = fn(); d = d.rename(columns=str.capitalize)
            summary.setdefault("tasi_candidates", {})[src] = len(d)
            if len(d) > 300:
                d.index = pd.to_datetime(d.index).normalize()
                if getattr(d.index, "tz", None) is not None: d.index = d.index.tz_localize(None)
                best = (src, d); break
        except Exception as e:
            summary.setdefault("tasi_candidates", {})[src] = str(e)[:120]
if best and len(best[1]) > 300:
    d = best[1]; d.index = d.index.tz_localize(None); d = enrich(d[["Open","High","Low","Close","Volume"]].copy())
    d.round(2).to_csv(os.path.join(OUT, "TASI_daily.csv")); summary["tasi_source"] = best[0]
    chart(d, "TASI daily", os.path.join(OUT, "charts", "TASI_daily.png"))

json.dump(summary, open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(summary, ensure_ascii=False, indent=1))
