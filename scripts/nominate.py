"""ترشيح أسهم للمتابعة على طريقة أبو خالد — بطلب المستخدم 2026-11-18 ("ابغى تقوم انت بدل ابو خالد وترشح").
المنطق مأخوذ من أنماط اختياراته الفعلية (picks/features.json وLecturer_Selection_Policy.md)، وهو [استنتاج غير مؤكد] لا قاعدة صريحة:
  1. فلترة الكورس: عائد سنة > 20%، فوق متوسط 30 أسبوعاً و200 يوم (المرحلة الثانية). الأمريكي: سعر ≥ 10، سيولة > 200 ألف.
  2. أقوى من المؤشر شهراً وثلاثة أشهر (أوضح سمة في اختياراته: 50 من 56).
  3. ضمن 12% من قمة السنة (34 من 60 من اختياراته).
  4. يُقدَّم من لمس متوسط 20 أو 50 اليوم وأغلق فوقه ("قبلة")، ثم الأقوى نسبياً في 3 أشهر.
  المالية (الأرقام الثلاثة من الكورس S27) تُعرض مرجّحاً لا شرطاً، كما يفعل هو.
  + قسم "محفزات قادمة": إعلانات شركات كبرى خلال 7 أيام تحرّك قطاعها (مثل SOXL مع إعلان إنفيديا) — للعلم.
هذا ترشيح للمتابعة فقط. الدخول تحكمه قواعد الكورس في البطاقات اليومية."""
import json, os, datetime as dt, requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "nominate")
os.makedirs(OUT, exist_ok=True)
COLS = ["name", "description", "close", "low", "Perf.1M", "Perf.3M", "Perf.Y", "SMA20", "SMA50", "SMA200", "SMA30|1W",
        "price_52_week_high", "volume", "average_volume_30d_calc", "total_revenue_yoy_growth_ttm",
        "earnings_per_share_diluted_yoy_growth_ttm", "gross_margin_ttm", "sector", "earnings_release_next_date", "market_cap_basic",
        # أعمدة جدول أبو خالد (صور القناة 2905–2906، استُخرجت بالمطابقة، S78): توقعات المحللين
        "earnings_per_share_forecast_next_fy", "revenue_forecast_next_fy", "net_income_estimate_ntm", "free_cash_flow_estimate_ntm",
        "price_earnings_fwd", "enterprise_value_ebitda_fwd", "price_sales_fwd", "total_debt_estimate_fy", "total_revenue_ttm"]
MK = {
    "sa": {"url": "https://scanner.tradingview.com/ksa/scan", "idx": "TADAWUL:TASI", "flt": []},
    "us": {"url": "https://scanner.tradingview.com/america/scan", "idx": "SP:SPX",
           "flt": [{"left": "exchange", "operation": "in_range", "right": ["NYSE", "NASDAQ", "AMEX"]},
                   {"left": "close", "operation": "egreater", "right": 10},
                   {"left": "average_volume_30d_calc", "operation": "greater", "right": 200000}]},
}
TODAY = dt.date.today().isoformat()

def scan(url, body):
    r = requests.post(url, json=body, timeout=60); r.raise_for_status()
    return [dict(zip(COLS, x["d"]), sym=x["s"]) for x in r.json().get("data", [])]

def r1(x): return None if x is None else round(float(x), 1)

result = {"date": TODAY, "note": "ترشيح للمتابعة على نمط اختيارات أبو خالد [استنتاج غير مؤكد]؛ ليس توصية ولا نقطة دخول", "markets": {}}
for m, c in MK.items():
    idx = scan(c["url"], {"symbols": {"tickers": [c["idx"]]}, "columns": COLS})[0]
    rows = scan(c["url"], {"filter": [{"left": "type", "operation": "equal", "right": "stock"},
                                      {"left": "Perf.Y", "operation": "greater", "right": 20}] + c["flt"],
                           "columns": COLS, "range": [0, 4000]})
    picks = []
    for x in rows:
        try:
            if not (x["close"] > x["SMA30|1W"] and x["close"] > x["SMA200"]): continue
            rs1, rs3 = x["Perf.1M"] - idx["Perf.1M"], x["Perf.3M"] - idx["Perf.3M"]
            if rs1 <= 0 or rs3 <= 0: continue
            fh = (x["close"] / x["price_52_week_high"] - 1) * 100
            if fh < -12: continue
        except (TypeError, ZeroDivisionError):
            continue
        if m == "sa" and x["sym"].split(":")[1].startswith("9"): continue   # نمو (السوق الموازية): أبو خالد يختار من السوق الرئيسية
        k20 = x["low"] <= x["SMA20"] * 1.02 and x["close"] > x["SMA20"]
        k50 = x["low"] <= x["SMA50"] * 1.02 and x["close"] > x["SMA50"]
        why = []
        if k50: why.append("قبلة متوسط 50")
        elif k20: why.append("قبلة متوسط 20")
        if fh >= -3: why.append("قرب قمة السنة")
        why.append(f"أقوى من المؤشر (+{rs1:.0f} شهر، +{rs3:.0f} ثلاثة أشهر)")
        sg, eg, gm = x["total_revenue_yoy_growth_ttm"], x["earnings_per_share_diluted_yoy_growth_ttm"], x["gross_margin_ttm"]
        fin = "مالية تدعمه" if (sg or 0) >= 15 and (eg or 0) > 0 else ("مالية ضعيفة: الاختيار بالسعر" if (sg or 0) < 0 or (eg or 0) < 0 else "مالية متوسطة")
        er = x["earnings_release_next_date"]
        picks.append({"sym": x["sym"].split(":")[1], "name": x["description"], "sector": x["sector"], "close": x["close"],
                      "rs1m": r1(rs1), "rs3m": r1(rs3), "from52h": r1(fh), "kiss": k20 or k50,
                      "salesG": r1(sg), "epsG": r1(eg), "gm": r1(gm), "fin": fin,
                      "next_results": dt.datetime.utcfromtimestamp(er).strftime("%Y-%m-%d") if er else None,
                      "fwd": {"mcap": x["market_cap_basic"], "eps_fy_next": r1(x["earnings_per_share_forecast_next_fy"]),
                              "rev_fy_next": x["revenue_forecast_next_fy"], "rev_fwd_growth": r1((x["revenue_forecast_next_fy"] / x["total_revenue_ttm"] - 1) * 100) if x["revenue_forecast_next_fy"] and x["total_revenue_ttm"] else None,
                              "ni_ntm": x["net_income_estimate_ntm"], "fcf_ntm": x["free_cash_flow_estimate_ntm"], "pe_fwd": r1(x["price_earnings_fwd"]),
                              "ev_ebitda_fwd": r1(x["enterprise_value_ebitda_fwd"]), "ps_fwd": r1(x["price_sales_fwd"]), "debt_fy": x["total_debt_estimate_fy"]},
                      "why": "، ".join(why)})
    picks.sort(key=lambda p: (not p["kiss"], -(p["rs3m"] or 0)))
    result["markets"][m] = {"index": {"close": idx["close"], "above50": idx["close"] > idx["SMA50"]},
                            "passed": len(picks), "top": picks[:15]}

# --- فحص العين (S80، بطلب المستخدم 2026-11-18 "ابغى انت تتعود"): تقريب رقمي لنظرات الكورس على الشارت اليومي.
# كل بند مأخوذ من نص في الدروس؛ الحدود الرقمية هنا اختيار آلي للتقريب (الكورس يقول "بالنظر") ومعلنة.
def eye(sym_full, idx_df):
    import tvDatafeed as tvd
    ex, s = sym_full.split(":")
    d = _TV.get_hist(s, ex, tvd.Interval.in_daily, n_bars=260)
    if d is None or len(d) < 210: return {"note": "بيانات غير كافية"}
    c, h, l, v = d["close"], d["high"], d["low"], d["volume"]
    ma = {k: c.rolling(k).mean() for k in (9, 21, 50, 200)}
    up = {k: bool(ma[k].iloc[-1] > ma[k].iloc[-6]) for k in ma}                       # زاوية المتوسطات للأعلى (S31 16:48)
    order = bool(ma[9].iloc[-1] > ma[21].iloc[-1] > ma[50].iloc[-1] > ma[200].iloc[-1])  # الترتيب المثالي (S31 08:47)
    gap = (ma[9].iloc[-1] / ma[50].iloc[-1] - 1) * 100                                 # الفجوة بين المتوسطات (S31 12:01)
    ext = (c.iloc[-1] / ma[9].iloc[-1] - 1) * 100                                      # فجوة السعر مع المتوسط الصغير (S31 14:44)
    def lows(lo, k=3, n=90):
        lo = lo.iloc[-n:].tolist(); return [lo[i] for i in range(k, len(lo) - k) if lo[i] == min(lo[i - k:i + k + 1])]
    sl, il = lows(l), lows(idx_df["low"]) if idx_df is not None else []
    hl_stock = len(sl) >= 2 and sl[-1] > sl[-2]
    ll_index = len(il) >= 2 and il[-1] < il[-2]
    rs_eye = hl_stock and ll_index                                                     # قيعان صاعدة والمؤشر يهبط (S26 10:13)
    st_low = l.iloc[-60:].idxmin(); ix_low = idx_df["low"].iloc[-60:].idxmin() if idx_df is not None else None
    low_first = bool(ix_low is not None and st_low < ix_low)                           # ضرب القاع قبل السوق (S26 12:20)
    chg = c.diff().iloc[-20:]; vv = v.iloc[-20:]
    upv, dnv = vv[chg > 0].mean(), vv[chg < 0].mean()
    take_me = bool(upv and dnv and upv > dnv * 1.2)                                    # "خذني معك": حجم الصعود أكبر من حجم النزول (S26 21:59)
    rng = lambda n: ((h - l) / c).iloc[-n:].mean()
    calm = bool(rng(10) < rng(50) * 0.8)                                               # الهدوء: تذبذب آخر 10 أيام أقل من متوسط 50 (S31 41:47)
    checks = {"زاوية المتوسطات للأعلى": all(up.values()), "ترتيب 9>21>50>200": order,
              "متوسطات متقاربة (9 عن 50 < 8%)": gap < 8, "غير ممتد عن متوسط 9 (< 4%)": abs(ext) < 4,
              "قيعان صاعدة والمؤشر يهبط": rs_eye, "قاعه قبل قاع المؤشر": low_first,
              "حجم الصعود > حجم النزول": take_me, "هدوء التذبذب": calm}
    return {"score": sum(checks.values()), "of": len(checks), "checks": checks,
            "gap_9_50": r1(gap), "ext_9": r1(ext), "note": "تقريب آلي لنظرات العين (S80)؛ الحكم النهائي بالنظر"}

try:
    import tvDatafeed as tvd
    _TV = tvd.TvDatafeed()
    for m, c in MK.items():
        ie, isy = c["idx"].split(":")
        try: idf = _TV.get_hist(isy, ie, tvd.Interval.in_daily, n_bars=260)
        except Exception: idf = None
        for p in result["markets"][m]["top"]:
            for f in ([f"TADAWUL:{p['sym']}"] if m == "sa" else [f"NASDAQ:{p['sym']}", f"NYSE:{p['sym']}", f"AMEX:{p['sym']}"]):
                try:
                    e = eye(f, idf)
                    if "score" in e: p["eye"] = e; break
                except Exception: pass
            p.setdefault("eye", {"note": "تعذر جلب الشارت"})
        result["markets"][m]["top"].sort(key=lambda p: (-(p["eye"].get("score") or 0), not p["kiss"], -(p["rs3m"] or 0)))
except Exception as ex:
    print("eye err", ex)

# محفزات: إعلانات الشركات الكبرى خلال 7 أيام (مثال أبو خالد: "SOXL تابع مع إعلان إنفيديا")
now = dt.datetime.utcnow().timestamp()
big = scan(MK["us"]["url"], {"filter": [{"left": "market_cap_basic", "operation": "greater", "right": 3e11},
                                        {"left": "earnings_release_next_date", "operation": "in_range", "right": [now - 86400, now + 7 * 86400]}],
                             "columns": COLS, "range": [0, 50]})
ETF = {"Electronic Technology": "SOXX/SOXL (أشباه الموصلات)", "Technology Services": "QQQ / XLK", "Retail Trade": "XRT",
       "Finance": "XLF", "Health Technology": "XLV / IBB", "Energy Minerals": "XLE"}
result["catalysts"] = [{"sym": b["sym"].split(":")[1], "name": b["description"], "date": dt.datetime.utcfromtimestamp(b["earnings_release_next_date"]).strftime("%Y-%m-%d"),
                        "sector": b["sector"], "moves": ETF.get(b["sector"], b["sector"])} for b in big]

json.dump(result, open(os.path.join(OUT, f"{TODAY}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(result, open(os.path.join(OUT, "latest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for m, v in result["markets"].items():
    print(m, "passed", v["passed"]); [print(" ", p["sym"], p.get("eye", {}).get("score"), {k: int(b) for k, b in p.get("eye", {}).get("checks", {}).items()}, "|", p["why"], "|", p["fin"]) for p in v["top"]]
print("catalysts", [(c["sym"], c["date"]) for c in result["catalysts"]])
