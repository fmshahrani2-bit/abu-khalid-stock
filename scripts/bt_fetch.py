"""جلب تاريخ يومي (600 جلسة) لكل أسهم السوق الرئيسية وتاسي لاختبار 2026 (bt/hist). بيانات فقط، بلا قواعد."""
import os, re, time, requests, tvDatafeed as tvd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "bt", "hist" + os.environ.get("BT_SUFFIX", "")); os.makedirs(OUT, exist_ok=True)
res = requests.post("https://scanner.tradingview.com/ksa/scan", json={"filter": [{"left": "type", "operation": "equal", "right": "stock"},
      {"left": "exchange", "operation": "equal", "right": "TADAWUL"}], "columns": ["name", "description"], "markets": ["ksa"], "range": [0, 600]}, timeout=30).json()
syms = [x["d"][0] for x in res["data"] if re.fullmatch(r"[1-8]\d{3}", str(x["d"][0]))]
names = {x["d"][0]: x["d"][1] for x in res["data"]}
open(os.path.join(ROOT, "bt", "universe.csv"), "w", encoding="utf-8").write("sym,name\n" + "".join(f"{s},{names[s].replace(',', ' ')}\n" for s in syms))
tv = tvd.TvDatafeed(); ok = 0
for s in ["TASI"] + syms:
    for a in range(3):
        try:
            d = tv.get_hist(s, "TADAWUL", tvd.Interval.in_daily, n_bars=int(os.environ.get("NBARS", 600)))
            if d is not None and len(d):
                d.index = d.index.date; d[["open", "high", "low", "close", "volume"]].to_csv(os.path.join(OUT, f"{s}.csv"), index_label="date"); ok += 1; break
        except Exception as e: print(s, e)
        time.sleep(2)
    time.sleep(0.3)
print("fetched", ok, "of", len(syms) + 1)
