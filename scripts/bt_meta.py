"""بيانات وصفية للاختبار: القطاع والقيمة السوقية الحالية من سكنر TradingView، وتاريخ أول شمعة (تقريب لتاريخ الطرح) للأمريكي."""
import os, re, json, time, requests
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); B = os.path.join(ROOT, "bt")
MKT = os.environ.get("BT_MKT", "us")
url = f"https://scanner.tradingview.com/{'america' if MKT == 'us' else 'ksa'}/scan"
cols = ["name", "sector", "market_cap_basic", "close"]
syms = [l.split(",")[0] for l in open(os.path.join(B, "universe_us.csv" if MKT == "us" else "universe.csv"), encoding="utf-8").readlines()[1:]]
meta = {}
for i in range(0, len(syms), 400):
    chunk = syms[i:i + 400]
    tick = [f"{'TADAWUL' if MKT == 'sa' else ex}:{s}" for s, ex in ((s, None) for s in chunk)] if MKT == "sa" else None
    if MKT == "us":
        ex = {l.split(",")[0]: l.split(",")[1] for l in open(os.path.join(B, "universe_us.csv"), encoding="utf-8").readlines()[1:]}
        tick = [f"{ex[s]}:{s}" for s in chunk]
    r = requests.post(url, json={"symbols": {"tickers": tick}, "columns": cols}, timeout=60).json()
    for x in r.get("data", []): meta[x["d"][0].replace(".", "_")] = {"sector": x["d"][1], "mcap": x["d"][2], "close": x["d"][3]}
if MKT == "us":
    import tvDatafeed as tvd
    tv = tvd.TvDatafeed(); SH, N = int(os.environ.get("SHARD", 0)), int(os.environ.get("NSHARDS", 1))
    ex = {l.split(",")[0]: l.split(",")[1] for l in open(os.path.join(B, "universe_us.csv"), encoding="utf-8").readlines()[1:]}
    for k, s in enumerate(syms):
        if k % N != SH: continue
        for a in range(3):
            try:
                d = tv.get_hist(s, ex[s], tvd.Interval.in_daily, n_bars=8000)
                if d is not None and len(d): meta.setdefault(s.replace(".", "_"), {})["first"] = str(d.index[0].date()); break
            except Exception as e: print(s, e)
            time.sleep(2)
json.dump(meta, open(os.path.join(B, f"meta_{MKT}_{os.environ.get('SHARD', 0)}.json"), "w"), ensure_ascii=False)
print(MKT, len(meta), sum(1 for v in meta.values() if v.get("first")))
