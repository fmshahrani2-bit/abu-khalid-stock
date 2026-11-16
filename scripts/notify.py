"""رسالة تلقرام اختيارية: تعمل فقط إذا وُجد TELEGRAM_TOKEN وTELEGRAM_CHAT_ID في أسرار المستودع.
تنبيهات أسعار لمستويات مركز أمريكانا فقط، وليست حكم العين."""
import json, os, requests
tok, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
if not tok or not chat: print("no telegram secrets; skip"); raise SystemExit(0)
S = json.load(open("data/summary.json", encoding="utf-8"))
lines = [f"تحديث البيانات {S['run_utc']} UTC"]
for it in S["items"]:
    if it["sym"] in ("TASI", "6015"):
        lines.append(f"{it['name']}: {it['close']} ({it['date']})")
a = next((i for i in S["items"] if i["sym"] == "6015"), None)
if a:
    c = a["close"]
    if c <= 2.46: lines.append("⚠️ أمريكانا عند الوقف 2.46 أو تحته")
    elif c > 2.80: lines.append("أمريكانا أغلقت فوق 2.80: موعد رفع الوقف إلى 2.60 حسب الخطة")
    elif c > 2.67: lines.append("أمريكانا أغلقت فوق 2.67 (بداية اختراق)")
if S["errors"]: lines.append("أخطاء: " + "; ".join(S["errors"])[:300])
requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", json={"chat_id": chat, "text": "\n".join(lines)}, timeout=30)
