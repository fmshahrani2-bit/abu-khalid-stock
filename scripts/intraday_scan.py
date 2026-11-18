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
cards = sorted(glob.glob(os.path.join(ROOT, "cards", "*.json")))
card = {str(c["sym"]): c for c in (json.load(open(cards[-1], encoding="utf-8")) if cards else [])}
try: prev_watch = {str(w["sym"]) for w in json.load(open(os.path.join(ROOT, "data", "screen.json"), encoding="utf-8"))["watchlist"]}
except Exception: prev_watch = set()
names = {str(k): v.get("name", k) for k, v in card.items()}

msgs = []
def alert(sym, kind, text):
    k = f"{sym}|{kind}"
    if k in state["sent"]: return
    state["sent"][k] = now.strftime("%H:%M"); msgs.append(text)

mkt = "السوق يخدم (تاسي فوق متوسط 50)" if gt(T["close"], T["SMA50"]) else "السوق لا يخدم (تاسي تحت متوسط 50): أي مركز استكشافي فقط"
if gt(T["close"], T["SMA50"]): alert("TASI", "above50", f"📈 تاسي {T['close']:.0f} تجاوز متوسط 50 يوماً ({T['SMA50']:.0f}) أثناء الجلسة؛ يُحكم بالإغلاق")

for r in rows:
    s = str(r["name"]); nm = names.get(s) or (r["description"] or s)[:22]; c = r["close"]; rv = rvol(r)
    rvt = f"، حجم نسبي {rv:.1f}×" if rv else ""
    # 1) خطة مركز أمريكانا
    if s == "6015":
        if c <= 2.46: alert(s, "stop", f"⚠️ أمريكانا {c} عند الوقف 2.46 أو تحته: الخطة الخروج، والوقف لا يُنزل")
        elif c > 2.80: alert(s, "raise", f"🔔 أمريكانا {c} فوق 2.80: إن أغلقت فوقها يُرفع الوقف إلى 2.60")
    # 2) مستويات المرشحين في البطاقة
    cr = card.get(s)
    if cr and cr.get("group") == "مرشح" and s != "6015":
        if cr.get("trigger") and c > cr["trigger"]:
            alert(s, "trigger", f"🔔 {nm} ({s}) {c} تجاوز الدخول {cr['trigger']}{rvt}. ليس أمر دخول: الشرط إغلاق فوق الدخول وفوق قمة أمس، بحجم قوي، وانظر الشارت. الوقف {cr.get('stop')}. {mkt}")
        if cr.get("stop") and c < cr["stop"]:
            alert(s, "stop", f"⚠️ {nm} ({s}) {c} تحت الوقف {cr['stop']}: إن كنت داخلاً فالكورس يقول اخرج ولا تُنزل الوقف")
    # 3) سهم يجتاز فلترة الكورس عند قمة 52 أسبوعاً بحجم مرتفع
    hi = r["price_52_week_high"]
    if base(r) and hi and c >= hi * 0.995 and (r["change"] or 0) > 0 and rv and rv >= 1.5:
        er = r.get("earnings_release_next_date"); ert = ""
        if er:
            d = dt.datetime.utcfromtimestamp(er)
            if 0 <= (d - now).days <= 14: ert = f"، ⚠️ النتائج {d:%Y-%m-%d}"
        alert(s, "high52", f"🚀 {nm} ({s}) {c} عند قمة 52 أسبوعاً{rvt}، ويجتاز فلترة الكورس الأساسية{ert}. إشارة أولية: افحص القاعدة والمقاومة على اليسار والوقف قبل أي قرار. {mkt}")
    # 4) مرشح جديد دخل الفلترة الكاملة
    if cand(r) and s not in prev_watch and s not in card:
        alert(s, "newcand", f"➕ {nm} ({s}) {c} دخل فلترة الكورس الكاملة اليوم (فوق المتوسطات ويتفوق على تاسي شهراً وثلاثة أشهر){rvt}. للمراقبة")

state["runs"].append(now.strftime("%H:%M"))
json.dump(state, open(SF, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"{now:%H:%M} الرياض | {len(rows)} سهماً | تاسي {T['close']} | تنبيهات جديدة: {len(msgs)}")
for m in msgs: print(" -", m)

if os.environ.get("TEST_MSG"): msgs.append("✅ رسالة تجربة: نظام فحص السوق يعمل")

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
    r = requests.post(f"{api}/issues/{num}/comments", headers=H, json={"body": f"**{now:%H:%M}**\n\n" + "\n\n".join(msgs)}, timeout=30)
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
    text = f"فحص السوق {now:%H:%M} (إشارات أولية، ليست توصية)\n\n" + "\n\n".join(msgs)
    for i in range(0, len(text), 3800):
        tr = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", json={"chat_id": chat, "text": text[i:i+3800]}, timeout=30)
        print("telegram:", tr.status_code, tr.json().get("description", "ok"))
elif msgs:
    print("no telegram secrets; messages only in log")
