# تقارير 2026-11-27 — نسخة توثيقية للمراجعة المستقلة

نُقلت من مستندات مشروع Claude دون أي تعديل في الكود أو نتائج الاختبارات أو قواعد التداول. فرع `main` لم يُمس.

| المجلد | الملفات |
|---|---|
| `stop_management/` | `SPEC.md` (v1.0 + ملحق التحليل)، `RESULTS.md` (v1.0.1 بيانات طويلة، مع بانر التصحيح)، `RESULTS_v1.0_short_data.md` (للسجل)، `robustness.md`، `robustness_analysis.json` |
| `resistance_rr/` | `SPEC.md`، `RESULTS.md`، `rr_analysis.json` |
| `visual_review/` | `PROTOCOL.md`، `blind_charts/` (60 شارتاً أعمى) |

**محجوب عمداً حتى ينتهي التقييم البشري الأعمى:** `visual_review/FINAL.md` (يكشف قرارات Claude ونتائج الحالات الستين)، ومفتاح الشارتات، وشارتات الكشف، وجدول المقارنة CSV.

الكود والنتائج الخام في `stopmgmt/` على هذا الفرع: المحرك `bt_stopmgmt.py` v1.0.1، و`rr.py` v1.0، و`review_sample.py`، والمخرجات في `stopmgmt/out/`.
