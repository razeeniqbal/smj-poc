"""
Loader for the ETL daily terminal summary CSV (am_daily_terminal_summary.csv).
Cleans the rows for the dashboard's Terminal view (see terminal_cards.py).

CSV location, first match wins:
1. the TERMINAL_CSV environment variable
2. the live ETL output folder (on the development machine)
3. the copy bundled in data/ (used by deployments such as Vercel)
"""

from datetime import datetime
import math
import os
from pathlib import Path
from typing import Any

import pandas as pd

ETL_TERMINAL_CSV = Path(
    r"C:\Users\AEM-Razeen\OneDrive - Aem Energy Solutions\Desktop\Razeen\AEM\DIC"
    r"\P4R\etl_dpr\output\am_daily_terminal_summary.csv"
)
BUNDLED_TERMINAL_CSV = Path(__file__).resolve().parent.parent / "data" / "am_daily_terminal_summary.csv"

NA_VALUES = ["N/A", "n/a", "NA", "-", ""]

# CSV column -> payload key, for the numeric columns the view uses
NUMERIC_COLUMNS = {
    "crude_daily_actual": "crude_actual",
    "crude_daily_target": "crude_target",
    "crude_monthly_production_target": "crude_monthly_target",
    "crude_bs_w": "bsw",
    "oil_in_water": "oiw",
    "condensate_daily_actual": "condensate_actual",
    "lopc_24hr": "lopc",
    "used_diesel": "diesel",
    "crude_lifted_volume": "lifted_volume",
    "crude_nominated_cargo_size": "cargo_size",
    "crude_stock": "crude_stock",
}

TEXT_COLUMNS = {
    "operator": "operator",
    "crude_lifting_party": "lifting_party",
    "crude_tanker_name": "tanker",
    "key_highlight": "highlight",
    "source_file": "source_file",
}


def get_terminal_csv_path() -> Path:
    if os.environ.get("TERMINAL_CSV"):
        return Path(os.environ["TERMINAL_CSV"])
    return ETL_TERMINAL_CSV if ETL_TERMINAL_CSV.exists() else BUNDLED_TERMINAL_CSV


def _clean(value: Any) -> Any:
    """Convert pandas missing values to None so the payload is valid JSON."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if value is pd.NA or value is pd.NaT:
        return None
    return value


def load_terminal_data(csv_path: Path | None = None) -> dict[str, Any]:
    """Load, de-duplicate and sort the terminal summary, and report data-quality issues."""
    path = Path(csv_path) if csv_path else get_terminal_csv_path()
    df = pd.read_csv(path, na_values=NA_VALUES, keep_default_na=True)
    raw_count = len(df)

    df["report_start_date"] = pd.to_datetime(df["report_start_date"], errors="coerce")
    df = df.dropna(subset=["report_start_date"])
    df["report_day"] = df["report_start_date"].dt.normalize()
    if "submission_date" in df.columns:
        df["submission_date"] = pd.to_datetime(df["submission_date"], errors="coerce")
        df = df.sort_values(["report_day", "submission_date"])
    if "operator" not in df.columns:
        df["operator"] = "Terminal"
    df["operator"] = df["operator"].fillna("Terminal").astype(str).str.strip()

    # Keep the latest submission when a day is reported more than once
    dup_mask = df.duplicated(subset=["operator", "report_day"], keep="last")
    duplicate_days = sorted({d.strftime("%Y-%m-%d") for d in df.loc[dup_mask, "report_day"]})
    df = df.loc[~dup_mask].sort_values(["operator", "report_day"]).reset_index(drop=True)

    for col in NUMERIC_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    rows = []
    for _, r in df.iterrows():
        row = {"date": r["report_day"].strftime("%Y-%m-%d")}
        for col, key in NUMERIC_COLUMNS.items():
            row[key] = _clean(float(r[col])) if col in df.columns and pd.notna(r[col]) else None
        for col, key in TEXT_COLUMNS.items():
            val = r[col] if col in df.columns else None
            row[key] = str(val).strip() if val is not None and pd.notna(val) else None
        rows.append(row)

    # Missing report days per operator, within that operator's own date span
    missing_days: dict[str, list[str]] = {}
    for op, grp in df.groupby("operator"):
        full = pd.date_range(grp["report_day"].min(), grp["report_day"].max(), freq="D")
        gaps = sorted(set(full) - set(grp["report_day"]))
        if gaps:
            missing_days[op] = [d.strftime("%Y-%m-%d") for d in gaps]

    # Rows where the tanker name sits in the lifting-party column (shifted source cells)
    suspect_shift = [
        row["date"]
        for row in rows
        if row["lifting_party"] and row["lifting_party"].upper().startswith("MT ")
    ]

    return {
        "source": {
            "path": str(path),
            "file": path.name,
            "modified": datetime.fromtimestamp(os.path.getmtime(path)).strftime("%d %b %Y %H:%M"),
        },
        "units": {
            "crude": "kbbl/d",
            "volume": "kbbl",
            "bsw": "%",
            "oiw": "ppm",
            "condensate": "kbbl/d",
        },
        "rows": rows,
        "liftings": _lifting_events(rows),
        "quality": {
            "raw_rows": raw_count,
            "rows": len(rows),
            "duplicate_days": duplicate_days,
            "missing_days": missing_days,
            "suspect_column_shift": suspect_shift,
        },
    }


def _lifting_events(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Collapse consecutive daily reports of the same lifted cargo into one event.
    Reports repeat the lifted volume for several days, so volumes are never summed per day.
    """
    events: list[dict[str, Any]] = []
    for row in rows:
        vol = row["lifted_volume"]
        if not vol or vol <= 0:
            continue
        last = events[-1] if events else None
        if (
            last
            and last["operator"] == row["operator"]
            and last["tanker"] == row["tanker"]
            and last["volume"] == vol
        ):
            last["last_reported"] = row["date"]
            continue
        events.append({
            "operator": row["operator"],
            "date": row["date"],
            "last_reported": row["date"],
            "tanker": row["tanker"],
            "lifting_party": row["lifting_party"],
            "volume": vol,
            "cargo_size": row["cargo_size"],
        })
    return events
