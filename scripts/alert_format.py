"""صياغة موحدة وبسيطة لرسائل التنبيه: أقسام قصيرة، سطر لكل سهم، والشرح مرة واحدة في آخر الرسالة."""
RLM = "‏"
SECTIONS = [
    ("plan",  "📌 مركزك"),
    ("market", "📈 المؤشر"),
    ("ready", "🔔 تجاوز سعر الدخول — افحص الشارت الآن"),
    ("chase", "⛔ ارتفع كثيراً فوق الدخول — لا تلحقه"),
    ("stop",  "⚠️ نزل تحت الوقف — إن كنت داخلاً فاخرج"),
    ("vcp",   "🎯 اخترق قمة آخر انكماش (VCP / شيك أوت) — افحص الشارت الآن"),
    ("new",   "➕ دخل الفلترة اليوم — للمراقبة"),
]

MARKET = {"m": "us"}   # الكورس: حجم الاختراق 1.5× المتوسط، وفي تاسي "أحياناً" 1.25× (S18-11)

def vol_word(rv):
    if rv is None: return ""
    if rv >= 1.5: return "حجم قوي"
    if MARKET["m"] == "sa" and rv >= 1.25: return "حجم مقبول في تاسي"
    return "حجم عادي" if rv >= 1 else "حجم ضعيف"

def line(name, price, trigger=None, stop=None, rv=None, extra=""):
    parts = [f"{name}: {price:g}"]
    if trigger is not None: parts.append(f"الدخول {trigger:g}")
    if stop is not None: parts.append(f"الوقف {stop:g}")
    v = vol_word(rv)
    if v: parts.append(v)
    if extra: parts.append(extra)
    return RLM + "• " + " — ".join(parts)

def build(title, items, market_ok, market_name):
    """items: list of (section_key, text)."""
    out = [RLM + title]
    for key, head in SECTIONS:
        ls = [t for k, t in items if k == key]
        if ls: out += ["", RLM + head] + ls
    m = f"{market_name} فوق متوسط 50: السوق يخدم." if market_ok else f"{market_name} تحت متوسط 50: السوق لا يخدم، فأي دخول يكون استكشافياً صغيراً فقط."
    out += ["", RLM + "تذكير: التنبيه ليس أمر شراء. في الكورس طريقتان: قاعدة VCP يُشترى فيها أثناء الجلسة فوق قمة آخر انكماش بشرط تجاوز قمة أمس وحجم قوي؛ واختراق مقاومة أفقية يُنتظر فيه الإغلاق فوقها ثم الشراء فوق قمة شمعة الإغلاق. " + m]
    return "\n".join(out)
