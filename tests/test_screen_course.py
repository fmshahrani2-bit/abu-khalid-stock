"""اختبارات فلترة الكورس (scripts/screen_course.py). بلا شبكة: بيانات ثابتة مكتوبة هنا.
التشغيل: python -m unittest discover -s tests"""
import os, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import screen_course as sc

TASI = {"close": 9960.0, "change": -0.5, "SMA20": 10070.0, "SMA50": 10276.0, "SMA200": 10831.0,
        "Perf.1M": 0.75, "Perf.3M": -10.1, "Perf.Y": -9.5}


def stock(sym, **kw):
    """سهم يجتاز كل الشروط افتراضياً؛ كل اختبار يكسر شرطاً واحداً."""
    r = {"name": sym, "description": "Co " + sym, "close": 100.0, "change": 1.0, "high": 101.0, "low": 99.0,
         "open": 99.5, "volume": 1e6, "average_volume_30d_calc": 8e5, "Perf.1M": 5.0, "Perf.3M": 10.0,
         "Perf.Y": 30.0, "SMA20": 95.0, "SMA50": 90.0, "SMA200": 80.0, "SMA10|1W": 96.0, "SMA30|1W": 85.0,
         "price_52_week_high": 105.0, "High.All": 120.0, "total_revenue_yoy_growth_fq": 30.0,
         "earnings_per_share_diluted_yoy_growth_fq": 10.0, "gross_margin_ttm": 20.0,
         "earnings_release_next_date": None}
    r.update(kw)
    return r


def group_of(rows, sym, held=()):
    out = sc.classify(rows, TASI, held=set(held))
    return {r["sym"]: r["group"] for r in out}.get(sym)


class Classify(unittest.TestCase):
    def test_all_conditions_is_candidate(self):
        self.assertEqual(group_of([stock("1111")], "1111"), "مرشح")

    def test_year_return_20_or_less_removed(self):
        self.assertIsNone(group_of([stock("1111", **{"Perf.Y": 20.0})], "1111"))

    def test_below_30_week_average_removed(self):
        self.assertIsNone(group_of([stock("1111", **{"SMA30|1W": 101.0})], "1111"))

    def test_below_sma200_removed(self):
        # قرار المستخدم 2026-11-22: الاجتياز الأساسي فوق متوسط 200 كما في المهمة
        self.assertIsNone(group_of([stock("1111", SMA200=100.5)], "1111"))

    def test_below_sma50_but_above_200_stays(self):
        self.assertEqual(group_of([stock("1111", SMA50=101.0)], "1111"), "مرشح")

    def test_below_sma20_is_reserve(self):
        self.assertEqual(group_of([stock("1111", SMA20=101.0)], "1111"), "احتياط")

    def test_month_not_beating_tasi_is_reserve(self):
        self.assertEqual(group_of([stock("1111", **{"Perf.1M": 0.5})], "1111"), "احتياط")

    def test_three_months_not_beating_tasi_is_reserve(self):
        self.assertEqual(group_of([stock("1111", **{"Perf.3M": -11.0})], "1111"), "احتياط")

    def test_missing_value_fails_condition(self):
        self.assertIsNone(group_of([stock("1111", SMA200=None)], "1111"))

    def test_nomu_and_non_numeric_symbols_excluded(self):
        rows = [stock("9510"), stock("1111X"), stock("0123")]
        self.assertEqual(sc.classify(rows, TASI, held=set()), [])

    def test_held_position_kept_as_reserve_when_failing(self):
        self.assertEqual(group_of([stock("6015", **{"Perf.Y": -5.0})], "6015", held={"6015"}), "احتياط")

    def test_held_position_keeps_candidate_when_passing(self):
        self.assertEqual(group_of([stock("6015")], "6015", held={"6015"}), "مرشح")

    def test_sales_is_display_only(self):
        # قرار المستخدم 2026-11-09: نمو المبيعات للعرض فقط
        out = sc.classify([stock("1111", total_revenue_yoy_growth_fq=5.0)], TASI, held=set())
        self.assertEqual(out[0]["group"], "مرشح")
        self.assertEqual(out[0]["cond_sales"], "لا")

    def test_sales_flags(self):
        out = {r["sym"]: r["cond_sales"] for r in sc.classify(
            [stock("1111", total_revenue_yoy_growth_fq=25.0), stock("2222", total_revenue_yoy_growth_fq=None)],
            TASI, held=set())}
        self.assertEqual(out, {"1111": "نعم", "2222": "غير متوفر"})

    def test_row_fields(self):
        r = sc.classify([stock("1111", SMA20=101.0)], TASI, held=set())[0]
        self.assertEqual(r["rs1m"], round(5.0 - 0.75, 1))
        self.assertEqual(r["ext10w"], round((100 / 96 - 1) * 100, 1))
        self.assertTrue(r["above50"])
        self.assertEqual(r["dist50"], round((100 / 90 - 1) * 100, 1))
        self.assertEqual(r["cond_market"], "لا")  # تاسي تحت متوسط 50


class Breadth(unittest.TestCase):
    def test_counts_main_market_only(self):
        rows = [stock("1111"), stock("2222", SMA50=101.0, SMA200=101.0, **{"Perf.Y": -1.0}),
                stock("3333", **{"Perf.Y": 10.0}), stock("9510")]
        b = sc.breadth(rows)
        self.assertEqual(b, {"universe": 3, "above50": 2, "above200": 2, "upYear": 2, "yr20": 1})


def bars(lows_highs):
    return [{"low": lo, "high": hi} for lo, hi in lows_highs]


class Structure(unittest.TestCase):
    def test_swing_points(self):
        # قاع عند 1 ثم قمة عند 7 ثم قاع أعلى عند 13 (كل نوع مقابل بعد أكثر من 5 شموع)
        lows = [10, 5, 9, 9, 9, 9, 12, 12, 12, 12, 12, 12, 12, 7, 12, 12]
        highs = [11, 11, 11, 11, 11, 11, 20, 13, 13, 13, 13, 13, 13, 13, 13, 13]
        highs[6] = 11; highs[7] = 25
        sw = sc.swings(bars(zip(lows, highs)))
        self.assertEqual([(k, v) for k, _, v in sw], [("L", 5), ("H", 25), ("L", 7)])

    def test_opposite_swing_within_5_bars_ignored(self):
        lows = [10, 5, 9, 9, 9, 9, 9, 9, 9, 9]
        highs = [11, 11, 11, 15, 11, 11, 11, 11, 11, 11]
        sw = sc.swings(bars(zip(lows, highs)))
        self.assertEqual([k for k, _, _ in sw], ["L"])

    def test_opposite_swing_exactly_5_bars_ignored(self):
        lows = [10, 5, 9, 9, 9, 9, 9, 9, 9, 9]
        highs = [11, 11, 11, 11, 11, 11, 15, 11, 11, 11]  # قمة بعد 5 شموع بالضبط: لا تُحسب
        sw = sc.swings(bars(zip(lows, highs)))
        self.assertEqual([k for k, _, _ in sw], ["L"])

    def test_consecutive_same_type_keeps_more_extreme(self):
        lows = [10, 6, 9, 9, 9, 9, 9, 5, 9, 9]
        highs = [11] * 10
        sw = sc.swings(bars(zip(lows, highs)))
        self.assertEqual([(k, v) for k, _, v in sw], [("L", 5)])

    def test_structure_labels(self):
        self.assertEqual(sc.structure_label(last_low=8, prev_low=5, last_high=20, close=21),
                         "قيعان صاعدة وتجاوز آخر قمة (تحسّن)")
        self.assertEqual(sc.structure_label(last_low=8, prev_low=5, last_high=20, close=19),
                         "قيعان صاعدة بلا تأكيد")
        self.assertEqual(sc.structure_label(last_low=4, prev_low=5, last_high=20, close=21),
                         "قيعان هابطة (لا تحسّن)")


class TasiRow(unittest.TestCase):
    def test_tasi_row_fields(self):
        rows = [stock("1111")]
        lows = [x * 1000 for x in [10, 5, 9, 9, 9, 9, 12, 12, 12, 12, 12, 12, 12, 7, 12, 12]]
        highs = [11000] * 16; highs[7] = 25000
        t = sc.tasi_row(TASI, rows, bars(zip(lows, highs)))
        self.assertEqual((t["sym"], t["group"]), ("TASI", "السوق"))
        self.assertEqual((t["lastLow"], t["prevLow"], t["lastHigh"]), (7000, 5000, 25000))
        self.assertEqual(t["structure"], "قيعان صاعدة بلا تأكيد")
        self.assertEqual((t["above50"], t["above200"]), (1, 1))  # اتساع: عدد الأسهم، لا حالة المؤشر
        self.assertEqual(t["cond_market"], "لا")  # تاسي 9960 تحت متوسط 50
        self.assertFalse(t["above_10630"])
        self.assertEqual(t["universe"], 1)


if __name__ == "__main__":
    unittest.main()
