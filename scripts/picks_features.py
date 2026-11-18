"""خصائص الأسهم التي ذكرها أبو خالد للمتابعة، يوم ذكرها، ونتيجتها بعده — لاستخراج سياسة اختياره.
المدخل: picks/mentions.json  [{sym, market: sa|us, date: YYYY-MM-DD, words, source}]
المخرج: picks/features.json  {sym|date: {...}}
القياسات مأخوذة من قواعد الكورس (المرحلة الثانية، المتوسطات، القوة النسبية، التمدد فوق متوسط 10 أسابيع، الحجم، شكل القاعدة)،
والنتائج بعد الذكر (+5 و+20 و+60 جلسة، أقصى صعود وأقصى هبوط) للقياس فقط، لا للتنبؤ."""
import json, os, sys, time, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vcp import detect
import tvDatafeed as tvd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
M = json.load(open(os.path.join(ROOT, "picks", "mentions.json"), encoding="utf-8"))
OUTF = os.path.join(ROOT, "picks", "features.json")
out = json.load(open(OUTF, encoding="utf-8")) if os.path.exists(OUTF) else {}
tv = tvd.TvDatafeed()
cache = {}

def bars(sym, market):
    if (sym, market) in cache: return cache[(sym, market)]
    exs = ["TADAWUL"] if market == "sa" else ["NASDAQ", "NYSE", "AMEX", "CBOE"]
    for e in exs:
        try:
            d = tv.get_hist(sym, e, tvd.Interval.in_daily, n_bars=600)
            if d is not None and len(d) > 30:
                d.index = d.index.normalize(); cache[(sym, market)] = d; return d
        except Exception: pass
        time.sleep(0.3)
    cache[(sym, market)] = None; return None

IDX = {"sa": bars("TASI", "sa"), "us": None}
try:
    s = tv.get_hist("SPX", "SP", tvd.Interval.in_daily, n_bars=600); s.index = s.index.normalize(); IDX["us"] = s
except Exception: pass

def perf(d, i, k): return (d["close"].iloc[i] / d["close"].iloc[i - k] - 1) * 100 if i >= k else None
def r2(x): return None if x is None else round(float(x), 2)

for m in M:
    key = f"{m['sym']}|{m['date']}"
    d = bars(m["sym"], m["market"])
    if d is None: out[key] = {**m, "error": "لا بيانات"}; continue
    t = dt.datetime.strptime(m["date"], "%Y-%m-%d")
    pos = d.index.searchsorted(t, side="right") - 1          # آخر جلسة يوم الذكر أو قبله
    if pos < 60: out[key] = {**m, "error": "تاريخ أقدم من البيانات"}; continue
    c = d["close"]; v = d["volume"]; x = c.iloc[pos]
    sma = lambda k: c.iloc[pos - k + 1:pos + 1].mean() if pos >= k - 1 else None
    s20, s50, s150, s200 = sma(20), sma(50), sma(150), sma(200)
    hi52 = d["high"].iloc[max(0, pos - 251):pos + 1].max()
    idx = IDX[m["market"]]
    ip = idx.index.searchsorted(t, side="right") - 1 if idx is not None else None
    rs = lambda k: (perf(d, pos, k) - perf(idx, ip, k)) if idx is not None and ip and perf(d, pos, k) is not None and perf(idx, ip, k) is not None else None
    sub = d.iloc[:pos + 1]
    shape = detect(*(sub[k].tolist() for k in ("open", "high", "low", "close", "volume")))
    low3 = d["low"].iloc[pos - 2:pos + 1].min()
    kiss50 = bool(s50 and low3 <= s50 * 1.02 and x > s50)               # "قبلة لمتوسط 50"
    kiss20 = bool(s20 and low3 <= s20 * 1.02 and x > s20)
    after = {}
    for k in (5, 20, 60):
        if pos + k < len(c): after[f"ret{k}"] = r2((c.iloc[pos + k] / x - 1) * 100)
    fut = d.iloc[pos + 1:pos + 61]
    out[key] = {**m,
        "close": r2(x), "chg_day": r2(perf(d, pos, 1)),
        "above50": bool(s50 and x > s50), "above200": bool(s200 and x > s200), "stage2_30w": bool(s150 and x > s150),
        "dist20": r2((x / s20 - 1) * 100) if s20 else None, "dist50": r2((x / s50 - 1) * 100) if s50 else None,
        "ext10w": r2((x / s50 - 1) * 100) if s50 else None,
        "from52h": r2((x / hi52 - 1) * 100), "perfY": r2(perf(d, pos, 250)),
        "rs1m": r2(rs(21)), "rs3m": r2(rs(63)),
        "vol_vs50": r2(v.iloc[pos] / v.iloc[pos - 50:pos].mean()),
        "range20": r2((d["high"].iloc[pos - 19:pos + 1].max() / d["low"].iloc[pos - 19:pos + 1].min() - 1) * 100),
        "shape": shape.get("shape"), "shape_note": shape.get("note"),
        "kiss50": kiss50, "kiss20": kiss20,
        "index_above50": bool(idx is not None and ip and idx["close"].iloc[ip] > idx["close"].iloc[max(0, ip - 49):ip + 1].mean()),
        **after,
        "max_up60": r2((fut["high"].max() / x - 1) * 100) if len(fut) else None,
        "max_dn60": r2((fut["low"].min() / x - 1) * 100) if len(fut) else None,
        "sessions_after": int(len(c) - 1 - pos), "computed": dt.date.today().isoformat()}
    print(key, out[key].get("shape"), out[key].get("ret20"))

json.dump(out, open(OUTF, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("saved", len(out))
