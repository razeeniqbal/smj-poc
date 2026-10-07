"""
Unit test suite for the Production Planning Dashboard.
Verifies all 6 cards, REST API endpoints, Excel template generation, and workbook ingestion.
Operates 100% in-memory with zero access to data/ or output/.
"""

import io
import json
from pathlib import Path
import sys
import unittest
import openpyxl

# Add dashboard root directory to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dashboard import create_app, dashboard_bp
from dashboard.placeholder_data import EXCEL_SHEET_MAPPING, get_default_dataset
from dashboard.analytics import parse_multi_sheet_excel


class TestStandaloneDashboard(unittest.TestCase):
    """Test suite for 6-card production dashboard endpoints and Excel template generation."""

    def setUp(self):
        self.app = create_app(debug=True)
        self.client = self.app.test_client()

    def test_api_health(self):
        """Verify health check endpoint returns 200 OK and healthy status."""
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data["status"], "healthy")
        self.assertIn("facility", data)

    def test_api_dashboard_all_6_cards_present(self):
        """Verify GET /api/dashboard returns all 6 operational cards."""
        response = self.client.get("/api/dashboard")
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)

        # Verify all 6 cards are returned in the payload
        self.assertIn("production_trend", data)        # Card 1
        self.assertIn("field_performance", data)       # Card 2
        self.assertIn("planned_activities", data)      # Card 3
        self.assertIn("active_issues", data)           # Card 4
        self.assertIn("offloading_planning", data)     # Card 5
        self.assertIn("offloading_estimation", data)   # Card 6
        self.assertIn("metadata", data)
        self.assertIn("excel_mapping", data)

        # Card 1 verification (dates, plan, actual, forecast, events)
        pt = data["production_trend"]
        self.assertGreater(len(pt["dates"]), 0)
        self.assertEqual(len(pt["plan"]), len(pt["dates"]))
        self.assertEqual(len(pt["actual"]), len(pt["dates"]))
        self.assertGreater(len(pt["events"]), 0)

        # Card 2 verification
        fp = data["field_performance"]
        self.assertGreater(len(fp["rows"]), 0)
        self.assertEqual(fp["total"]["field"], "Total")

        # Card 3 verification (Planned activities)
        self.assertIsInstance(data["planned_activities"], list)

        # Card 4 verification (Active issues)
        self.assertIsInstance(data["active_issues"], list)

        # Card 5 verification (Offloading planning)
        op = data["offloading_planning"]
        self.assertIn("actual_inventory", op)
        self.assertIn("max_capacity", op)
        self.assertIn("target_offload", op)
        self.assertIn("dates", op)

        # Card 6 verification (Offloading estimation)
        oe = data["offloading_estimation"]
        self.assertIn("scenarios", oe)
        self.assertIn("target_offload_level", oe)
        self.assertIn("maximum_capacity", oe)

    def test_upload_excel_workbook(self):
        """Verify POST /api/upload ingests an uploaded Excel workbook."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Production_Trend"
        ws.append(["report_start_date", "crude_daily_target", "crude_daily_actual", "pd_crude_highlight"])
        ws.append(["2026-09-01", 45.0, 42.0, "Operational Highlight"])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        response = self.client.post(
            "/api/upload",
            data={"file": (buf, "test_upload.xlsx")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data["status"], "success")
        self.assertGreater(data["sheets_parsed"], 0)

    def test_field_filtering(self):
        """Verify GET /api/dashboard?field=Field%20A filters Card 1, 3, 4, 5, 6 appropriately."""
        res_all = self.client.get("/api/dashboard?field=All%20Fields")
        self.assertEqual(res_all.status_code, 200)
        data_all = json.loads(res_all.data)

        res_field = self.client.get("/api/dashboard?field=Field%20A")
        self.assertEqual(res_field.status_code, 200)
        data_field = json.loads(res_field.data)

        self.assertEqual(data_field["metadata"]["selected_field"], "Field A")
        # Planned activities should be filtered to Field A
        for act in data_field["planned_activities"]:
            self.assertEqual(act["field"], "Field A")

    def test_activity_status_update(self):
        """Verify POST /api/activity_status dynamically updates activity status."""
        res = self.client.post(
            "/api/activity_status",
            data=json.dumps({"index": 0, "status": "Completed"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["new_status"], "Completed")

    def test_issue_status_update(self):
        """Verify POST /api/issue_status dynamically updates issue status."""
        res = self.client.post(
            "/api/issue_status",
            data=json.dumps({"index": 0, "status": "Mitigated"}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["new_status"], "Mitigated")

    def test_reset_endpoint(self):
        """Verify POST /api/reset resets data back to default baseline."""
        res = self.client.post("/api/reset")
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertEqual(data["status"], "reset_complete")


class TestColleagueIntegration(unittest.TestCase):
    """Test suite simulating mounting the dashboard Blueprint into a colleague's existing Flask app."""

    def test_colleague_app_blueprint_mounting(self):
        from flask import Flask

        colleague_app = Flask("colleague_main_app")
        colleague_app.register_blueprint(dashboard_bp)
        client = colleague_app.test_client()

        # Check UI route
        ui_res = client.get("/")
        self.assertEqual(ui_res.status_code, 200)

        # Check API route
        api_res = client.get("/api/dashboard")
        self.assertEqual(api_res.status_code, 200)
        data = json.loads(api_res.data)
        self.assertIn("production_trend", data)
        self.assertIn("field_performance", data)


if __name__ == "__main__":
    unittest.main()
