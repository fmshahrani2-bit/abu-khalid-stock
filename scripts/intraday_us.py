"""فحص السوق الأمريكي كاملاً أثناء الجلسة (كل 15 دقيقة) وإرسال تنبيهات تلقرام وGitHub.
قواعد الكورس للسوق الأمريكي (Demo_Rules_US وبطاقة الأمريكي): المؤشر S&P 500 فوق متوسط 50 حتى يخدم السوق،
فلترة: عائد سنة > 20%، فوق متوسط 30 أسبوعاً و200 يوم، نمو مبيعات ≥ 25%، سعر ≥ 10، سيولة > 200 ألف؛
الاختراق بحجم ≥ 1.5×، لا مطاردة فوق 3% من نقطة الدخول، لا دخول قبل النتائج (10 أيام تداول ≈ 14 يوماً).
إشارات أولية آلية للفت النظر فقط، ليست توصية ولا حكم العين. كل تنبيه مرة واحدة لكل سهم ونوع في اليوم."""
import json, os, re, datetime as dt, requests
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ny = dt.datetime.now(ZoneInfo("America/New_York")); ry = dt.datetime.now(ZoneInfo("Asia/Riyadh"))
TEST = bool(os.environ.get("TEST_MSG"))
open_ = ny.replace(hour=9, minute=30, second=0); close_ = ny.replace(hour=16, minute=10, second=0)
if not TEST and (ny.weekday() > 4 or not (open_ <= ny <= close_)):
    print(f"خارج جلسة السوق الأمريكي ({ny:%a %H:%M} نيويورك)؛ لا فحص"); raise SystemExit(0)
day = ny.strftime("%Y-%m-%d")
SD = os.path.join(ROOT, "data", "intraday_us"); os.makedirs(SD, exist_ok=True)
SF = os.path.join(SD, f"{day}.json")
state = json.load(open(SF, encoding="utf-8")) if os.path.exists(SF) else {"sent": {}, "runs": []}

SCAN = "https://scanner.tradingview.com/america/scan"
def post(body):
    r = requests.post(SCAN, json=body, timeout=40); r.raise_for_status(); return r.json()
cols = ["name", "description", "exchange", "close", "change", "Perf.1M", "Perf.3M", "Perf.Y", "SMA20", "SMA50", "SMA200",
        "SMA30|1W", "price_52_week_high", "total_revenue_yoy_growth_fq", "earnings_release_next_date", "relative_volume_intraday|5"]
flt = [{"left": "type", "operation": "equal", "right": "stock"},
       {"left": "exchange", "operation": "in_range", "right": ["NYSE", "NASDAQ", "AMEX"]},
       {"left": "Perf.Y", "operation": "greater", "right": 20},
       {"left": "average_volume_30d_calc", "operation": "greater", "right": 200000},
       {"left": "close", "operation": "egreater", "right": 10}]
rows = [dict(zip(cols, x["d"])) for x in post({"filter": flt, "options": {"lang": "en"}, "markets": ["america"], "columns": cols, "range": [0, 3000]})["data"]]
spx = dict(zip(["close", "SMA50", "Perf.1M", "Perf.3M"], post({"symbols": {"tickers": ["SP:SPX"]}, "columns": ["close", "SMA50", "Perf.1M", "Perf.3M"]})["data"][0]["d"]))

CJ = json.load(open(os.path.join(ROOT, "us", "card.json"), encoding="utf-8"))
card = {r["sym"]: r for r in CJ["rows"]}
# أسعار أسهم البطاقة التي قد لا تمر بفلتر الماسح (مثل أسهم ذكرها المحاضر وعائد سنتها أقل)
miss = [s for s in card if s not in {r["name"] for r in rows}]
if miss:
    extra = post({"filter": [{"left": "name", "operation": "in_range", "right": miss}, {"left": "type", "operation": "in_range", "right": ["stock", "fund", "dr"]}],
                  "options": {"lang": "en"}, "markets": ["america"], "columns": cols, "range": [0, 500]})["data"]
    rows += [dict(zip(cols, x["d"])) for x in extra]

gt = lambda a, b: a is not None and b is not None and a > b
base = lambda r: gt(r["close"], r["SMA30|1W"]) and gt(r["close"], r["SMA200"]) and (r["total_revenue_yoy_growth_fq"] or 0) >= 25 and gt(r["Perf.Y"], 20)
cand = lambda r: base(r) and gt(r["close"], r["SMA20"]) and gt(r["Perf.1M"], spx["Perf.1M"]) and gt(r["Perf.3M"], spx["Perf.3M"])
serve = gt(spx["close"], spx["SMA50"])
mkt = "السوق يخدم (S&P 500 فوق متوسط 50)" if serve else "السوق لا يخدم (S&P 500 تحت متوسط 50): لا دخول جديد في الديمو"

msgs = []
def alert(sym, kind, text):
    k = f"{sym}|{kind}"
    if k in state["sent"]: return
    state["sent"][k] = ry.strftime("%H:%M"); msgs.append(text)
def earn(r):
    er = r.get("earnings_release_next_date")
    if not er: return ""
    d = dt.datetime.fromtimestamp(er, ZoneInfo("America/New_York"))
    return f"، ⚠️ النتائج {d:%Y-%m-%d} (لا دخول قبلها)" if 0 <= (d.date() - ny.date()).days <= 14 else ""

if serve: alert("SPX", "above50", f"📈 S&P 500 عند {spx['close']:.0f} فوق متوسط 50 يوماً ({spx['SMA50']:.0f}) أثناء الجلسة؛ يُحكم بالإغلاق، ومعه تبدأ مراكز استكشافية فقط")

hits = []
for r in rows:
    s = r["name"]; c = r["close"]
    if c is None: continue
    rv = r.get("relative_volume_intraday|5"); rvt = f"، حجم نسبي {rv:.1f}×" if rv else ""
    pc = c / (1 + (r["change"] or 0) / 100)          # إغلاق أمس
    cr = card.get(s)
    if cr and cr.get("group") in ("ذكره المحاضر", "مرشح") and cr.get("trigger"):
        tag = "ذكره المحاضر للمتابعة" if cr["group"] == "ذكره المحاضر" else "مرشح الفلترة"
        if c > cr["trigger"] >= pc:                    # عبر الدخول اليوم فقط
            chase = " — أعلى من الدخول بأكثر من 3%: لا مطاردة" if c > cr["trigger"] * 1.03 else ""
            alert(s, "trigger", f"🔔 {s} ({tag}) {c} تجاوز الدخول {cr['trigger']}{rvt}{chase}{earn(r)}. ليس أمر دخول: الشرط إغلاق فوق الدخول وفوق قمة أمس بحجم ≥1.5×، والوقف {cr['stop']}. {mkt}")
        if cr.get("stop") and c < cr["stop"] <= pc and cr.get("status") != "أُبطلت الفرضية":
            alert(s, "stop", f"⚠️ {s} ({tag}) {c} تحت الوقف {cr['stop']}: إن كنت داخلاً فالكورس يقول اخرج ولا تُنزل الوقف")
    hi = r["price_52_week_high"]
    if cand(r) and hi and c >= hi * 0.995 and (r["change"] or 0) > 0 and rv and rv >= 1.5 and s not in card:
        hits.append((rv, s, f"🚀 {s} {c} عند قمة 52 أسبوعاً{rvt}، ويجتاز فلترة الكورس (مبيعات {r['total_revenue_yoy_growth_fq']:.0f}%، يتفوق على S&P 500){earn(r)}. إشارة أولية: افحص القاعدة والمقاومة والوقف (≤8%). {mkt}"))
for rv, s, t in sorted(hits, reverse=True)[:12]: alert(s, "high52", t)
if TEST: msgs.append("✅ رسالة تجربة: فحص السوق الأمريكي يعمل")

state["runs"].append(ry.strftime("%H:%M"))
json.dump(state, open(SF, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"{ry:%H:%M} الرياض ({ny:%H:%M} نيويورك) | {len(rows)} سهماً | SPX {spx['close']} | تنبيهات جديدة: {len(msgs)}")
for m in msgs: print(" -", m)
if not msgs: raise SystemExit(0)

gh_tok, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
if gh_tok and repo:
    H = {"Authorization": f"Bearer {gh_tok}", "Accept": "application/vnd.github+json"}; api = f"https://api.github.com/repos/{repo}"
    title = f"تنبيهات السوق الأمريكي {day}"; num = state.get("issue")
    if not num:
        ex = [i for i in requests.get(f"{api}/issues", headers=H, params={"state": "all", "labels": "alerts-us", "per_page": 20}, timeout=30).json()
              if isinstance(i, dict) and i.get("title") == title]
        num = ex[0]["number"] if ex else requests.post(f"{api}/issues", headers=H, json={"title": title, "labels": ["alerts-us"], "assignees": [repo.split("/")[0]],
              "body": "تنبيهات آلية من فحص السوق الأمريكي أثناء الجلسة. إشارات أولية، ليست توصية ولا حكم العين."}, timeout=30).json()["number"]
        state["issue"] = num; json.dump(state, open(SF, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("github comment:", requests.post(f"{api}/issues/{num}/comments", headers=H, json={"body": f"**{ry:%H:%M} الرياض**\n\n" + "\n\n".join(msgs)}, timeout=30).status_code)

tok, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
if tok and chat:
    tok = re.sub(r"\s+", "", tok); tok = tok[3:] if tok.lower().startswith("bot") else tok
    text = f"🇺🇸 فحص السوق الأمريكي {ry:%H:%M} الرياض (إشارات أولية، ليست توصية)\n\n" + "\n\n".join(msgs)
    for i in range(0, len(text), 3800):
        tr = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", json={"chat_id": chat.strip(), "text": text[i:i+3800]}, timeout=30)
        print("telegram:", tr.status_code, tr.json().get("description", "ok"))
