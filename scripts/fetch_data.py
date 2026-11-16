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
        d = yf.Ticker(s).history(period="max", interval="1d", auto_adjust=False)
        if d.empty: raise RuntimeError("no daily data")
        d.index = d.index.tz_localize(None); d = enrich(d[["Open", "High", "Low", "Close", "Volume"]].copy())
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

# لقطة الفلترة الكاملة لتاسي من TradingView (بلا تسجيل دخول)
try:
    cols = ["name", "description", "close", "change", "volume", "average_volume_30d_calc", "SMA50", "SMA200", "Perf.1M", "Perf.3M", "Perf.Y", "price_52_week_high", "market_cap_basic"]
    r = requests.post("https://scanner.tradingview.com/ksa/scan", json={"columns": cols, "range": [0, 400], "markets": ["ksa"]}, timeout=30)
    r.raise_for_status()
    rows = [dict(zip(cols, x["d"])) for x in r.json().get("data", [])]
    json.dump(rows, open(os.path.join(OUT, "tasi_scan.json"), "w", encoding="utf-8"), ensure_ascii=False)
    summary["scan_rows"] = len(rows)
except Exception as e:
    summary["errors"].append(f"scanner: {e}")

json.dump(summary, open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps(summary, ensure_ascii=False, indent=1))
