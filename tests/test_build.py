import unittest
from scraper.build import build, load_config


class YesterdayCutoffTest(unittest.TestCase):
    def test_today_price_does_not_enter_yesterday_summary(self):
        row = dict(title="いちご", kind="生果", url="", producer="農家", prefecture="大分県",
                   variety="ベリーツ", image="", price=1000, ship=0, fee=0, rank=1,
                   status="", weight=500, west=0, ppk=2000, reviews=10, rating=5,
                   stock=None, sold_out=0)
        days = {"2026-11-01": {"1": row}, "2026-11-02": {"1": dict(row, price=9000, reviews=100)}}
        result = build(days, load_config(), False, through_date="2026-11-01")
        self.assertEqual(result["latest_date"], "2026-11-01")
        self.assertEqual([d["date"] for d in result["daily"]], ["2026-11-01"])
        self.assertEqual(result["products"][0]["price"], 1000)
        self.assertEqual(result["products"][0]["reviews"], 10)
        self.assertEqual(result["through_date"], "2026-11-01")
