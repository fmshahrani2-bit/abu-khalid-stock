"""فحص السوق السعودي كاملاً أثناء الجلسة (كل 15 دقيقة) وإرسال تنبيهات تلقرام.
هذه إشارات أولية آلية للفت النظر فقط، وليست حكم العين ولا توصية؛ القرار بعد النظر في الشارت وفق منهج أبو خالد.
كل تنبيه يُرسل مرة واحدة فقط لكل سهم ونوع في اليوم (الحالة محفوظة في data/intraday/<التاريخ>.json)."""
import json, os, re, glob, datetime as dt, requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAN = "https://scanner.tradingview.com/ksa/scan"
now = dt.datetime.utcnow() + dt.timedelta(hours=3)          # توقيت الرياض
day = now.strftime("%Y-%m-%d")
SD = os.path.join(ROOT, "data", "intraday"); os.makedirs(SD, exist_ok=True)
SF = os.path.join(SD, f"{day}.json")
state = json.load(open(SF, encoding="utf-8")) if os.path.exists(SF) else {"sent": {}, "runs": []}

def post(body):
    r = requests.post(SCAN, json=body, timeout=30); r.raise_for_status(); return r.json()

base_cols = ["name", "description", "close", "change", "high", "volume", "average_volume_10d_calc",
             "Perf.1M", "Perf.3M", "Perf.Y", "SMA20", "SMA50", "SMA200", "SMA30|1W", "price_52_week_high",
             "earnings_release_next_date"]
rv_col = "relative_volume_intraday|5"
flt = {"filter": [{"left": "type", "operation": "equal", "right": "stock"},
                  {"left": "exchange", "operation": "equal", "right": "TADAWUL"}],
       "options": {"lang": "en"}, "markets": ["ksa"], "range": [0, 500]}
try:
    res = post({**flt, "columns": base_cols + [rv_col]}); cols = base_cols + [rv_col]
except Exception:
    res = post({**flt, "columns": base_cols}); cols = base_cols
rows = [dict(zip(cols, x["d"])) for x in res["data"]]
rows = [r for r in rows if re.fullmatch(r"[1-8]\d{3}", str(r["name"])) and r["close"] is not None]
T = dict(zip(["close", "change", "Perf.1M", "Perf.3M", "SMA50"],
             post({"symbols": {"tickers": ["TADAWUL:TASI"]}, "columns": ["close", "change", "Perf.1M", "Perf.3M", "SMA50"]})["data"][0]["d"]))

gt = lambda a, b: a is not None and b is not None and a > b
base = lambda r: gt(r["Perf.Y"], 20) and gt(r["close"], r["SMA30|1W"]) and gt(r["close"], r["SMA200"])
cand = lambda r: base(r) and gt(r["close"], r["SMA20"]) and gt(r["Perf.1M"], T["Perf.1M"]) and gt(r["Perf.3M"], T["Perf.3M"])
def rvol(r):
    if r.get(rv_col) is not None: return r[rv_col]
    return r["volume"] / r["average_volume_10d_calc"] if r.get("average_volume_10d_calc") else None

# مستويات بطاقة آخر يوم (دخول/وقف المرشحين) من المستودع
# المصدر الأول: بطاقة اللابتوب الأصلية (sa/card.json تدفعها المهمة اليومية)، والبديل: بطاقة النسخة السحابية (cards/)
SA = os.path.join(ROOT, "sa", "card.json")
cards = sorted(glob.glob(os.path.join(ROOT, "cards", "*.json")))
sa_rows = json.load(open(SA, encoding="utf-8")) if os.path.exists(SA) else None
cloud_date = os.path.basename(cards[-1])[:10] if cards else ""
if sa_rows and sa_rows.get("date", "") >= cloud_date:
    rows_src, card_src = sa_rows["rows"], f"بطاقة اللابتوب {sa_rows.get('date')}"
else:
    rows_src, card_src = (json.load(open(cards[-1], encoding="utf-8")) if cards else []), f"البطاقة السحابية {cloud_date}"
card = {str(c["sym"]): c for c in rows_src}
print("مستويات من:", card_src)
try: prev_watch = {str(w["sym"]) for w in json.load(open(os.path.join(ROOT, "data", "screen.json"), encoding="utf-8"))["watchlist"]}
except Exception: prev_watch = set()
names = {str(k): v.get("name", k) for k, v in card.items()}

import sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from alert_format import line, build
msgs = []          # (القسم، السطر)
def alert(sym, kind, sec, text):
    k = f"{sym}|{kind}"
    if k in state["sent"]: return
    state["sent"][k] = now.strftime("%H:%M"); msgs.append((sec, text))

serve = gt(T["close"], T["SMA50"])
from vcp import shapes_for
card_trig = {k for k, v in card.items() if v.get("group") == "مرشح" and v.get("trigger")}
pool = [(str(r["name"]), "TADAWUL") for r in rows if base(r)] + [(k, "TADAWUL") for k in card]
shapes = shapes_for(list(dict.fromkeys(pool)), os.path.join(ROOT, "data", "shapes", f"sa_{day}.json"))
if serve: alert("TASI", "above50", "market", line("تاسي", round(T["close"]), extra=f"تجاوز متوسط 50 ({T['SMA50']:.0f})، يُحكم بالإغلاق"))

for r in rows:
    s = str(r["name"]); nm = f"{names.get(s) or (r['description'] or s)[:20]} ({s})"; c = r["close"]; rv = rvol(r)
    # 1) خطة مركز أمريكانا
    if s == "6015":
        if c <= 2.46: alert(s, "stop", "plan", line("أمريكانا", c, extra="عند الوقف 2.46 أو تحته: الخطة الخروج، والوقف لا يُنزل"))
        elif c > 2.80: alert(s, "raise", "plan", line("أمريكانا", c, extra="فوق 2.80: إن أغلقت فوقها ارفع الوقف إلى 2.60"))
    # 2) مستويات المرشحين في البطاقة (عند العبور اليوم فقط)
    pc = c / (1 + (r["change"] or 0) / 100)          # إغلاق أمس
    cr = card.get(s)
    if cr and cr.get("group") == "مرشح" and s != "6015":
        t, st = cr.get("trigger"), cr.get("stop")
        if t and c > t >= pc:
            alert(s, "trigger", "chase" if c > t * 1.03 else "ready", line(nm, c, t, st, rv))
        if st and c < st <= pc:
            alert(s, "stop", "stop", line(nm, c, stop=st))
    # 3) VCP / شيك أوت (كشف آلي يومي من الدرس 12): عبور قمة آخر انكماش اليوم
    sh = shapes.get(s)
    if sh and sh.get("pivot") and s not in card_trig:
        pv, st = sh["pivot"], sh["stop"]
        if c > pv >= pc:
            er = r.get("earnings_release_next_date"); ert = ""
            if er:
                d = dt.datetime.utcfromtimestamp(er)
                if 0 <= (d - now).days <= 14: ert = f"⚠️ النتائج {d:%m-%d}"
            sec = "chase" if c > pv * 1.03 else "vcp"
            alert(s, "vcp", sec, line(nm, c, round(pv, 2), round(st, 2), rv, " — ".join(x for x in (f"{sh['shape']}: {sh['note']}", ert) if x)))
    # 4) مرشح جديد دخل الفلترة الكاملة
    if cand(r) and s not in prev_watch and s not in card:
        alert(s, "newcand", "new", line(nm, c, rv=rv))

state["runs"].append(now.strftime("%H:%M"))
json.dump(state, open(SF, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"{now:%H:%M} الرياض | {len(rows)} سهماً | تاسي {T['close']} | تنبيهات جديدة: {len(msgs)}")
if os.environ.get("TEST_MSG"): msgs.append(("plan", "✅ رسالة تجربة: نظام فحص السوق يعمل"))
text = build(f"🇸🇦 تنبيهات السوق السعودي — {now:%H:%M}", msgs, serve, "تاسي") if msgs else ""
print(text)

# قناة 1: إشعار GitHub (تعليق في قضية يومية، يصل لتطبيق GitHub والبريد بلا أي أسرار إضافية)
gh_tok, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
if msgs and gh_tok and repo:
    H = {"Authorization": f"Bearer {gh_tok}", "Accept": "application/vnd.github+json"}
    api = f"https://api.github.com/repos/{repo}"
    title = f"تنبيهات السوق {day}"
    num = state.get("issue")
    if not num:
        ex = [i for i in requests.get(f"{api}/issues", headers=H, params={"state": "all", "labels": "alerts", "per_page": 20}, timeout=30).json()
              if isinstance(i, dict) and i.get("title") == title]
        num = ex[0]["number"] if ex else requests.post(f"{api}/issues", headers=H, json={"title": title, "labels": ["alerts"],
              "body": "تنبيهات آلية من فحص السوق أثناء الجلسة. إشارات أولية للفت النظر، ليست توصية ولا حكم العين.", "assignees": [repo.split("/")[0]]}, timeout=30).json()["number"]
        state["issue"] = num
    r = requests.post(f"{api}/issues/{num}/comments", headers=H, json={"body": text}, timeout=30)
    print("github comment:", r.status_code)
    json.dump(state, open(SF, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# قناة 2: تلقرام (عند إضافة السرّين)
tok, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
if tok:
    tok = re.sub(r"\s+", "", tok)
    if tok.lower().startswith("bot"): tok = tok[3:]
    print("token shape:", "ok" if re.fullmatch(r"\d{6,}:[A-Za-z0-9_-]{30,}", tok) else f"غير صالح (طوله {len(tok)}، فيه نقطتان: {':' in tok})")
if chat: chat = chat.strip()
if msgs and tok and chat:
    for i in range(0, len(text), 3800):
        tr = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", json={"chat_id": chat, "text": text[i:i+3800]}, timeout=30)
        print("telegram:", tr.status_code, tr.json().get("description", "ok"))
elif msgs:
    print("no telegram secrets; messages only in log")
