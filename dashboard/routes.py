"""
Routes and API endpoints for the Production Planning Dashboard.
Encapsulates all UI rendering, REST APIs, and in-memory runtime data management.
"""

from copy import deepcopy
from datetime import datetime
from flask import Blueprint, jsonify, render_template, request

from dashboard.analytics import parse_multi_sheet_excel
from dashboard.placeholder_data import EXCEL_SHEET_MAPPING, get_default_dataset
from dashboard.terminal import get_terminal_csv_path
from dashboard.terminal_cards import get_terminal_dashboard

# Dashboard Blueprint - ready to be registered in any Flask application
dashboard_bp = Blueprint(
    "dashboard",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/dashboard/static",
)

# In-memory working runtime dataset
_runtime_dataset = get_default_dataset()


def _source_dataset(view: str) -> dict:
    """The live dataset behind a view: fields (placeholder / Excel upload) or terminals (ETL CSV)."""
    return get_terminal_dashboard() if view == "terminal" else _runtime_dataset


def get_filtered_dashboard_data(field_filter: str = "All Fields", view: str = "field") -> dict:
    """Return complete 6-card payload with field-level filtering and scaling applied."""
    data = deepcopy(_source_dataset(view))
    data["metadata"]["view"] = view
    offloading_by_field = data.pop("offloading_by_field", {})

    # Ensure available_fields is always present in metadata
    if "available_fields" not in data["metadata"] or not data["metadata"].get("available_fields"):
        fields_list = []
        for r in data.get("field_performance", {}).get("rows", []):
            fn = r.get("field")
            if fn and fn.lower() != "total" and fn not in fields_list:
                fields_list.append(fn)
        for fn in data.get("production_trend", {}).get("by_field", {}).keys():
            if fn and fn.lower() != "total" and fn not in fields_list:
                fields_list.append(fn)
        data["metadata"]["available_fields"] = fields_list or ["Field A", "Field B", "Field C", "Field D"]

    # When a specific field is filtered, update Production Trend, Planned Activities, and Active Issues
    if field_filter and field_filter != "All Fields":
        data["metadata"]["selected_field"] = field_filter

        # 1. Update Card 1 (Production Trend) to display the selected field's data
        pt = data.get("production_trend", {})
        by_field = pt.get("by_field", {})
        if field_filter in by_field:
            f_data = by_field[field_filter]
            pt["plan"] = f_data["plan"]
            pt["actual"] = f_data["actual"]
            pt["forecast"] = f_data["forecast"]
            if "dates" in f_data and f_data["dates"]:
                pt["dates"] = f_data["dates"]
            pt["events"] = f_data.get("events", [])
        else:
            pt["events"] = [e for e in pt.get("events", []) if e.get("field") == field_filter]

        # 2. Filter Planned Activities and Active Issues
        data["planned_activities"] = [
            a for a in data["planned_activities"] if a.get("field") == field_filter
        ]
        data["active_issues"] = [
            i for i in data["active_issues"] if i.get("field") == field_filter
        ]

        # 3. Card 5 & 6: use the entity's own offloading model when there is one,
        #    otherwise scale the totals by the field's share of production
        if field_filter in offloading_by_field:
            data.update(deepcopy(offloading_by_field[field_filter]))
            data["excel_mapping"] = EXCEL_SHEET_MAPPING
            return data

        fp_rows = data.get("field_performance", {}).get("rows", [])
        tot_act = data.get("field_performance", {}).get("total", {}).get("actual", 0)
        field_row = next((r for r in fp_rows if r.get("field") == field_filter), None)

        if field_row and tot_act > 0:
            f_act = field_row.get("actual", 0)
            ratio = round(f_act / tot_act, 4)

            # Scale Card 5
            op = data.get("offloading_planning", {})
            op["current_inventory"] = round(op.get("current_inventory", 2.4) * ratio, 2)
            op["target_offload"] = round(op.get("target_offload", 3.0) * ratio, 2)
            op["max_capacity"] = round(op.get("max_capacity", 3.5) * ratio, 2)
            op["actual_inventory"] = [
                round(x * ratio, 2) if x is not None else None for x in op.get("actual_inventory", [])
            ]
            op["p10_early"] = [
                round(x * ratio, 2) if x is not None else None for x in op.get("p10_early", [])
            ]
            op["p50_base"] = [
                round(x * ratio, 2) if x is not None else None for x in op.get("p50_base", [])
            ]
            op["p90_late"] = [
                round(x * ratio, 2) if x is not None else None for x in op.get("p90_late", [])
            ]
            if "milestones" in op:
                for m_key in op["milestones"]:
                    op["milestones"][m_key]["level"] = op["target_offload"]

            # Scale Card 6
            oe = data.get("offloading_estimation", {})
            oe["current_inventory"] = op["current_inventory"]
            oe["target_offload_level"] = op["target_offload"]
            oe["maximum_capacity"] = op["max_capacity"]
            oe["field"] = field_filter
    else:
        data["metadata"]["selected_field"] = "All Fields"

    data["excel_mapping"] = EXCEL_SHEET_MAPPING
    return data


# --- UI Route ---

@dashboard_bp.route("/")
def index():
    """Serve the 6-Card Production Planning Dashboard view."""
    return render_template("index.html")


# --- REST API Endpoints ---

@dashboard_bp.route("/api/health", methods=["GET"])
def health():
    """System health status check."""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "facility": _runtime_dataset.get("metadata", {}).get("facility", "Central Operations"),
    })


@dashboard_bp.route("/api/dashboard", methods=["GET"])
def get_dashboard_data():
    """Return complete 6-card payload with query filters."""
    field_filter = request.args.get("field", "All Fields")
    view = request.args.get("view", "field")
    if view == "terminal" and not get_terminal_csv_path().exists():
        return jsonify({
            "error": f"Terminal CSV not found: {get_terminal_csv_path()}. Set TERMINAL_CSV to its location."
        }), 404
    return jsonify(get_filtered_dashboard_data(field_filter=field_filter, view=view))


@dashboard_bp.route("/api/upload", methods=["POST"])
def upload_excel_workbook():
    """Ingest an uploaded Excel workbook with the 6 card sheets into memory."""
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded. Supply 'file' in multipart form."}), 400

    uploaded = request.files["file"]
    filename = uploaded.filename or "uploaded.xlsx"

    if not filename.lower().endswith((".xlsx", ".xlsm", ".xls")):
        return jsonify({"error": "Please upload an Excel workbook (.xlsx or .xlsm)."}), 400

    try:
        file_bytes = uploaded.read()
        global _runtime_dataset
        updated_data, sheets_count = parse_multi_sheet_excel(file_bytes, _runtime_dataset)
        _runtime_dataset = updated_data
        _runtime_dataset["metadata"]["last_updated"] = datetime.now().strftime("%d %b %Y %H:%M")

        return jsonify({
            "status": "success",
            "filename": filename,
            "sheets_parsed": sheets_count,
            "message": f"Successfully parsed {sheets_count} sheet(s) from {filename}.",
            "last_updated": _runtime_dataset["metadata"]["last_updated"],
        })
    except Exception as e:
        return jsonify({"error": f"Failed to parse Excel workbook: {str(e)}"}), 500


@dashboard_bp.route("/api/filter", methods=["POST"])
def apply_filters():
    """Update runtime filters (Period, Field, Facility, Well)."""
    payload = request.get_json() or {}
    meta = _runtime_dataset["metadata"]
    if "period" in payload:
        meta["period"] = payload["period"]
    if "field" in payload:
        meta["selected_field"] = payload["field"]
    if "facility" in payload:
        meta["facility"] = payload["facility"]
    meta["last_updated"] = datetime.now().strftime("%d %b %Y %H:%M")

    return jsonify({"status": "filters_applied", "metadata": meta})


@dashboard_bp.route("/api/activity_status", methods=["POST"])
def update_activity_status():
    """Dynamically update activity status from front-end dropdown."""
    payload = request.get_json() or {}
    idx = payload.get("index")
    status = payload.get("status")
    activities = _source_dataset(payload.get("view", "field")).get("planned_activities", [])
    if idx is not None and 0 <= idx < len(activities) and status:
        activities[idx]["status"] = status
        return jsonify({"status": "success", "index": idx, "new_status": status})
    return jsonify({"error": "Invalid index or status"}), 400


@dashboard_bp.route("/api/issue_status", methods=["POST"])
def update_issue_status():
    """Dynamically update issue status from front-end dropdown."""
    payload = request.get_json() or {}
    idx = payload.get("index")
    status = payload.get("status")
    issues = _source_dataset(payload.get("view", "field")).get("active_issues", [])
    if idx is not None and 0 <= idx < len(issues) and status:
        issues[idx]["status"] = status
        return jsonify({"status": "success", "index": idx, "new_status": status})
    return jsonify({"error": "Invalid index or status"}), 400


@dashboard_bp.route("/api/reset", methods=["POST"])
def reset_to_placeholder():
    """Reset dataset to default placeholder data."""
    global _runtime_dataset
    _runtime_dataset = get_default_dataset()
    return jsonify({
        "status": "reset_complete",
        "message": "Reset to default placeholder dataset.",
    })
