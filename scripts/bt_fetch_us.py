"""جلب تاريخ يومي (600 جلسة) لأسهم أمريكية (قيمة سوقية ≥ 2 مليار، سعر ≥ 10، سيولة ≥ 500 ألف اليوم) وS&P 500 لاختبار 2026.
الشريحة SHARD من NSHARDS للتوازي. القائمة من اليوم (انحياز بقاء معلن)."""
import os, time, json, requests, tvDatafeed as tvd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "bt", "hist_us" + os.environ.get("BT_SUFFIX", "")); os.makedirs(OUT, exist_ok=True)
SH, N = int(os.environ.get("SHARD", 0)), int(os.environ.get("NSHARDS", 1))
res = requests.post("https://scanner.tradingview.com/america/scan", json={"filter": [
    {"left": "type", "operation": "equal", "right": "stock"}, {"left": "subtype", "operation": "in_range", "right": ["common", ""]},
    {"left": "exchange", "operation": "in_range", "right": ["NASDAQ", "NYSE"]},
    {"left": "market_cap_basic", "operation": "greater", "right": 2e9}, {"left": "close", "operation": "greater", "right": 10},
    {"left": "average_volume_30d_calc", "operation": "greater", "right": 5e5}],
    "columns": ["name", "exchange", "description"], "sort": {"sortBy": "market_cap_basic", "sortOrder": "desc"}, "range": [0, 2000]}, timeout=30).json()
rows = [(x["d"][0], x["d"][1], x["d"][2]) for x in res["data"]]
if SH == 0:
    open(os.path.join(ROOT, "bt", "universe_us.csv"), "w", encoding="utf-8").write("sym,ex,name\n" + "".join(f"{s},{e},{n.replace(',', ' ')}\n" for s, e, n in rows))
todo = ([("SPX", "SP")] if SH == 0 else []) + [(s, e) for i, (s, e, _) in enumerate(rows) if i % N == SH]
tv = tvd.TvDatafeed(); ok = 0
for s, e in todo:
    for a in range(3):
        try:
            d = tv.get_hist(s, e, tvd.Interval.in_daily, n_bars=int(os.environ.get("NBARS", 600)))
            if d is not None and len(d):
                d.index = d.index.date; d[["open", "high", "low", "close", "volume"]].to_csv(os.path.join(OUT, f"{s.replace('.', '_')}.csv"), index_label="date"); ok += 1; break
        except Exception as ex: print(s, ex)
        time.sleep(2)
print("shard", SH, "fetched", ok, "of", len(todo), "universe", len(rows))
