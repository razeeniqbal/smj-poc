"""
Tests for the dashboard's Terminal view (dashboard/terminal.py, dashboard/terminal_cards.py).
Each test writes a small CSV to a temp folder and points TERMINAL_CSV at it.
"""

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dashboard import create_app
from dashboard.terminal import load_terminal_data

HEADER = (
    "source_file,submission_date,report_start_date,operator,lopc_24hr,oil_in_water,"
    "crude_daily_actual,crude_daily_target,crude_bs_w,condensate_daily_actual,"
    "crude_lifted_volume,crude_lifting_party,crude_tanker_name,crude_nominated_cargo_size,key_highlight"
)

ROWS = [
    # 3 Aug comes first to check sorting; 2 Aug is reported twice; 4 Aug is missing
    "f3,2026-08-04,2026-08-03 06:00:00,LADY,0,15,28,31.7,0.06,0,0,MT CSK VALIANT,TBA,300,N/A",
    "f1,2026-08-02,2026-08-01 06:00:00,LADY,0,19.6,31.16,23.97,0.027,0.02,,PET,MT BLUE MOON,300,\"Tanker loading \"\"MT BLUE MOON\"\" ~300,000 bbls (PET) planned on 1-2/8/2026.\"",
    "f2a,2026-08-03,2026-08-02 06:00:00,LADY,0,20,30,23.97,0.2,0,313,PET,MT BLUE MOON,300,N/A",
    "f2b,2026-08-03 12:00:00,2026-08-02 06:00:00,LADY,0,20.7,30.29,23.97,0.2,0,313,PET,MT BLUE MOON,300,Completed loading",
    "f5,2026-08-06,2026-08-05 06:00:00,LADY,0,16,33,31.7,N/A,0.03,300,SMJE,MT CSK VALIANT,300,N/A",
    "f6,2026-08-07,2026-08-06 06:00:00,LADY,0,18,29,31.7,0.04,0.01,300,SMJE,MT CSK VALIANT,300,N/A",
]


class TestTerminalLoader(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.csv = Path(self.tmp.name) / "am_daily_terminal_summary.csv"
        self.csv.write_text("\n".join([HEADER, *ROWS]) + "\n", encoding="utf-8")
        self.data = load_terminal_data(self.csv)

    def tearDown(self):
        self.tmp.cleanup()

    def test_rows_sorted_and_deduplicated_keeping_latest_submission(self):
        dates = [r["date"] for r in self.data["rows"]]
        self.assertEqual(dates, ["2026-08-01", "2026-08-02", "2026-08-03", "2026-08-05", "2026-08-06"])
        aug2 = next(r for r in self.data["rows"] if r["date"] == "2026-08-02")
        self.assertEqual(aug2["crude_actual"], 30.29)
        self.assertEqual(self.data["quality"]["duplicate_days"], ["2026-08-02"])
        self.assertEqual(self.data["quality"]["raw_rows"], 6)
        self.assertEqual(self.data["quality"]["rows"], 5)

    def test_missing_days_reported(self):
        self.assertEqual(self.data["quality"]["missing_days"], {"LADY": ["2026-08-04"]})

    def test_na_values_become_none_and_payload_is_strict_json(self):
        aug5 = next(r for r in self.data["rows"] if r["date"] == "2026-08-05")
        self.assertIsNone(aug5["bsw"])
        aug1 = self.data["rows"][0]
        self.assertIsNone(aug1["lifted_volume"])
        json.dumps(self.data, allow_nan=False)

    def test_repeated_lifting_reports_collapse_into_one_event(self):
        events = self.data["liftings"]
        self.assertEqual([(e["tanker"], e["volume"]) for e in events],
                         [("MT BLUE MOON", 313.0), ("MT CSK VALIANT", 300.0)])
        self.assertEqual(events[1]["date"], "2026-08-05")
        self.assertEqual(events[1]["last_reported"], "2026-08-06")

    def test_shifted_lifting_party_is_flagged(self):
        self.assertEqual(self.data["quality"]["suspect_column_shift"], ["2026-08-03"])


class TestTerminalEndpoints(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.csv = Path(self.tmp.name) / "terminal.csv"
        self.csv.write_text("\n".join([HEADER, *ROWS]) + "\n", encoding="utf-8")
        self._old_env = os.environ.get("TERMINAL_CSV")
        os.environ["TERMINAL_CSV"] = str(self.csv)
        self.client = create_app(debug=False).test_client()

    def tearDown(self):
        if self._old_env is None:
            os.environ.pop("TERMINAL_CSV", None)
        else:
            os.environ["TERMINAL_CSV"] = self._old_env
        self.tmp.cleanup()

    def test_dashboard_terminal_view_returns_six_cards(self):
        res = self.client.get("/api/dashboard?view=terminal")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["metadata"]["view"], "terminal")
        self.assertEqual(data["metadata"]["available_fields"], ["LADY"])
        pt = data["production_trend"]
        self.assertEqual(len(pt["plan"]), len(pt["dates"]))
        self.assertIsNone(pt["actual"][pt["dates"].index("4 Aug")])  # missing report stays a gap
        self.assertEqual(data["field_performance"]["rows"][0]["field"], "LADY")
        self.assertEqual(data["offloading_planning"]["unit"], "kbbl")
        self.assertEqual(data["offloading_planning"]["target_offload"], 300.0)
        self.assertEqual(len(data["offloading_estimation"]["scenarios"]), 3)
        self.assertNotIn("offloading_by_field", data)

    def test_terminal_filter_uses_own_offloading_model(self):
        data = self.client.get("/api/dashboard?view=terminal&field=LADY").get_json()
        self.assertEqual(data["metadata"]["selected_field"], "LADY")
        self.assertEqual(data["offloading_estimation"]["field"], "LADY")
        self.assertTrue(all(a["field"] == "LADY" for a in data["planned_activities"]))

    def test_terminal_status_update_does_not_touch_field_dataset(self):
        field_before = self.client.get("/api/dashboard").get_json()["planned_activities"][0]["status"]
        res = self.client.post("/api/activity_status", json={"index": 0, "status": "Deferred", "view": "terminal"})
        self.assertEqual(res.status_code, 200)
        term = self.client.get("/api/dashboard?view=terminal").get_json()["planned_activities"]
        self.assertEqual(term[0]["status"], "Deferred")
        field_after = self.client.get("/api/dashboard").get_json()["planned_activities"][0]["status"]
        self.assertEqual(field_before, field_after)

    def test_terminal_view_missing_csv_returns_404(self):
        os.environ["TERMINAL_CSV"] = str(Path(self.tmp.name) / "nope.csv")
        res = self.client.get("/api/dashboard?view=terminal")
        self.assertEqual(res.status_code, 404)


class TestTerminalCards(unittest.TestCase):
    """Card mapping rules on hand-made terminal data."""

    def _rows(self):
        rows = []
        for day in range(1, 11):
            rows.append({
                "date": f"2026-08-{day:02d}", "operator": "T1", "crude_actual": 30.0, "crude_target": 31.0,
                "lopc": 0.0, "cargo_size": 300.0, "tanker": "MT A", "lifting_party": "PET",
                "highlight": 'Tanker loading "MT A" ~300,000 bbls (PET) planned on 4-5/8/2026.',
                "lifted_volume": None,
            })
        return rows

    def test_planned_loading_without_lift_is_assumed_and_unconfirmed(self):
        from dashboard.terminal_cards import build_terminal_dashboard

        data = build_terminal_dashboard({
            "rows": self._rows(),
            "liftings": [],
            "source": {"file": "x.csv", "modified": "now"},
        })
        act = data["planned_activities"][0]
        self.assertEqual(act["status"], "Unconfirmed")
        self.assertEqual(act["date"], "4-5 Aug 2026")
        inv = data["offloading_planning"]["actual_inventory"]
        # 30 kbbl/d for 5 days, minus the assumed 300 kbbl lift on 5 Aug -> opening stock lifted to keep >= 0
        self.assertEqual(min(v for v in inv if v is not None), 0.0)
        self.assertIn("MT A", data["ai_insight"]["text"])

    def test_inventory_projection_crosses_cargo_size(self):
        from dashboard.terminal_cards import build_terminal_dashboard

        rows = self._rows()
        for r in rows:
            r["highlight"] = None
        data = build_terminal_dashboard({
            "rows": rows,
            "liftings": [{"operator": "T1", "date": "2026-08-10", "tanker": "MT A",
                          "lifting_party": "PET", "volume": 300.0, "cargo_size": 300.0}],
            "source": {"file": "x.csv", "modified": "now"},
        })
        self.assertEqual(data["offloading_planning"]["current_inventory"], 0.0)
        # 300 kbbl at 30 kbbl/d -> 10 days
        self.assertEqual(data["offloading_estimation"]["scenarios"][1]["days_from_now"], "10 days")


if __name__ == "__main__":
    unittest.main()
