import tempfile
import unittest
from pathlib import Path
from datetime import datetime
from scraper.update_status import make_status, JST


class UpdateStatusTest(unittest.TestCase):
    def test_failed_attempt_keeps_previous_date(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, "2026-10-24.csv").write_text("existing")
            status = make_status("failure", d, datetime(2026, 11, 2, 5, tzinfo=JST))
            self.assertEqual(status["latest_date"], "2026-10-24")
            self.assertEqual(status["outcome"], "failure")
            self.assertEqual(len(list(Path(d).iterdir())), 1)

    def test_success_requires_today_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            now = datetime(2026, 11, 2, 5, tzinfo=JST)
            self.assertEqual(make_status("success", d, now)["outcome"], "failure")
            Path(d, "2026-11-02.csv").write_text("today")
            self.assertEqual(make_status("success", d, now)["outcome"], "success")


    def test_partial_and_yesterday_cutoff(self):
        with tempfile.TemporaryDirectory() as d:
            for day in ["2026-11-01", "2026-11-02"]:
                Path(d, day + ".csv").write_text("observed")
            status = make_status("success", d, datetime(2026, 11, 2, 5, tzinfo=JST),
                                 report={"outcome": "partial", "completed_pages": 2, "product_count": 80})
            self.assertEqual(status["outcome"], "partial")
            self.assertEqual(status["latest_date"], "2026-11-01")
            self.assertEqual(status["latest_observed_date"], "2026-11-02")
            self.assertEqual(status["through_date"], "2026-11-01")
            self.assertEqual(status["product_count"], 80)
