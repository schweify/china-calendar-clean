import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lunar_python import Solar
from src.build import build, build_statutory_events, render


class CalendarBuildTests(unittest.TestCase):
    def test_2026_statutory_notice(self):
        events, _ = build_statutory_events(2026, 2026)
        by_day = {(e.day.isoformat(), e.summary) for e in events}
        must_have = {
            ("2026-01-01", "元旦 假期 第1天/共3天"),
            ("2026-01-03", "元旦 假期 第3天/共3天"),
            ("2026-01-04", "元旦 补班 第1天/共1天"),
            ("2026-02-15", "春节 假期 第1天/共9天"),
            ("2026-02-23", "春节 假期 第9天/共9天"),
            ("2026-02-14", "春节 补班 第1天/共2天"),
            ("2026-02-28", "春节 补班 第2天/共2天"),
            ("2026-04-04", "清明节 假期 第1天/共3天"),
            ("2026-04-06", "清明节 假期 第3天/共3天"),
            ("2026-05-01", "劳动节 假期 第1天/共5天"),
            ("2026-05-09", "劳动节 补班 第1天/共1天"),
            ("2026-06-19", "端午节 假期 第1天/共3天"),
            ("2026-09-25", "中秋节 假期 第1天/共3天"),
            ("2026-09-20", "国庆节 补班 第1天/共2天"),
            ("2026-10-01", "国庆节 假期 第1天/共7天"),
            ("2026-10-07", "国庆节 假期 第7天/共7天"),
            ("2026-10-10", "国庆节 补班 第2天/共2天"),
        }
        self.assertTrue(must_have <= by_day)
        self.assertEqual(39, len(events))

    def test_2026_solar_terms_match_hko(self):
        expected = {
            "小寒":"2026-01-05","大寒":"2026-01-20","立春":"2026-02-04","雨水":"2026-02-18",
            "惊蛰":"2026-03-05","春分":"2026-03-20","清明":"2026-04-05","谷雨":"2026-04-20",
            "立夏":"2026-05-05","小满":"2026-05-21","芒种":"2026-06-05","夏至":"2026-06-21",
            "小暑":"2026-07-07","大暑":"2026-07-23","立秋":"2026-08-07","处暑":"2026-08-23",
            "白露":"2026-09-07","秋分":"2026-09-23","寒露":"2026-10-08","霜降":"2026-10-23",
            "立冬":"2026-11-07","小雪":"2026-11-22","大雪":"2026-12-07","冬至":"2026-12-22",
        }
        actual = {}
        d = date(2026, 1, 1)
        while d.year == 2026:
            term = Solar.fromYmd(d.year, d.month, d.day).getLunar().getJieQi()
            if term:
                actual[term] = d.isoformat()
            d = date.fromordinal(d.toordinal() + 1)
        self.assertEqual(expected, actual)

    def test_2026_key_lunar_dates(self):
        expected = {
            "2026-01-26": (12, 8),
            "2026-02-17": (1, 1),
            "2026-03-03": (1, 15),
            "2026-03-20": (2, 2),
            "2026-06-19": (5, 5),
            "2026-08-19": (7, 7),
            "2026-08-27": (7, 15),
            "2026-09-25": (8, 15),
            "2026-10-18": (9, 9),
        }
        for ds, lunar_expected in expected.items():
            y, m, d = map(int, ds.split("-"))
            lunar = Solar.fromYmd(y, m, d).getLunar()
            self.assertEqual(lunar_expected, (lunar.getMonth(), lunar.getDay()), ds)

    def test_dedupe_on_dual_role_dates(self):
        events = build(2026, 2026)
        on_mid_autumn = [e.summary for e in events if e.day.isoformat() == "2026-09-25"]
        self.assertEqual(["中秋节 假期 第1天/共3天"], on_mid_autumn)
        on_qingming = [e.summary for e in events if e.day.isoformat() == "2026-04-05"]
        self.assertEqual(["清明节 假期 第2天/共3天"], on_qingming)
        on_cny = [e.summary for e in events if e.day.isoformat() == "2026-02-17"]
        self.assertEqual(["春节 假期 第3天/共9天"], on_cny)

    def test_ics_structure_and_line_folding(self):
        content = render(build(2026, 2026))
        self.assertTrue(content.startswith("BEGIN:VCALENDAR\r\n"))
        self.assertTrue(content.endswith("END:VCALENDAR\r\n"))
        self.assertEqual(content.count("BEGIN:VEVENT"), content.count("END:VEVENT"))
        for line in content.split("\r\n"):
            self.assertLessEqual(len(line.encode("utf-8")), 75, line)


if __name__ == "__main__":
    unittest.main()
