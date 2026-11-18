"""كشف آلي تقريبي لشكل القاعدة حسب الدرس 12 (VCP) ودرس الشيك أوت (S46).
القواعد من الكورس: انكماشات متتالية تصغر بقيعان أعلى (3 أو 4 أو 5، العد من أدنى قاع)، آخر انكماش أقل من 10%،
الحجم يجف في آخر انكماش تحت متوسط 50، الدخول فوق قمة آخر انكماش بفارق بسيط (12.60→12.65 ≈ +0.4%)، الوقف تحت قاعه.
اختيارات آلية ليست من الكورس (معلنة): القمم والقيعان بنافذة شمعتين على كل جانب، نافذة 120 جلسة، والحد الأدنى
لعدد الانكماشات 2 بعد الانكماش الأول (أي 3 انكماشات)، وشيك أوت = كسر أدنى قاع 20 جلسة بحجم ≥1.5× ثم عودة فوقه خلال 3 جلسات.
هذا تقريب لحكم العين وليس بديلاً عنه."""

def _pivots(h, l, k=2):
    piv = []
    for i in range(k, len(h) - k):
        if h[i] == max(h[i - k:i + k + 1]): piv.append((i, "H", h[i]))
        if l[i] == min(l[i - k:i + k + 1]): piv.append((i, "L", l[i]))
    piv.sort()
    out = []                                    # دمج المتتالي من النوع نفسه بالأقصى
    for p in piv:
        if out and out[-1][1] == p[1]:
            if (p[1] == "H" and p[2] >= out[-1][2]) or (p[1] == "L" and p[2] <= out[-1][2]): out[-1] = p
        else: out.append(p)
    return out

def detect(o, h, l, c, v, window=120, K=2):
    """قوائم بالترتيب الزمني. يعيد dict: shape (VCP/شيك أوت/لا شكل)، pivot، stop، depths، note."""
    n = len(c)
    if n < 60: return {"shape": "لا شكل", "note": "بيانات أقل من 60 جلسة"}
    o, h, l, c, v = [x[-window:] for x in (o, h, l, c, v)]
    n = len(c)
    vavg50 = sum(v[-50:]) / 50
    res = {"shape": "لا شكل", "note": ""}
    # --- VCP: آخر سلسلة انكماشات متتالية تصغر بقيعان أعلى، تنتهي بالانكماش الحالي ---
    piv = _pivots(h, l, K)
    if piv and piv[0][1] == "L": piv = piv[1:]
    cons = [(piv[i], piv[i + 1], (piv[i][2] - piv[i + 1][2]) / piv[i][2]) for i in range(0, len(piv) - 1, 2)
            if piv[i][1] == "H" and piv[i + 1][1] == "L"]
    if cons:
        k = len(cons) - 1
        while k > 0 and cons[k - 1][2] > cons[k][2] and cons[k - 1][1][2] < cons[k][1][2]: k -= 1
        run = cons[k:]
        d = [x[2] for x in run]
        lastH, lastL, lastD = run[-1]
        top = run[0][0][2]
        vol_last = sum(v[lastH[0]:lastL[0] + 1]) / max(1, lastL[0] - lastH[0] + 1)
        intact = min(l[lastL[0]:]) >= lastL[2]
        not_far = c[-1] <= lastH[2] * 1.03                  # لم يبتعد فوق قمة آخر انكماش
        under_top = all(x[0][2] <= top * 1.03 for x in run)  # القمم داخل القاعدة
        res["note"] = f"آخر سلسلة انكماشات {[round(x*100,1) for x in d]}"
        if len(run) >= 3 and lastD < 0.10 and vol_last < vavg50 and intact and not_far and under_top:
            return {"shape": "VCP", "pivot": round(lastH[2] * 1.004, 4), "stop": round(lastL[2] * 0.999, 4),
                    "depths": [round(x * 100, 1) for x in d], "note": f"{len(d)} انكماشات، آخرها {lastD*100:.1f}%"}
    # --- شيك أوت ---
    for j in range(n - 15, n - 1):
        base_low = min(l[j - 20:j]) if j >= 20 else None
        if base_low and l[j] < base_low and v[j] >= 1.5 * vavg50:
            back = [k for k in range(j, min(n, j + 4)) if c[k] > base_low]
            if back and min(l[j:]) >= l[j]:
                top = max(h[j - 20:j])
                return {"shape": "شيك أوت", "pivot": round(top * 1.004, 4), "stop": round(l[j] * 0.999, 4),
                        "note": f"كسر {base_low:g} بحجم {v[j]/vavg50:.1f}× ثم عاد"}
    return res


def shapes_for(pairs, cache_path, log=print):
    """pairs: [(الرمز، السوق في TradingView)]. يحسب الشكل مرة واحدة في اليوم ويحفظه في cache_path."""
    import json, os, time
    cache = json.load(open(cache_path, encoding="utf-8")) if os.path.exists(cache_path) else {}
    todo = [(s, e) for s, e in pairs if s not in cache]
    if todo:
        import tvDatafeed as tvd
        tv = tvd.TvDatafeed()
        for s, e in todo:
            try:
                d = tv.get_hist(s, e, tvd.Interval.in_daily, n_bars=130)
                cache[s] = detect(*(d[x].tolist() for x in ("open", "high", "low", "close", "volume"))) if d is not None and len(d) else {"shape": "لا شكل", "note": "لا بيانات"}
            except Exception as ex:
                cache[s] = {"shape": "لا شكل", "note": f"خطأ بيانات: {str(ex)[:60]}"}
            time.sleep(0.3)
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        json.dump(cache, open(cache_path, "w", encoding="utf-8"), ensure_ascii=False)
        log(f"أشكال القاعدة: حُسب {len(todo)} سهماً؛ VCP={sum(1 for v in cache.values() if v['shape']=='VCP')}، شيك أوت={sum(1 for v in cache.values() if v['shape']=='شيك أوت')}")
    return cache
