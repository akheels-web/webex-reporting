import json
import tempfile
import unittest

import db
import jobs


class TestMonthRange(unittest.TestCase):
    def test_muscat_month_window(self):
        start, end = jobs.month_range_utc("2026-09")
        self.assertEqual(start, "2026-08-31T20:00:00Z")
        self.assertEqual(end, "2026-09-30T20:00:00Z")

    def test_previous_month(self):
        from datetime import datetime
        self.assertEqual(jobs.previous_month(datetime(2026, 1, 2)), "2025-12")
        self.assertEqual(jobs.previous_month(datetime(2026, 10, 20)), "2026-09")


class TestAggregation(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.cfg = {"data_dir": self._tmp.name, "org_timezone": "Asia/Muscat"}
        db.init(self.cfg)
        conn = db.connect(self.cfg)
        db.save_members(conn, "2026-09-30", "g1", [
            {"person_id": "p1", "name": "Ali", "email": "ali@x.com"},
            {"person_id": "p2", "name": "Maya", "email": "maya@x.com"},
        ])
        recs = [
            {"recordId": "r1", "startTime": "2026-09-05T10:00:00Z", "duration": 60,
             "answered": True,
             "originatingUserId": "p1", "terminatingUserId": "p9"},   # p1 outbound
            {"recordId": "r2", "startTime": "2026-09-06T10:00:00Z", "duration": 120,
             "answered": True,
             "originatingUserId": "p7", "terminatingUserId": "p1"},   # p1 inbound
            {"recordId": "r3", "startTime": "2026-09-07T10:00:00Z", "duration": 59,
             "answered": False,                                       # missed -> excluded
             "originatingUserId": "p1", "terminatingUserId": "p9"},
            {"recordId": "r4", "startTime": "2026-09-08T10:00:00Z", "duration": 0,
             "answered": True,                                        # 0s -> excluded
             "originatingUserId": "p1", "terminatingUserId": "p9"},
            {"recordId": "r5", "startTime": "2026-09-09T10:00:00Z", "duration": 90,
             "answered": True, "originatingUserId": "nobody"},        # unknown -> excluded
            {"recordId": "r6", "startTime": "2026-10-01T01:00:00Z", "duration": 99,
             "answered": True, "originatingUserId": "p1"},            # next month
        ]
        for r in recs:
            db.upsert_cdr(conn, r["recordId"], jobs.cdr_start(r), r["duration"],
                          r["answered"], json.dumps(r))
        conn.commit()
        conn.close()

    def tearDown(self):
        self._tmp.cleanup()

    def test_counts(self):
        rows = {r["email"]: r for r in jobs.aggregate(self.cfg, "2026-09")}
        self.assertEqual(rows["ali@x.com"]["outbound"], 1)
        self.assertEqual(rows["ali@x.com"]["inbound"], 1)
        self.assertEqual(rows["ali@x.com"]["talk_min"], 3.0)
        self.assertEqual(rows["maya@x.com"]["total"], 0)

    def test_csv(self):
        rows = jobs.aggregate(self.cfg, "2026-09")
        data = jobs.make_csv(rows, "2026-09").decode("utf-8")
        csv_lines = data.strip().splitlines()
        self.assertEqual(csv_lines[-2], "Maya,maya@x.com,0,0,0,0.0")
        self.assertEqual(csv_lines[-1], "TOTAL,,1,1,2,3.0")


if __name__ == "__main__":
    unittest.main()
