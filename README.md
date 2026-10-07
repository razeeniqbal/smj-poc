# Production Planning Dashboard (6-Card Operations Cockpit)

A lightweight, production-grade web dashboard service engineered for real-time facility monitoring, field performance tracking, operational activity management, and scenario forecasting.

---

## 📋 Table of Contents

- [Quickstart: How to Run](#-quickstart-how-to-run)
- [Repository Architecture & Directory Tree](#-repository-architecture--directory-tree)
- [Detailed Structure of Each File](#-detailed-structure-of-each-file)
- [Colleague Integration Guide (Blueprint)](#-colleague-integration-guide-blueprint)
- [The 6 Operations Cards](#-the-6-operations-cards)
- [Excel Workbook Upload Schema](#-excel-workbook-upload-schema)
- [REST API Reference](#-rest-api-reference)
- [Automated Testing](#-automated-testing)

---

## 🚀 Quickstart: How to Run

### 1. Prerequisites & Setup
Activate your Python virtual environment and install the required dependencies:

```bash
# Windows PowerShell / CMD
.\.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Launch the Application
Start the dashboard using either entry point:

```bash
# Recommended: Standalone CLI launcher (supports --host, --port, --no-debug)
python run.py

# Alternative: Direct WSGI module
python app.py
```

### 3. Open in Browser
Navigate to:
👉 **`http://127.0.0.1:5000`**

---

## 📂 Repository Architecture & Directory Tree

```
SMJ_DASHBOARD/
├── .vscode/
│   ├── extensions.json            # Recommended workspace extensions
│   ├── launch.json                # VS Code Run & Debug configuration
│   └── settings.json              # Python interpreter & explorer configuration
├── dashboard/                     # Self-contained Flask Blueprint package
│   ├── static/                    # Frontend assets
│   │   ├── css/
│   │   │   └── style.css          # Glassmorphic dark theme & responsive layouts
│   │   └── js/
│   │       ├── dashboard.js       # ECharts controller, UI logic & API handlers
│   │       └── echarts.min.js     # Self-hosted Apache ECharts library (offline)
│   ├── templates/
│   │   └── index.html             # Single-page cockpit dashboard UI template
│   ├── __init__.py                # Package export: dashboard_bp & create_app()
│   ├── analytics.py               # Pure math models, forecasting & Excel ingestion
│   ├── placeholder_data.py        # Baseline operational dataset & Excel schemas
│   └── routes.py                  # UI route & REST API endpoints
├── tests/
│   ├── __init__.py                # Test package marker
│   └── test_dashboard.py          # Standalone & Colleague Blueprint test suite
├── .gitignore                     # Git ignore rules for Python, IDE, and temp files
├── app.py                         # WSGI / Flask module entry point
├── README.md                      # Project documentation & file breakdown
├── requirements.txt               # Dependencies (Flask, pandas, openpyxl)
└── run.py                         # CLI entry point with command-line arguments
```

---

## 🔍 Detailed Structure of Each File

### 1. Root-Level Entry Points & Configurations

#### [`run.py`](run.py)
- **Role**: Primary Command-Line Interface (CLI) launcher for running the dashboard standalone.
- **Key Components**:
  - `main()`: Parses CLI arguments (`--host`, default `127.0.0.1`; `--port`, default `5000`; `--no-debug`, disables Flask debug mode).
  - Automatically ensures repository root is in `sys.path`.
  - Instantiates the application via `create_app(debug=not args.no_debug)`.
  - Prints startup status banners and runs the Flask development/production server.
- **Data Flow**: Invokes `dashboard.create_app()` and binds the HTTP server to the specified network interface.

#### [`app.py`](app.py)
- **Role**: Standard WSGI application module for direct execution and production deployment servers (e.g., Gunicorn, Waitress).
- **Key Components**:
  - Imports pre-instantiated `app` and factory `create_app` from `dashboard`.
  - Directly runnable with `python app.py`, `flask run`, or `gunicorn app:app`.
- **Data Flow**: Exposes the top-level `app` WSGI callable.

#### [`requirements.txt`](requirements.txt)
- **Role**: Manifest of required third-party Python packages.
- **Key Dependencies**:
  - `Flask>=3.0.0`: Web framework, Blueprint routing, and template rendering.
  - `openpyxl>=3.1.5`: Reading and extracting cell data from Excel workbooks (`.xlsx`, `.xlsm`).
  - `pandas>=2.2.0`: Tabular data processing, column normalization, and time-series conversions.

#### [`.gitignore`](.gitignore)
- **Role**: Prevents unwanted cache files, virtual environments, and local editor state from being tracked.
- **Key Rules**: Excludes `__pycache__/`, `*.pyc`, `.venv/`, `.vscode/` user caches, Excel temporary lock files (`~$*.xlsx`), and OS metadata (`.DS_Store`, `Thumbs.db`).

---

### 2. Backend Package (`dashboard/`)

#### [`dashboard/__init__.py`](dashboard/__init__.py)
- **Role**: Package initializer and Application Factory definition.
- **Key Components**:
  - `create_app(debug: bool = True) -> Flask`: Instantiates Flask, configures local templates (`templates/`) and static assets (`static/`), sets maximum file upload size to 32 MB (`MAX_CONTENT_LENGTH`), and mounts `dashboard_bp` at root.
  - `app = create_app()`: Default ready-to-run instance for WSGI runners.
  - `__all__ = ["dashboard_bp", "create_app", "app"]`: Clean explicit public API.
- **Data Flow**: Connects `dashboard.routes.dashboard_bp` with the Flask application container.

#### [`dashboard/routes.py`](dashboard/routes.py)
- **Role**: Defines the Blueprint (`dashboard_bp`), UI page route, and all REST API endpoints.
- **Key Components**:
  - `_runtime_dataset`: In-memory global store containing the active 6-card dataset (initialized from `get_default_dataset()`).
  - `get_filtered_dashboard_data(field_filter)`: Applies field filtering across Card 1 (trend & events), Card 3 (activities), Card 4 (issues), and rescales inventory projections for Card 5 and Card 6 based on field production ratios.
  - `@dashboard_bp.route("/")`: Serves the single-page cockpit dashboard via `render_template("index.html")`.
  - `@dashboard_bp.route("/api/health")`: Health check returning system status and facility info.
  - `@dashboard_bp.route("/api/dashboard")`: Returns the complete 6-card payload (supports `?field=<name>`).
  - `@dashboard_bp.route("/api/upload", methods=["POST"])`: Handles Excel multipart file uploads, invokes `parse_multi_sheet_excel()`, and replaces `_runtime_dataset` in memory.
  - `@dashboard_bp.route("/api/filter", methods=["POST"])`: Updates period, field, or facility filter metadata.
  - `@dashboard_bp.route("/api/activity_status", methods=["POST"])`: Updates the status of an activity in Card 3.
  - `@dashboard_bp.route("/api/issue_status", methods=["POST"])`: Updates the status of an issue in Card 4.
  - `@dashboard_bp.route("/api/reset", methods=["POST"])`: Restores the runtime dataset back to baseline placeholder data.
- **Data Flow**: Bridges HTTP client requests from `dashboard.js` with `analytics.py` and `placeholder_data.py`.

#### [`dashboard/analytics.py`](dashboard/analytics.py)
- **Role**: Unified mathematical calculation engine and multi-sheet Excel ingestion parser.
- **Key Components**:
  - **Forecasting Models**:
    - `compute_exponential_forecast(actuals, targets, alpha=0.35)`: Mathematical exponential smoothing and recovery model that anchors to the last actual production point and projects forward toward target quotas.
    - `compute_offloading_projections(dates, daily_actuals, daily_targets, ...)`: Simulates cumulative terminal crude inventory and generates P10 (Accelerated, +12%), P50 (Base), and P90 (Conservative, -12%) trajectory branches until reaching the 3.0 MMbbl offload threshold.
  - **Text & Column Sanitizers**:
    - `_normalize_col_name()` & `_find_column()`: Case- and punctuation-insensitive column matching.
    - `format_chart_date()`: Standardizes dates into clean chart labels (e.g., `"1 Sep"`).
    - `is_valid_event_highlight()`: Filters out empty remarks, routine placeholders, and filler text.
  - **Ingestion Pipeline**:
    - `parse_multi_sheet_excel(file_bytes, current_data)`: Parses uploaded Excel workbooks (supports both single-sheet Daily Operational Reports and multi-sheet workbooks), extracts tabular data for Cards 1 through 6, recalculates mathematical models, and returns updated structured dictionaries.
- **Data Flow**: Ingests raw workbook bytes from `routes.py`, calculates derived metrics, and populates the dataset.

#### [`dashboard/placeholder_data.py`](dashboard/placeholder_data.py)
- **Role**: Baseline operational data supplier and declarative Excel column schema definitions.
- **Key Components**:
  - `EXCEL_SHEET_MAPPING`: Mapping schema detailing sheet names, target cards, required/optional columns, and descriptions for Cards 1 to 6.
  - `get_default_dataset() -> dict`: Factory producing a realistic operational baseline with complete data for all 6 cards:
    - `metadata`: Facility name, period, last updated timestamp, and available fields list.
    - `production_trend`: Daily dates, plan, actual, forecast series, and operational milestone event pins.
    - `field_performance`: Table rows for Field A, B, C, D with plan, actual, variance, attainment %, and 30-day sparkline arrays.
    - `planned_activities`: Upcoming maintenance and field operations with dates, impact, and status.
    - `active_issues`: Operational downtime/trips with severity, status, and recovery dates.
    - `offloading_planning`: Time-series inventory curves and P10/P50/P90 projection models.
    - `offloading_estimation`: Metric callouts (current inventory, target ullage, max capacity) and scenario ETA cards.
- **Data Flow**: Feeds `routes.py` with default data on application start or upon calling `/api/reset`.

---

### 3. Frontend Assets (`dashboard/templates/` & `dashboard/static/`)

#### [`dashboard/templates/index.html`](dashboard/templates/index.html)
- **Role**: The single-page responsive dashboard template.
- **Key Components**:
  - **Header Bar (`<header class="app-header">`)**: Displays the dashboard title, facility status badge, period selector, field selector, "Apply" button, "Upload Excel" button, and "Reset" button.
  - **Operations Cockpit Grid (`<main class="dashboard-grid">`)**:
    - Card 1: Production Trend (`#chart-prod-trend` container and milestone pin legend).
    - Card 2: Field Performance (`#table-field-perf` table container).
    - Card 3: Planned Activities (`#table-activities` with dynamic status selector dropdowns).
    - Card 4: Active Issues & Mitigation (`#table-issues` with interactive status selectors and bi-directional hover triggers).
    - Card 5: Offloading Planning (`#chart-offload-plan` container with P10/P50/P90 scenario curves).
    - Card 6: Offloading Estimation (`#metrics-offload` summary tiles and scenario ETA cards).
  - **Hidden Upload Input (`#excel-file-input`)**: Triggers native file selection dialog for `.xlsx`/`.xlsm` uploads.
  - **Toast Notifications Container (`#toast-container`)**: Floating notifications for user actions.

#### [`dashboard/static/css/style.css`](dashboard/static/css/style.css)
- **Role**: Styling and responsive design system for the entire application.
- **Key Components**:
  - **Design Tokens**: CSS variables for surface hues, slate backgrounds, text contrast, and status accents (emerald, amber, rose, cyan, purple).
  - **Layout Engine**: Responsive CSS Grid cockpit (2-column layout on desktop, auto-collapsing to single-column on smaller screens).
  - **Card System**: Glassmorphic dark surfaces with subtle border glows, headers, and metric stat badges.
  - **Tables & Elements**: Custom-styled status dropdowns, attainment pills, SVG sparkline containers, and action buttons.
  - **Toast Notifications**: Animated floating feedback banners for user interactions and upload progress.

#### [`dashboard/static/js/dashboard.js`](dashboard/static/js/dashboard.js)
- **Role**: Client-side application controller, chart renderer, and API communication layer.
- **Key Components**:
  - **Chart Management**: Initializes and manages Apache ECharts instances for Card 1 (`initProdTrendChart`) and Card 5 (`initOffloadPlanChart`), with automated window resize observers.
  - **DOM Rendering Handlers**:
    - `renderFieldPerformanceTable(data)`: Generates tabular rows, attainment pill colors, and inline SVG sparklines.
    - `renderPlannedActivities(data)`: Builds activity rows and binds status change events to `/api/activity_status`.
    - `renderActiveIssues(data)`: Builds issue rows, binds status changes to `/api/issue_status`, and registers mouseenter/mouseleave hover events to highlight corresponding Card 1 markers.
    - `renderOffloadingEstimation(data)`: Populates KPI metric callouts and scenario estimation cards.
  - **API Client**:
    - `loadDashboard(field)`: Fetches `/api/dashboard?field=...` and updates all 6 cards.
    - `uploadWorkbook(file)`: Sends `FormData` payload to `/api/upload` and re-renders the dashboard.
    - `applyFilters()`: Updates runtime filters via `/api/filter`.
    - `resetDashboard()`: Restores baseline dataset via `/api/reset`.
  - **Notification Helper**: `showToast(message, type)` displays non-blocking toast notifications.

#### [`dashboard/static/js/echarts.min.js`](dashboard/static/js/echarts.min.js)
- **Role**: Production build of Apache ECharts library (~1 MB).
- **Key Benefit**: Bundled locally to guarantee **100% offline functionality** without requiring any external internet access or CDN links.

---

### 4. Automated Tests (`tests/`)

#### [`tests/test_dashboard.py`](tests/test_dashboard.py)
- **Role**: Complete automated test suite using Python's standard `unittest` framework.
- **Key Test Classes & Methods**:
  - `TestStandaloneDashboard`:
    - `test_api_health`: Verifies `/api/health` returns status `healthy` and HTTP 200.
    - `test_api_dashboard_all_6_cards_present`: Verifies `/api/dashboard` contains all 6 required card payloads.
    - `test_field_filtering`: Verifies field filtering updates Card 1, 3, 4, and rescales Card 5 & 6.
    - `test_activity_status_update`: Validates POST `/api/activity_status` dynamically updates activity status.
    - `test_issue_status_update`: Validates POST `/api/issue_status` dynamically updates issue status.
    - `test_reset_endpoint`: Validates POST `/api/reset` successfully restores default baseline data.
    - `test_upload_excel_workbook`: Tests in-memory multi-sheet Excel ingestion via POST `/api/upload`.
  - `TestColleagueIntegration`:
    - `test_colleague_app_blueprint_mounting`: Validates registering `dashboard_bp` directly inside an external/host Flask application.

#### [`tests/__init__.py`](tests/__init__.py)
- **Role**: Package marker file allowing standard `unittest discover` execution.

---

### 5. IDE Configuration (`.vscode/`)

#### [`.vscode/settings.json`](.vscode/settings.json)
- **Role**: Configures the workspace editor experience in Visual Studio Code.
- **Key Settings**:
  - Points Python interpreter directly to the local virtual environment (`.venv/Scripts/python.exe`).
  - Hides generated `__pycache__` folders from the file tree.
  - Sorts explorer files cleanly by file type (`"explorer.sortOrder": "type"`).
  - Disables file nesting (`"explorer.fileNesting.enabled": false`) so all files remain immediately visible.

#### [`.vscode/launch.json`](.vscode/launch.json)
- **Role**: One-click VS Code Run & Debug configuration.
- **Key Settings**: Pre-configures a `"Launch Dashboard Server"` debug profile that executes `run.py` with `FLASK_DEBUG=1`.

#### [`.vscode/extensions.json`](.vscode/extensions.json)
- **Role**: Recommends essential VS Code extensions for python development (`ms-python.python`, `ms-python.vscode-pylance`).

---

## 🤝 Colleague Integration Guide (Blueprint)

The entire dashboard is packaged as a standard, self-contained Flask Blueprint (`dashboard_bp`). A colleague can mount it into their application in **2 lines of code**:

```python
from flask import Flask
from dashboard import dashboard_bp

app = Flask(__name__)

# Register the dashboard Blueprint at the root URL:
app.register_blueprint(dashboard_bp)

# Or mount under a custom URL prefix:
# app.register_blueprint(dashboard_bp, url_prefix="/operations")

if __name__ == "__main__":
    app.run(port=5000, debug=True)
```

All templates, static files, REST endpoints, and UI views are self-contained and require zero additional configuration.

---

## 📊 The 6 Operations Cards

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       PRODUCTION PLANNING DASHBOARD                         │
├─────────────────────────────────────────────────────────────────────────────┤
│  [ Card 1: Production Trend ]       │  [ Card 2: Field Performance ]        │
│  - Daily Plan, Actual & Forecast    │  - Plan vs. Actual by Field           │
│  - Interactive Milestone/Dip Pins   │  - Attainment Pills & Sparklines      │
├─────────────────────────────────────┼───────────────────────────────────────┤
│  [ Card 3: Planned Activities ]     │  [ Card 4: Active Issues & Action ]   │
│  - Scheduled Field Operations       │  - Unresolved trips, leaks & downtime │
│  - Status Toggles (On Schedule etc) │  - Bi-directional link with Card 1    │
├─────────────────────────────────────┼───────────────────────────────────────┤
│  [ Card 5: Offloading Planning ]    │  [ Card 6: Offloading Estimation ]    │
│  - Inventory MMbbl Time-Series      │  - Offload Target (3.0 MMbbl) ETA     │
│  - P10 (Early) / P50 / P90 Proj.    │  - Max Capacity (3.5 MMbbl) Proj.     │
└─────────────────────────────────────┴───────────────────────────────────────┘
```

1. **Card 1 — Production Trend**: Area and line chart showing Plan (kbopd), Actual (kbopd), and Forecast (kbopd) with interactive operational event pins.
2. **Card 2 — Field Performance**: Tabular breakdown of production performance across all fields plus Total, showing variance, attainment percentage badges, and 30-day SVG sparkline trends.
3. **Card 3 — Planned Activities**: Upcoming field operations with date, impact, and interactive status toggles (*On Schedule*, *Delayed*, *Completed*).
4. **Card 4 — Active Issues & Mitigation**: Incident register with severity ratings, root cause details, recovery dates, interactive status selectors, and bi-directional hover links to Card 1 event pins.
5. **Card 5 — Offloading Planning**: Cumulative inventory trajectory against the 3.5 MMbbl maximum capacity and 3.0 MMbbl target offload level, featuring P10 (Early), P50 (Base), and P90 (Late) scenario projections.
6. **Card 6 — Offloading Estimation**: KPI summary callouts (Current Inventory, Target Ullage, Max Capacity) and scenario projection ETA dates.

---

## 📑 Excel Workbook Upload Schema

When uploading an Excel workbook via the **Upload Excel** button, the ingestion engine automatically maps the following 6 sheets into their respective cards:

| Sheet Name | Mapped Card | Supported Columns |
| :--- | :--- | :--- |
| `Production_Trend` | Card 1: Production Trend | `Date`, `Plan_kbopd`, `Actual_kbopd`, `Forecast_kbopd`, `Event_Title`, `Event_Impact`, `Related_Issue` |
| `Field_Performance` | Card 2: Field Performance | `Field`, `Plan_kbopd`, `Actual_kbopd`, `Variance_kbopd`, `Attainment_Pct` |
| `Planned_Activities` | Card 3: Planned Activities | `Date`, `Activity`, `Field`, `Expected_Impact`, `Status` |
| `Active_Issues` | Card 4: Active Issues & Mitigation | `Issue`, `Field`, `Impact`, `Status`, `Recovery_Date`, `Details` |
| `Offloading_Planning` | Card 5: Offloading Planning | `Date`, `Actual_Inventory_MMbbl`, `P10_Early_MMbbl`, `P50_Base_MMbbl`, `P90_Late_MMbbl` |
| `Offloading_Estimation` | Card 6: Offloading Estimation | `Scenario`, `Estimated_Offload_Date`, `Days_From_Now` |

> *Note: Single-sheet operational Daily Operational Reports (DOR) containing `report_date`, `crude_daily_actual`, and `crude_daily_target` are also automatically recognized and parsed into Card 1.*

---

## 🌐 REST API Reference

| Endpoint | Method | Payload / Parameters | Description |
| :--- | :---: | :--- | :--- |
| `/` | `GET` | None | Serves the single-page HTML dashboard interface. |
| `/api/health` | `GET` | None | Returns system health status, timestamp, and active facility name. |
| `/api/dashboard` | `GET` | `?field=<field_name>` (optional) | Returns the full 6-card payload with field filtering applied. |
| `/api/upload` | `POST` | `multipart/form-data` with `file` | Ingests an uploaded Excel workbook (`.xlsx`/`.xlsm`) into memory. |
| `/api/filter` | `POST` | `{"field": "...", "period": "..."}` | Updates runtime filter metadata. |
| `/api/activity_status` | `POST` | `{"index": 0, "status": "Completed"}` | Dynamically updates the status of a planned activity. |
| `/api/issue_status` | `POST` | `{"index": 0, "status": "Mitigated"}` | Dynamically updates the status of an active issue. |
| `/api/reset` | `POST` | None | Resets runtime data back to the default baseline dataset. |

---

## 🧪 Automated Testing

Run the test suite using Python's standard `unittest` runner:

```bash
python -m unittest discover tests -v
```

All 8 tests execute completely in-memory in under 0.2 seconds, verifying:
- API health check and response schemas.
- 6-card payload generation and field filtering logic.
- Dynamic activity and issue status mutations.
- Multi-sheet Excel workbook parsing.
- Blueprint mounting inside an external colleague Flask application.

---

## 🛡️ Standalone & Security Guarantee

- **In-Memory Ingestion**: All Excel workbook parsing and calculations occur entirely in memory (`io.BytesIO`) without temporary disk writes.
- **100% Offline Asset Delivery**: Apache ECharts and all styles/scripts are bundled locally in `dashboard/static/`. No CDN calls, telemetry, or external internet connections are required.
- **Completely Decoupled**: The `dashboard` package functions as an isolated, standalone service or a drop-in Flask Blueprint with zero required external dependencies.

