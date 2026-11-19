"""إعادة تشغيل النظام الحالي يوماً بيوم على 2026 (بلا نظر للمستقبل): فلترة الكورس + كاشف VCP/شيك أوت (scripts/vcp.py)
ثم دخول وخروج بقواعد الكورس كما هي مطبقة في المشروع. يُشغَّل محلياً على bt/hist.
القواعد (المصدر في المشروع): فلترة تاسي (عائد سنة >20%، فوق متوسط 30 أسبوعاً و200 وفوق 20، أقوى من تاسي شهراً و3 أشهر)؛
الدخول فوق قمة آخر انكماش +0.4% (الدرس 12)، لا مطاردة فوق 3% (ENT-05)، الوقف تحت قاع آخر انكماش ولا يُنزل، الوقف ≥10% = لا دخول (S12-03)؛
بيع النصف عند +25% (S8-10) والباقي بإغلاق تحت متوسط 20 (S8-15)؛ مخاطرة 1% وحد 12,500 للسهم و8 أسهم (S5)؛ عمولة 0.178% لكل جانب.
اختيارات آلية ليست من الكورس: أمر الدخول صالح للجلسة التالية فقط ويعاد حسابه يومياً؛ الخروج بالمتوسط عند افتتاح اليوم التالي."""
import os, sys, json, glob, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, os.path.join(ROOT, "scripts"))
from vcp import detect
MKT = os.environ.get("BT_MKT", "sa")
if MKT == "us":   # السوق الأمريكي: المؤشر S&P 500، حجم الاختراق 1.5× (S18-11)، عمولة تقديرية 0.05% (ليست من الكورس)
    H = os.path.join(ROOT, "bt", "hist_us"); IDX = "SPX"; VOLX = 1.5
    names = {l.split(",")[0].replace(".", "_"): l.strip().split(",", 2)[2] for l in open(os.path.join(ROOT, "bt", "universe_us.csv"), encoding="utf-8").readlines()[1:]}
else:
    H = os.path.join(ROOT, "bt", "hist"); IDX = "TASI"; VOLX = 1.25
    names = dict(l.strip().split(",", 1) for l in open(os.path.join(ROOT, "bt", "universe.csv"), encoding="utf-8").readlines()[1:])
T = pd.read_csv(os.path.join(H, f"{IDX}.csv"), index_col=0, parse_dates=True)
T["sma50"] = T.close.rolling(50).mean()
D = {}
for f in glob.glob(os.path.join(H, "*.csv")):
    s = os.path.basename(f)[:-4]
    if s == IDX: continue
    d = pd.read_csv(f, index_col=0, parse_dates=True)
    if len(d) < 260: continue
    d = d.reindex(T.index).dropna()  # جلسات تاسي فقط
    d["sma20"] = d.close.rolling(20).mean(); d["sma200"] = d.close.rolling(200).mean(); d["sma150"] = d.close.rolling(150).mean()
    D[s] = d
START, END = pd.Timestamp("2026-01-01"), T.index[-1]
days = [x for x in T.index if x >= START]
COM, CAP, RISK, MAXP = (0.0005 if MKT == "us" else 0.00178), 12500, 1000, 8
METHOD = os.environ.get("BT_METHOD", "both")

def screen(s, i):
    d = D[s]; c = d.close
    if i < 250 or pd.isna(d.sma200.iloc[i]): return False
    perfY = c.iloc[i] / c.iloc[i - 250] - 1
    t = T.close.reindex(d.index)
    rs1 = c.iloc[i] / c.iloc[i - 21] - t.iloc[i] / t.iloc[i - 21]; rs3 = c.iloc[i] / c.iloc[i - 63] - t.iloc[i] / t.iloc[i - 63]
    return perfY > .20 and c.iloc[i] > d.sma150.iloc[i] and c.iloc[i] > d.sma200.iloc[i] and c.iloc[i] > d.sma20.iloc[i] and rs1 > 0 and rs3 > 0

def run(mode):
    """mode: all = كل الإشارات بمخاطرة 1%؛ serve = فقط وتاسي فوق متوسط 50؛ explore = 1% إن خدم السوق وإلا 20% (مركز استكشافي S58-08)."""
    open_, trades, signals = {}, [], 0
    for k in range(len(days) - 1):
        day, nxt = days[k], days[k + 1]
        # 1) إدارة المراكز المفتوحة على جلسة الغد
        for s in list(open_):
            p = open_[s]; d = D[s]
            if nxt not in d.index: continue
            r = d.loc[nxt]
            if p.get("exit_next"):                                   # إغلاق تحت متوسط 20 أمس → خروج بالافتتاح
                p["legs"].append((nxt, r.open, p["qty"])); p["qty"] = 0
            else:
                if r.low <= p["stop"]:
                    px = min(r.open, p["stop"]); p["legs"].append((nxt, px, p["qty"])); p["qty"] = 0
                else:
                    if not p["half"] and r.high >= p["entry"] * 1.25:
                        q = p["qty"] // 2; p["legs"].append((nxt, max(r.open, p["entry"] * 1.25), q)); p["qty"] -= q; p["half"] = True
                    if r.close < d.sma20.loc[nxt]: p["exit_next"] = True
            if p["qty"] == 0:
                cost = p["entry"] * p["q0"] * (1 + COM); proceeds = sum(px * q for _, px, q in p["legs"]) * (1 - COM)
                trades.append({"sym": s, "name": names.get(s, s), "in": str(p["d"].date()), "entry": round(p["entry"], 3), "stop": round(p["stop0"], 3),
                               "out": str(p["legs"][-1][0].date()), "pnl": round(proceeds - cost), "R": round((proceeds - cost) / p["risk"], 2),
                               "ret%": round((proceeds / (cost / (1 + COM)) / (1 - COM) - 1) * 100, 1) if False else round((sum(px*q for _,px,q in p["legs"])/(p['entry']*p['q0'])-1)*100, 1),
                               "half": p["half"], "tasi_serves": p["serve"], "shape": p["shape"]})
                del open_[s]
        # 2) إشارات اليوم (بيانات حتى إغلاق اليوم فقط) → أوامر للغد
        serve = T.close.loc[day] > T.sma50.loc[day]
        if mode == "serve" and not serve: continue
        for s, d in D.items():
            if s in open_ or day not in d.index or nxt not in d.index or len(open_) >= MAXP: continue
            i = d.index.get_loc(day)
            if not screen(s, i): continue
            r = d.loc[nxt]
            entry = None
            if METHOD in ("vcp", "both"):
                w = d.iloc[max(0, i - 129): i + 1]
                sh = detect(*(w[x].tolist() for x in ("open", "high", "low", "close", "volume")))
                if sh["shape"] in ("VCP", "شيك أوت"):
                    piv, stop = sh["pivot"], sh["stop"]
                    if d.close.iloc[i] < piv and (piv - stop) / piv < 0.10:
                        signals += 1
                        if r.high >= piv and r.open <= piv * 1.03: entry = max(r.open, piv)
            if entry is None and METHOD in ("res", "both"):
                # اختراق مقاومة أفقية بالإغلاق (C21، S18-12): مقاومة = قمة آخر 20 جلسة لمسها السعر مرتين على الأقل (±1.5%)،
                # إغلاق اليوم فوقها بحجم ≥1.25× متوسط 50 (تاسي، S18-11)، الدخول بافتتاح الغد إن لم يتجاوز 3%، الوقف تحت أدنى قاع 10 جلسات
                hh = d.high.iloc[i - 20:i]; piv = hh.max()
                touches = int((hh >= piv * 0.985).sum())
                vavg = d.volume.iloc[i - 50:i].mean()
                if touches >= 2 and d.close.iloc[i] > piv and d.close.iloc[i - 1] <= piv and d.volume.iloc[i] >= VOLX * vavg:
                    stop = d.low.iloc[i - 9:i + 1].min() * 0.999
                    if (d.close.iloc[i] - stop) / d.close.iloc[i] < 0.10:
                        signals += 1; sh = {"shape": "مقاومة أفقية"}
                        if r.open <= piv * 1.03: entry = r.open
            if entry is None: continue
            if entry <= stop: continue
            risk = RISK * (1 if (mode != "explore" or serve) else 0.2)
            q = int(min(risk / (entry - stop), (CAP if (mode != "explore" or serve) else CAP * 0.2) / entry))
            if q <= 0: continue
            p = {"d": nxt, "entry": entry, "stop": stop, "stop0": stop, "qty": q, "q0": q, "half": False, "legs": [], "risk": max(1, q * (entry - stop)), "serve": bool(serve), "shape": sh["shape"]}
            open_[s] = p
            if r.low <= stop: p["legs"].append((nxt, stop, q)); p["qty"] = 0   # ضُرب الوقف في يوم الدخول نفسه
            elif r.close < d.sma20.loc[nxt]: p["exit_next"] = True
            if p["qty"] == 0:
                cost = entry * q * (1 + COM); proc = stop * q * (1 - COM)
                trades.append({"sym": s, "name": names.get(s, s), "in": str(nxt.date()), "entry": round(entry, 3), "stop": round(stop, 3), "out": str(nxt.date()),
                               "pnl": round(proc - cost), "R": round((proc - cost) / p["risk"], 2), "ret%": round((stop / entry - 1) * 100, 1), "half": False, "tasi_serves": bool(serve), "shape": sh["shape"]})
                del open_[s]
    # مراكز مفتوحة: تقييم بآخر إغلاق
    for s, p in open_.items():
        last = D[s].close.iloc[-1]; held = sum(px * q for _, px, q in p["legs"]) + last * p["qty"]
        pnl = held * (1 - COM) - p["entry"] * p["q0"] * (1 + COM)
        trades.append({"sym": s, "name": names.get(s, s), "in": str(p["d"].date()), "entry": round(p["entry"], 3), "stop": round(p["stop0"], 3), "out": "مفتوح",
                       "pnl": round(pnl), "R": round(pnl / p["risk"], 2), "ret%": round((held / (p["entry"] * p["q0"]) - 1) * 100, 1), "half": p["half"], "tasi_serves": p["serve"], "shape": p["shape"]})
    return trades, signals

out = {"period": [str(START.date()), str(END.date())], "tasi": [round(T.close[T.index >= START].iloc[0], 2), round(T.close.iloc[-1], 2)],
       "tasi_serve_days": int(sum(T.close.loc[x] > T.sma50.loc[x] for x in days)), "days": len(days), "universe": len(D)}
for m in ("all", "serve", "explore"):
    tr, sg = run(m)
    w = [t for t in tr if t["pnl"] > 0]; l = [t for t in tr if t["pnl"] <= 0]
    eq, peak, dd = 0, 0, 0
    for t in sorted(tr, key=lambda x: x["out"]): eq += t["pnl"]; peak = max(peak, eq); dd = max(dd, peak - eq)
    out[m] = {"signals": sg, "trades": len(tr), "wins": len(w), "net": sum(t["pnl"] for t in tr), "avgR": round(sum(t["R"] for t in tr) / len(tr), 2) if tr else 0,
              "avg_win%": round(sum(t["ret%"] for t in w) / len(w), 1) if w else 0, "avg_loss%": round(sum(t["ret%"] for t in l) / len(l), 1) if l else 0,
              "pf": round(sum(t["pnl"] for t in w) / -sum(t["pnl"] for t in l), 2) if l and sum(t["pnl"] for t in l) else None, "maxDD": dd, "list": tr}
json.dump(out, open(os.path.join(ROOT, "bt", f"result_2026_{MKT}_{METHOD}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for m in ("all", "serve", "explore"):
    o = out[m]; print(m, {k: v for k, v in o.items() if k != "list"})
print({k: v for k, v in out.items() if k not in ("all", "serve", "explore")})
