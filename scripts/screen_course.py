"""فلترة الكورس اليومية لتاسي بصيغة صفوف البطاقة (نقل الخطوة 2 من مهمة "السعودي اليومي" إلى GitHub Actions).
يكتب data/screen_course.json. لا يحكم بالعين ولا يضع مستويات دخول/وقف ولا يحدد "مستبعد": هذا يبقى لمهمة Claude.

القواعد كما في المهمة المجدولة:
- الاجتياز الأساسي: عائد سنة > 20 والسعر > متوسط 30 أسبوعاً والسعر > متوسط 200 (قرار المستخدم 2026-11-22: "200 كما في المهمة").
- مرشح: الاجتياز الأساسي + السعر > متوسط 20 + أداء شهر و3 أشهر أفضل من تاسي.
- احتياط: اجتاز الأساس ولم يصبح مرشحاً. من لم يجتز الأساس يُحذف، إلا مركز المستخدم المملوك (يبقى احتياطاً).
- نمو المبيعات والربحية والهامش للعرض فقط (قرار المستخدم 2026-11-09).
مكتبة بايثون القياسية فقط."""
import csv, datetime as dt, json, os, re, statistics, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAN = "https://scanner.tradingview.com/ksa/scan"
HELD = {"6015"}  # أمريكانا: مركز المستخدم، يبقى على البطاقة ما دام مملوكاً
TASI_LEVEL = 10630  # المحاضر 7 نوفمبر 2026: تجاوزه لازم لتغيّر السلوك
COLS = ["name", "description", "close", "change", "high", "low", "open", "volume", "average_volume_30d_calc",
        "Perf.1M", "Perf.3M", "Perf.Y", "SMA20", "SMA50", "SMA200", "SMA10|1W", "SMA30|1W", "price_52_week_high",
        "High.All", "total_revenue_yoy_growth_fq", "earnings_per_share_diluted_yoy_growth_fq", "gross_margin_ttm",
        "earnings_release_next_date", "Perf.W", "sector"]
TCOLS = ["close", "change", "SMA20", "SMA50", "SMA200", "Perf.1M", "Perf.3M", "Perf.Y"]
MAIN = re.compile(r"[1-8]\d{3}")


def gt(a, b):
    return a is not None and b is not None and a > b


def pct(a, b):
    return round((a / b - 1) * 100, 1) if a is not None and b else None


def r1(x):
    return None if x is None else round(x, 1)


def main_market(rows):
    return [r for r in rows if MAIN.fullmatch(str(r.get("name") or "")) and r.get("close") is not None]


def sector_ranks(rows):
    """قوة القطاع كما في المهمة: وسيط أداء الأسبوع لكل قطاع على كل أسهم السوق الرئيسية، ثم ترتيب.
    الثلث الأعلى قوي والثلث الأدنى ضعيف ("الثلث" اختيار آلي، حجمه round(عدد القطاعات/3))."""
    by = {}
    for r in main_market(rows):
        if r.get("sector") and r.get("Perf.W") is not None:
            by.setdefault(r["sector"], []).append(r["Perf.W"])
    ranked = sorted(((s, statistics.median(v)) for s, v in by.items()), key=lambda x: -x[1])
    n = len(ranked)
    k = max(1, round(n / 3)) if n else 0
    out = {}
    for i, (s, m) in enumerate(ranked, 1):
        label = "قطاع قوي هذا الأسبوع" if i <= k else ("قطاع ضعيف" if i > n - k else "وسط")
        out[s] = {"rank": i, "medW": round(m, 2), "label": label}
    return out


def classify(rows, tasi, held=HELD):
    """يعيد صفوف الأسهم (مرشح/احتياط) بحقول البطاقة. status و next يتركان لمهمة Claude."""
    market_ok = "نعم" if gt(tasi["close"], tasi["SMA50"]) else "لا"
    secs = sector_ranks(rows)
    out = []
    for r in main_market(rows):
        sym = str(r["name"])
        c = r["close"]
        base = gt(r["Perf.Y"], 20) and gt(c, r["SMA30|1W"]) and gt(c, r["SMA200"])
        cand = base and gt(c, r["SMA20"]) and gt(r["Perf.1M"], tasi["Perf.1M"]) and gt(r["Perf.3M"], tasi["Perf.3M"])
        if cand:
            group = "مرشح"
        elif base or sym in held:
            group = "احتياط"
        else:
            continue
        s = r["total_revenue_yoy_growth_fq"]
        row = {"sym": sym, "name": r.get("description"), "group": group, "close": c, "chg": r1(r.get("change")),
               "high": r.get("high"), "sma50": r["SMA50"], "above50": gt(c, r["SMA50"]),
               "rs1m": r1(r["Perf.1M"] - tasi["Perf.1M"]) if r["Perf.1M"] is not None else None,
               "rs3m": r1(r["Perf.3M"] - tasi["Perf.3M"]) if r["Perf.3M"] is not None else None,
               "ext10w": pct(c, r["SMA10|1W"]), "from52H": pct(c, r["price_52_week_high"]),
               "salesG": r1(s), "epsG": r1(r["earnings_per_share_diluted_yoy_growth_fq"]),
               "gm": r1(r["gross_margin_ttm"]), "sector": r.get("sector"),
               "sectorRank": secs.get(r.get("sector"), {}).get("rank"),
               "sectorLabel": secs.get(r.get("sector"), {}).get("label"),
               "cond_sales": "غير متوفر" if s is None else ("نعم" if s >= 25 else "لا"),
               "cond_market": market_ok, "held": sym in held, "base_pass": base,
               "earnings_next": r.get("earnings_release_next_date"), "status": None, "next": None}
        if group == "احتياط":
            row["dist50"] = pct(c, r["SMA50"])
        out.append(row)
    out.sort(key=lambda x: (x["group"] != "مرشح", -(x["rs1m"] or -999)))
    return out


def breadth(rows):
    m = main_market(rows)
    return {"universe": len(m), "above50": sum(gt(r["close"], r["SMA50"]) for r in m),
            "above200": sum(gt(r["close"], r["SMA200"]) for r in m),
            "upYear": sum(gt(r["Perf.Y"], 0) for r in m), "yr20": sum(gt(r["Perf.Y"], 20) for r in m)}


def swings(bars):
    """قاع = أدنى من الشمعة قبله وبعده؛ قمة كذلك. المتتاليان من نفس النوع: يبقى الأشد.
    المقابل يُحسب فقط إذا جاء بعد أكثر من 5 شموع من السابق. يعيد [(نوع, فهرس, قيمة)]."""
    out = []
    for i in range(1, len(bars) - 1):
        for kind, key, better in (("L", "low", lambda a, b: a < b), ("H", "high", lambda a, b: a > b)):
            v = bars[i][key]
            if not (better(v, bars[i - 1][key]) and better(v, bars[i + 1][key])):
                continue
            if out and out[-1][0] == kind:
                if better(v, out[-1][2]):
                    out[-1] = (kind, i, v)
            elif not out or i - out[-1][1] > 5:
                out.append((kind, i, v))
    return out


def structure_label(last_low, prev_low, last_high, close):
    if gt(last_low, prev_low) and gt(close, last_high):
        return "قيعان صاعدة وتجاوز آخر قمة (تحسّن)"
    if gt(last_low, prev_low):
        return "قيعان صاعدة بلا تأكيد"
    return "قيعان هابطة (لا تحسّن)"


def tasi_row(tasi, rows, bars):
    sw = swings(bars)
    lows = [v for k, _, v in sw if k == "L"]
    highs = [v for k, _, v in sw if k == "H"]
    last_low = round(lows[-1]) if lows else None
    prev_low = round(lows[-2]) if len(lows) > 1 else None
    last_high = round(highs[-1]) if highs else None
    c = tasi["close"]
    return {"sym": "TASI", "name": "تاسي", "group": "السوق", "close": c, "chg": r1(tasi["change"]),
            "sma20": tasi["SMA20"], "sma50": tasi["SMA50"], "sma200": tasi["SMA200"],
            "perf1m": r1(tasi["Perf.1M"]), "perf3m": r1(tasi["Perf.3M"]), "perfY": r1(tasi["Perf.Y"]),
            **breadth(rows),  # above50/above200 في صف تاسي = عدد الأسهم فوق المتوسط (اتساع السوق)
            "structure": structure_label(last_low, prev_low, last_high, c),
            "lastLow": last_low, "prevLow": prev_low, "lastHigh": last_high,
            "above_10630": gt(c, TASI_LEVEL), "cond_market": "نعم" if gt(c, tasi["SMA50"]) else "لا",
            "status": None, "next": None}


def post(body):
    req = urllib.request.Request(SCAN, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as f:
        return json.load(f)


def fetch():
    allr = post({"filter": [{"left": "type", "operation": "equal", "right": "stock"},
                            {"left": "exchange", "operation": "equal", "right": "TADAWUL"}],
                 "options": {"lang": "ar"}, "markets": ["ksa"], "columns": COLS, "range": [0, 500]})
    t = post({"symbols": {"tickers": ["TADAWUL:TASI"]}, "columns": TCOLS})["data"][0]["d"]
    return [dict(zip(COLS, x["d"])) for x in allr["data"]], dict(zip(TCOLS, t))


def load_bars(path):
    with open(path, encoding="utf-8") as f:
        return [{"date": r["datetime"], "low": float(r["Low"]), "high": float(r["High"])} for r in csv.DictReader(f)]


def main():
    rows, tasi = fetch()
    bars = load_bars(os.path.join(ROOT, "data", "TASI_daily.csv"))
    stocks = classify(rows, tasi)
    out = {"when_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "source": "TradingView scanner ksa/scan (بلا تسجيل دخول) + data/TASI_daily.csv للهيكل",
           "tasi_bars_last_date": bars[-1]["date"] if bars else None,
           "rows": [tasi_row(tasi, rows, bars)] + stocks}
    with open(os.path.join(ROOT, "data", "screen_course.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    n = {g: sum(r["group"] == g for r in stocks) for g in ("مرشح", "احتياط")}
    print(json.dumps({"when_utc": out["when_utc"], **n, "structure": out["rows"][0]["structure"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
