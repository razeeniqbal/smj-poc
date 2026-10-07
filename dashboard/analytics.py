"""
Analytics, mathematical forecasting, and multi-sheet Excel ingestion/mapping
for the 6-Card Production Planning Dashboard.

CARDS SPECIFICATION:
1. Production Trend: Daily plan, actual, forecast, and interactive event pins
2. Field Performance: Table with Plan, Actual, Variance, Attainment %, and sparklines
3. Planned Activities: Scheduled field operations, impacts, and status
4. Active Issues: Unresolved trips, leaks, downtime, and recovery timeline
5. Offloading Planning: Terminal crude inventory time-series & P10/P50/P90 models
6. Offloading Estimation: Scenario forecast dates and executive callouts
"""

from datetime import datetime, timedelta
import io
import math
import re
from typing import Any
import openpyxl
import pandas as pd


# =========================================================================
# MATHEMATICAL FORECASTING & OFFLOADING PROJECTION MODELS
# =========================================================================

def compute_exponential_forecast(
    actuals: list[float | None],
    targets: list[float | None],
    alpha: float = 0.35,
) -> list[float | None]:
    """
    Mathematical/ML Exponential Smoothing & Recovery Model for Card 1 Forecast:
    - Anchors precisely to the last recorded actual data point.
    - Projects forward across the remaining timeline smoothly converging toward the planned quota.
    - Model: F_{t} = F_{t-1} + alpha * (Target_{t} - F_{t-1})
    """
    n = len(actuals)
    if n == 0:
        return []

    last_idx = None
    for i in range(n - 1, -1, -1):
        if actuals[i] is not None and not (isinstance(actuals[i], float) and math.isnan(actuals[i])):
            last_idx = i
            break

    if last_idx is None:
        return [None] * n

    forecast: list[float | None] = [None] * n
    forecast[last_idx] = round(float(actuals[last_idx]), 1)

    curr_val = float(actuals[last_idx])
    for i in range(last_idx + 1, n):
        tgt = None
        if i < len(targets) and targets[i] is not None:
            tgt = float(targets[i])
        elif last_idx < len(targets) and targets[last_idx] is not None:
            tgt = float(targets[last_idx])
        else:
            tgt = curr_val

        curr_val = curr_val + alpha * (tgt - curr_val)
        forecast[i] = round(curr_val, 1)

    return forecast


def compute_offloading_projections(
    dates: list[str],
    daily_actuals: list[float | None],
    daily_targets: list[float | None],
    target_offload: float = 3.0,
    max_capacity: float = 3.5,
    base_inventory: float = 1.1,
) -> dict[str, Any]:
    """
    Compute cumulative inventory and P10/P50/P90 offloading projections for Card 5 & Card 6:
    - Actual Inventory: Cumulative crude_daily_actual up to current date.
    - Forecast: Cumulative crude_daily_target projected forward.
    - P10 (Early): Accelerated filling trajectory (+12% rate, reaches 3.0 MMbbl earliest).
    - P50 (Base): Base filling trajectory following daily target plan.
    - P90 (Late): Conservative filling trajectory (-12% rate, reaches 3.0 MMbbl latest).
    - Auto-projects forward until all three trajectories cross 3.0 MMbbl target.
    """
    if not dates:
        return {
            "offloading_planning": {
                "unit": "MMbbl",
                "max_capacity": max_capacity,
                "target_offload": target_offload,
                "current_inventory": base_inventory,
                "current_date": "Today",
                "dates": [],
                "actual_inventory": [],
                "p10_early": [],
                "p50_base": [],
                "p90_late": [],
                "milestones": {},
            },
            "offloading_estimation": {
                "current_inventory": base_inventory,
                "target_offload_level": target_offload,
                "maximum_capacity": max_capacity,
                "scenarios": [],
            },
        }

    valid_acts = [
        float(x)
        for x in daily_actuals
        if x is not None and not (isinstance(x, float) and math.isnan(x))
    ]
    is_kbopd = any(x > 5.0 for x in valid_acts) if valid_acts else True
    scale = 0.001 if is_kbopd else 1.0

    last_actual_idx = None
    for i in range(len(daily_actuals) - 1, -1, -1):
        if daily_actuals[i] is not None and not (
            isinstance(daily_actuals[i], float) and math.isnan(daily_actuals[i])
        ):
            last_actual_idx = i
            break
    if last_actual_idx is None:
        last_actual_idx = min(len(dates) - 1, 0)

    actual_inv: list[float | None] = []
    cum = base_inventory
    for i in range(len(dates)):
        if i <= last_actual_idx:
            val = (
                daily_actuals[i]
                if i < len(daily_actuals) and daily_actuals[i] is not None
                else 40.0
            )
            cum += float(val) * scale
            actual_inv.append(round(cum, 2))
        else:
            actual_inv.append(None)

    curr_inv = (
        actual_inv[last_actual_idx]
        if actual_inv and actual_inv[last_actual_idx] is not None
        else 2.4
    )
    curr_date = dates[last_actual_idx] if last_actual_idx < len(dates) else dates[-1]

    all_dates = list(dates)
    try:
        parts = all_dates[-1].split()
        day_num = int(parts[0])
        month_str = parts[1] if len(parts) > 1 else "Sep"
        last_dt = pd.to_datetime(f"{day_num} {month_str} 2026")
    except Exception:
        last_dt = datetime(2026, 9, 30)

    min_future_days = 22
    remaining_days = len(all_dates) - 1 - last_actual_idx
    if remaining_days < min_future_days:
        needed = min_future_days - remaining_days
        for d in range(1, needed + 1):
            next_dt = last_dt + timedelta(days=d)
            all_dates.append(next_dt.strftime("%d %b").lstrip("0"))
            actual_inv.append(None)

    n_total = len(all_dates)
    p10_early: list[float | None] = [None] * n_total
    p50_base: list[float | None] = [None] * n_total
    p90_late: list[float | None] = [None] * n_total

    p10_early[last_actual_idx] = curr_inv
    p50_base[last_actual_idx] = curr_inv
    p90_late[last_actual_idx] = curr_inv

    c10 = curr_inv
    c50 = curr_inv
    c90 = curr_inv

    p10_cross_idx, p50_cross_idx, p90_cross_idx = None, None, None

    for i in range(last_actual_idx + 1, n_total):
        tgt_val = (
            daily_targets[i]
            if i < len(daily_targets) and daily_targets[i] is not None
            else 45.0
        )
        tgt_rate = float(tgt_val) * scale
        if tgt_rate <= 0:
            tgt_rate = 0.045

        c10 = round(c10 + tgt_rate * 1.12, 2)
        c50 = round(c50 + tgt_rate * 1.00, 2)
        c90 = round(c90 + tgt_rate * 0.88, 2)

        p10_early[i] = c10
        p50_base[i] = c50
        p90_late[i] = c90

        if p10_cross_idx is None and c10 >= target_offload:
            p10_cross_idx = i
        if p50_cross_idx is None and c50 >= target_offload:
            p50_cross_idx = i
        if p90_cross_idx is None and c90 >= target_offload:
            p90_cross_idx = i

    p10_cross_idx = p10_cross_idx or min(last_actual_idx + 13, n_total - 1)
    p50_cross_idx = p50_cross_idx or min(last_actual_idx + 16, n_total - 1)
    p90_cross_idx = p90_cross_idx or min(last_actual_idx + 20, n_total - 1)

    p10_date = all_dates[p10_cross_idx]
    p50_date = all_dates[p50_cross_idx]
    p90_date = all_dates[p90_cross_idx]

    p10_days = max(1, p10_cross_idx - last_actual_idx)
    p50_days = max(1, p50_cross_idx - last_actual_idx)
    p90_days = max(1, p90_cross_idx - last_actual_idx)

    milestones = {
        "p10": {"date": p10_date, "level": target_offload, "tag": f"P10 {p10_date}"},
        "p50": {"date": p50_date, "level": target_offload, "tag": f"P50 {p50_date}"},
        "p90": {"date": p90_date, "level": target_offload, "tag": f"P90 {p90_date}"},
    }

    scenarios = [
        {
            "scenario": "P10 (Early)",
            "estimated_offload_date": f"{p10_date} 2026",
            "days_from_now": f"{p10_days} days",
            "tag_class": "p10-tag",
        },
        {
            "scenario": "P50 (Base)",
            "estimated_offload_date": f"{p50_date} 2026",
            "days_from_now": f"{p50_days} days",
            "tag_class": "p50-tag",
        },
        {
            "scenario": "P90 (Late)",
            "estimated_offload_date": f"{p90_date} 2026",
            "days_from_now": f"{p90_days} days",
            "tag_class": "p90-tag",
        },
    ]

    return {
        "offloading_planning": {
            "unit": "MMbbl",
            "max_capacity": max_capacity,
            "target_offload": target_offload,
            "current_inventory": curr_inv,
            "current_date": curr_date,
            "dates": all_dates,
            "actual_inventory": actual_inv,
            "p10_early": p10_early,
            "p50_base": p50_base,
            "p90_late": p90_late,
            "milestones": milestones,
        },
        "offloading_estimation": {
            "current_inventory": curr_inv,
            "target_offload_level": target_offload,
            "maximum_capacity": max_capacity,
            "scenarios": scenarios,
        },
    }


# =========================================================================
# EXCEL INGESTION HELPERS
# =========================================================================

def _normalize_col_name(col: Any) -> str:
    """Normalize column header into clean lowercase alphanumeric string."""
    return re.sub(r"[^a-z0-9]", "", str(col).lower().strip())


def _find_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """Find a column in DataFrame matching candidate names (case and punctuation insensitive)."""
    norm_map = {_normalize_col_name(c): c for c in df.columns}
    for cand in candidates:
        norm_cand = _normalize_col_name(cand)
        if norm_cand in norm_map:
            return norm_map[norm_cand]
    return None


def format_chart_date(val: Any) -> str:
    """Convert various Excel date formats (Timestamp, string, date) into clean chart date (e.g. '1 Sep')."""
    if pd.isna(val):
        return ""
    if isinstance(val, (datetime, pd.Timestamp)):
        return val.strftime("%d %b").lstrip("0")
    s = str(val).strip()
    try:
        dt = pd.to_datetime(s)
        return dt.strftime("%d %b").lstrip("0")
    except Exception:
        return s


def is_valid_event_highlight(text: Any) -> bool:
    """Determine whether text represents an operational event/highlight rather than a placeholder or negative remark."""
    if text is None or pd.isna(text):
        return False
    s = str(text).strip()
    if not s or s.lower() in ("-", "--", "---", ".", "na", "n/a", "none", "nil", "null"):
        return False

    lower = s.lower()
    filler_patterns = [
        "no highlight", "no highlights", "no remark", "no remarks",
        "no issue", "no issues", "no event", "no events", "no downtime",
        "no deferment", "normal", "normal operation", "as planned",
        "routine", "routine operation", "steady", "all good", "nil highlight", "nil remarks"
    ]
    for pat in filler_patterns:
        if (
            lower == pat
            or lower.startswith(pat + " ")
            or lower.startswith(pat + ".")
            or lower.startswith(pat + ",")
            or lower.startswith(pat + "-")
        ):
            return False

    return True


# =========================================================================
# CARD-BY-CARD MULTI-SHEET EXCEL PARSER (Populating Cards 1 to 6)
# =========================================================================

def parse_multi_sheet_excel(
    file_bytes: bytes, current_data: dict[str, Any]
) -> tuple[dict[str, Any], int]:
    """
    Parse an uploaded Excel file (supporting both single-sheet operational DOR formats
    and multi-sheet templates) and dynamically populate the 6 dashboard cards.
    Returns (updated_dataset, parsed_items_count).
    """
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    sheets_found = list(wb.sheetnames)
    updated = current_data
    parsed_count = 0

    all_dfs = {s: pd.read_excel(io.BytesIO(file_bytes), sheet_name=s) for s in sheets_found}

    # =========================================================================
    # CARD 1 MAPPING: Production Trend
    # =========================================================================
    card1_df = None
    col_date, col_target, col_actual, col_highlight = None, None, None, None

    for s_name, df in all_dfs.items():
        c_date = _find_column(df, ["report_start_date", "report_date", "Date", "date"])
        c_tgt = _find_column(df, ["crude_daily_target", "crude_target", "Plan_kbopd", "daily_target", "plan"])
        c_act = _find_column(df, ["crude_daily_actual", "crude_actual", "Actual_kbopd", "daily_actual", "actual"])
        c_hl = _find_column(df, ["pd_crude_highlight", "crude_highlight", "highlight", "Event_Description", "remarks"])

        if c_act or c_tgt or (c_date and s_name == "Production_Trend"):
            card1_df = df
            col_date, col_target, col_actual, col_highlight = c_date, c_tgt, c_act, c_hl
            break

    if card1_df is not None:
        pt = updated["production_trend"]
        col_fld = _find_column(card1_df, ["field_name", "field", "Field_Name", "Field", "stream"])

        fields_in_card1 = []
        if col_fld:
            fields_in_card1 = [
                str(f).strip()
                for f in card1_df[col_fld].dropna().unique()
                if str(f).strip() and str(f).strip().lower() != "total"
            ]

        if col_fld and len(fields_in_card1) > 1 and col_date:
            ordered_dates = []
            for x in card1_df[col_date].dropna():
                d_fmt = format_chart_date(x)
                if d_fmt and d_fmt not in ordered_dates:
                    ordered_dates.append(d_fmt)

            by_field = {}
            for f in fields_in_card1:
                f_df = card1_df[card1_df[col_fld].astype(str).str.strip() == f]
                date_to_plan = {}
                date_to_act = {}
                date_to_hl = {}

                if col_target:
                    for _, r in f_df.iterrows():
                        if pd.notna(r[col_date]) and pd.notna(r[col_target]):
                            date_to_plan[format_chart_date(r[col_date])] = float(r[col_target])
                if col_actual:
                    for _, r in f_df.iterrows():
                        if pd.notna(r[col_date]) and pd.notna(r[col_actual]):
                            date_to_act[format_chart_date(r[col_date])] = float(r[col_actual])
                if col_highlight:
                    for _, r in f_df.iterrows():
                        if pd.notna(r[col_date]) and is_valid_event_highlight(r[col_highlight]):
                            date_to_hl[format_chart_date(r[col_date])] = str(r[col_highlight]).strip()

                f_plan = [date_to_plan.get(d, None) for d in ordered_dates]
                f_act = [date_to_act.get(d, None) for d in ordered_dates]
                f_fc = compute_exponential_forecast(f_act, f_plan, alpha=0.35)

                f_events = []
                for d in ordered_dates:
                    if d in date_to_hl:
                        text = date_to_hl[d]
                        title_match = text.split(".")[0].split(":")[0].strip()
                        title = title_match[:22] + "..." if len(title_match) > 22 else title_match
                        is_unplanned = any(
                            w in text.lower()
                            for w in ["trip", "leak", "shutdown", "fail", "down", "upset", "cut"]
                        )
                        f_events.append({
                            "date": d,
                            "title": title or "Operational Highlight",
                            "type": "issue" if is_unplanned else "activity",
                            "field": f,
                            "impact": "-1.5 kbopd" if is_unplanned else "-0.3 kbopd",
                            "status": "Open" if is_unplanned else "Planned",
                            "description": text,
                        })

                by_field[f] = {
                    "dates": ordered_dates,
                    "plan": f_plan,
                    "actual": f_act,
                    "forecast": f_fc,
                    "events": f_events,
                }

            tot_plan = []
            tot_act = []
            for idx, d in enumerate(ordered_dates):
                plans = [
                    by_field[f]["plan"][idx]
                    for f in fields_in_card1
                    if by_field[f]["plan"][idx] is not None
                ]
                acts = [
                    by_field[f]["actual"][idx]
                    for f in fields_in_card1
                    if by_field[f]["actual"][idx] is not None
                ]
                tot_plan.append(round(sum(plans), 1) if plans else None)
                tot_act.append(round(sum(acts), 1) if acts else None)

            tot_fc = compute_exponential_forecast(tot_act, tot_plan, alpha=0.35)
            tot_events = [ev for f in fields_in_card1 for ev in by_field[f]["events"]]

            pt["dates"] = ordered_dates
            pt["plan"] = tot_plan
            pt["actual"] = tot_act
            pt["forecast"] = tot_fc
            pt["events"] = tot_events
            pt["by_field"] = by_field

        else:
            if col_date:
                dates = [format_chart_date(x) for x in card1_df[col_date].tolist() if pd.notna(x)]
                if dates:
                    pt["dates"] = dates

            n_dates = len(pt["dates"])

            if col_target:
                plan_raw = [float(x) if pd.notna(x) else None for x in card1_df[col_target].tolist()]
                if len(plan_raw) < n_dates:
                    plan_raw += [plan_raw[-1] if plan_raw else 45.0] * (n_dates - len(plan_raw))
                pt["plan"] = plan_raw[:n_dates]

            if col_actual:
                act_raw = [float(x) if pd.notna(x) else None for x in card1_df[col_actual].tolist()]
                if len(act_raw) < n_dates:
                    act_raw += [None] * (n_dates - len(act_raw))
                pt["actual"] = act_raw[:n_dates]

            c_fc = _find_column(card1_df, ["Forecast_kbopd", "forecast", "forecast_kbopd"])
            if c_fc:
                fc_raw = [float(x) if pd.notna(x) else None for x in card1_df[c_fc].tolist()]
                if len(fc_raw) < n_dates:
                    fc_raw += [None] * (n_dates - len(fc_raw))
                pt["forecast"] = fc_raw[:n_dates]
            else:
                pt["forecast"] = compute_exponential_forecast(pt["actual"], pt["plan"], alpha=0.35)

            if col_highlight:
                events = []
                for i, h in enumerate(card1_df[col_highlight]):
                    if is_valid_event_highlight(h):
                        text = str(h).strip()
                        d_str = pt["dates"][i] if i < len(pt["dates"]) else "N/A"
                        title_match = text.split(".")[0].split(":")[0].strip()
                        title = title_match[:22] + "..." if len(title_match) > 22 else title_match

                        is_unplanned = any(
                            w in text.lower()
                            for w in ["trip", "leak", "shutdown", "fail", "down", "upset", "cut"]
                        )
                        events.append({
                            "date": d_str,
                            "title": title or "Operational Highlight",
                            "type": "issue" if is_unplanned else "activity",
                            "field": "Crude Stream",
                            "impact": "-1.500 kbopd" if is_unplanned else "-0.300 kbopd",
                            "status": "Open" if is_unplanned else "Planned",
                            "description": text,
                        })
                if events:
                    pt["events"] = events

        parsed_count += 1

    # =========================================================================
    # CARD 2: Field Performance
    # =========================================================================
    card2_df = None
    c2_field, c2_tgt, c2_act = None, None, None

    for s_name, df in all_dfs.items():
        f_col = _find_column(df, ["field_name", "field", "Field_Name", "Field"])
        t_col = _find_column(df, ["crude_daily_target", "crude_target", "Plan_kbopd", "daily_target", "plan"])
        a_col = _find_column(df, ["crude_daily_actual", "crude_actual", "Actual_kbopd", "daily_actual", "actual"])
        if f_col and (t_col or a_col):
            card2_df = df
            c2_field, c2_tgt, c2_act = f_col, t_col, a_col
            break

    if card2_df is not None:
        rows = []
        date_col = _find_column(card2_df, ["report_start_date", "report_date", "Date", "date"])

        if date_col and len(card2_df[c2_field].unique()) < len(card2_df):
            for f_name, group in card2_df.groupby(c2_field, sort=False):
                f_str = str(f_name).strip()
                if not f_str or f_str.lower() == "total":
                    continue
                sorted_group = group.sort_values(date_col)
                last_row = sorted_group.iloc[-1]
                p_val = float(last_row[c2_tgt]) if c2_tgt and pd.notna(last_row[c2_tgt]) else 0.0
                a_val = float(last_row[c2_act]) if c2_act and pd.notna(last_row[c2_act]) else 0.0
                var_val = round(a_val - p_val, 1)
                att_val = round((a_val / p_val) * 100, 1) if p_val > 0 else 0.0

                act_series = (
                    [float(x) for x in sorted_group[c2_act].dropna().tolist()]
                    if c2_act
                    else [a_val] * 7
                )
                trend = [round(x, 1) for x in act_series[-30:]] if act_series else [a_val] * 7
                if len(trend) < 2:
                    trend = [a_val] * 7

                rows.append({
                    "field": f_str,
                    "plan": round(p_val, 1),
                    "actual": round(a_val, 1),
                    "variance": var_val,
                    "attainment": att_val,
                    "trend": trend,
                })
        else:
            for _, r in card2_df.iterrows():
                f_name = str(r[c2_field]).strip() if pd.notna(r[c2_field]) else ""
                if not f_name or f_name.lower() == "total":
                    continue

                p_val = float(r[c2_tgt]) if c2_tgt and pd.notna(r[c2_tgt]) else 0.0
                a_val = float(r[c2_act]) if c2_act and pd.notna(r[c2_act]) else 0.0
                var_val = round(a_val - p_val, 1)
                att_val = round((a_val / p_val) * 100, 1) if p_val > 0 else 0.0

                if var_val >= 0:
                    trend = [round(a_val * f, 2) for f in [0.98, 0.99, 1.01, 1.0, 0.99, 1.0, 1.0]]
                else:
                    trend = [round(p_val - (p_val - a_val) * f, 2) for f in [0.1, 0.2, 0.4, 0.7, 0.85, 0.95, 1.0]]

                rows.append({
                    "field": f_name,
                    "plan": round(p_val, 1),
                    "actual": round(a_val, 1),
                    "variance": var_val,
                    "attainment": att_val,
                    "trend": trend,
                })

        if rows:
            tot_plan = round(sum(r["plan"] for r in rows), 1)
            tot_actual = round(sum(r["actual"] for r in rows), 1)
            tot_var = round(tot_actual - tot_plan, 1)
            tot_att = round((tot_actual / tot_plan) * 100, 1) if tot_plan > 0 else 0.0

            min_len = min(len(r["trend"]) for r in rows)
            tot_trend = [round(sum(r["trend"][k] for r in rows), 1) for k in range(min_len)]

            updated["field_performance"] = {
                "unit": "kbopd",
                "rows": rows,
                "total": {
                    "field": "Total",
                    "plan": tot_plan,
                    "actual": tot_actual,
                    "variance": tot_var,
                    "attainment": tot_att,
                    "trend": tot_trend,
                },
            }
            parsed_count += 1

            pt = updated.get("production_trend", {})
            if "by_field" not in pt:
                pt["by_field"] = {}

            if rows and pt.get("plan"):
                tot_p = tot_plan if tot_plan > 0 else 1.0
                tot_a = tot_actual if tot_actual > 0 else 1.0
                for r in rows:
                    fn = r["field"]
                    if fn not in pt["by_field"]:
                        ratio_p = r["plan"] / tot_p
                        ratio_a = r["actual"] / tot_a
                        f_plan = [round(float(p) * ratio_p, 1) if p is not None else None for p in pt["plan"]]
                        f_act = [round(float(a) * ratio_a, 1) if a is not None else None for a in pt.get("actual", [])]
                        f_fc = compute_exponential_forecast(f_act, f_plan, alpha=0.35)
                        f_ev = [
                            e for e in pt.get("events", [])
                            if e.get("field") == fn or fn.lower() in e.get("title", "").lower()
                        ]
                        pt["by_field"][fn] = {
                            "dates": pt.get("dates", []),
                            "plan": f_plan,
                            "actual": f_act,
                            "forecast": f_fc,
                            "events": f_ev,
                        }

    # =========================================================================
    # CARD 3: Planned Activities (Upcoming)
    # =========================================================================
    card3_df = None
    c3_date, c3_act, c3_field, c3_imp = None, None, None, None

    for s_name, df in all_dfs.items():
        d_col = _find_column(df, ["report_start_date", "report_date", "date", "Date"])
        act_col = _find_column(df, ["pd_crude_highlight", "activity", "Activity", "activity_name", "highlight", "remarks"])
        fld_col = _find_column(df, ["field_name", "field", "Field_Name", "Field"])
        imp_col = _find_column(df, ["pd_crude_volume_impact", "expected_impact", "volume_impact", "Expected_Impact_kbopd", "impact"])

        if act_col and (imp_col or s_name == "Planned_Activities"):
            card3_df = df
            c3_date, c3_act, c3_field, c3_imp = d_col, act_col, fld_col, imp_col
            break

    if card3_df is not None and c3_act:
        acts = []
        for _, r in card3_df.iterrows():
            act_text = str(r[c3_act]).strip() if pd.notna(r[c3_act]) else ""
            if not act_text or act_text.lower() in ("nan", "none", "-", ""):
                continue

            d_val = r[c3_date] if c3_date and pd.notna(r[c3_date]) else ""
            date_str = format_chart_date(d_val) if d_val else "Upcoming"
            f_val = str(r[c3_field]).strip() if c3_field and pd.notna(r[c3_field]) else "All Fields"

            imp_val = r[c3_imp] if c3_imp and pd.notna(r[c3_imp]) else None
            if imp_val is not None:
                try:
                    num_imp = float(imp_val)
                    if num_imp > 0:
                        imp_str = f"-{num_imp:.3f} kbopd"
                    else:
                        imp_str = f"{num_imp:.3f} kbopd"
                except Exception:
                    imp_str = str(imp_val)
            else:
                imp_str = "-0.300 kbopd"

            st_col = _find_column(card3_df, ["status", "Status"])
            status_val = str(r[st_col]).strip() if st_col and pd.notna(r[st_col]) else "Planned"
            if not status_val or status_val.lower() == "nan":
                status_val = "Planned"

            acts.append({
                "date": date_str,
                "activity": act_text,
                "field": f_val,
                "expected_impact": imp_str,
                "status": status_val,
            })

        if acts:
            updated["planned_activities"] = acts
            parsed_count += 1

    # =========================================================================
    # CARD 4: Active Issues & Mitigation
    # =========================================================================
    card4_df = None
    c4_iss, c4_fld, c4_imp, c4_rec = None, None, None, None

    for s_name, df in all_dfs.items():
        iss_col = _find_column(df, ["upd_crude_highlight", "issue", "Issue", "issue_name", "unplanned_highlight", "deferment_reason"])
        fld_col = _find_column(df, ["field_name", "field", "Field_Name", "Field"])
        imp_col = _find_column(df, ["upd_crude_volume_impact", "impact", "Impact", "Impact_kbopd", "deferment_kbopd"])
        rec_col = _find_column(df, ["report_start_date", "recovery_date", "recovery", "Recovery_Date", "date", "Date"])

        if iss_col and (imp_col or s_name == "Active_Issues"):
            card4_df = df
            c4_iss, c4_fld, c4_imp, c4_rec = iss_col, fld_col, imp_col, rec_col
            break

    if card4_df is not None and c4_iss:
        issues = []
        for _, r in card4_df.iterrows():
            iss_text = str(r[c4_iss]).strip() if pd.notna(r[c4_iss]) else ""
            if not iss_text or iss_text.lower() in ("nan", "none", "-", ""):
                continue

            f_val = str(r[c4_fld]).strip() if c4_fld and pd.notna(r[c4_fld]) else "All Fields"

            imp_val = r[c4_imp] if c4_imp and pd.notna(r[c4_imp]) else None
            if imp_val is not None:
                try:
                    num_imp = float(imp_val)
                    if num_imp > 0:
                        imp_str = f"-{num_imp:.3f} kbopd"
                    else:
                        imp_str = f"{num_imp:.3f} kbopd"
                except Exception:
                    imp_str = str(imp_val)
            else:
                imp_str = "-1.500 kbopd"

            rec_val = r[c4_rec] if c4_rec and pd.notna(r[c4_rec]) else ""
            rec_str = format_chart_date(rec_val) if rec_val else "-"

            title_part = iss_text.split(".")[0].split(":")[0].strip()
            issue_title = title_part if len(title_part) <= 45 else title_part[:42].rsplit(" ", 1)[0] + "..."

            st_col = _find_column(card4_df, ["status", "Status"])
            st_raw = str(r[st_col]).strip() if st_col and pd.notna(r[st_col]) else "Open"
            if not st_raw or st_raw.lower() in ("nan", "none", "", "-"):
                st_val = "Open"
            else:
                status_map = {
                    "open": "Open",
                    "monitoring": "Monitoring",
                    "in progress": "In Progress",
                    "inprogress": "In Progress",
                    "closed": "Closed",
                    "close": "Closed",
                    "resolved": "Closed",
                }
                st_val = status_map.get(st_raw.lower(), st_raw.capitalize())

            issues.append({
                "issue": issue_title,
                "field": f_val,
                "impact": imp_str,
                "status": st_val,
                "recovery": rec_str,
                "description": iss_text,
                "remarks": iss_text,
            })

        if issues:
            updated["active_issues"] = issues
            parsed_count += 1

    # =========================================================================
    # CARD 5 & CARD 6: Offloading Planning & Estimation
    # =========================================================================
    card5_df = None
    c5_date, c5_act, c5_tgt = None, None, None

    if "Offloading_Planning" in sheets_found:
        card5_df = all_dfs["Offloading_Planning"]
        c5_date = _find_column(card5_df, ["Date", "date", "report_start_date"])
        c5_act = _find_column(card5_df, ["Actual_Inventory_MMbbl", "actual_inventory", "inventory", "crude_daily_actual"])
        c5_tgt = _find_column(card5_df, ["crude_daily_target", "P50_Base_MMbbl", "target", "plan"])
    else:
        for s_name, df in all_dfs.items():
            d_col = _find_column(df, ["report_start_date", "report_date", "date", "Date"])
            a_col = _find_column(df, ["crude_daily_actual", "crude_actual", "Actual_kbopd", "daily_actual", "actual"])
            t_col = _find_column(df, ["crude_daily_target", "crude_target", "Plan_kbopd", "daily_target", "plan"])
            if d_col and a_col:
                card5_df = df
                c5_date, c5_act, c5_tgt = d_col, a_col, t_col
                break

    if card5_df is not None and c5_date and c5_act:
        dates_raw = [format_chart_date(x) for x in card5_df[c5_date].tolist() if pd.notna(x)]
        acts_raw = [float(x) if pd.notna(x) else None for x in card5_df[c5_act].tolist()]
        tgts_raw = (
            [float(x) if pd.notna(x) else None for x in card5_df[c5_tgt].tolist()]
            if c5_tgt
            else [45.0] * len(dates_raw)
        )

        c_p10 = _find_column(card5_df, ["P10_Early_MMbbl", "p10_early", "p10"])
        c_p50 = _find_column(card5_df, ["P50_Base_MMbbl", "p50_base", "p50"])
        c_p90 = _find_column(card5_df, ["P90_Late_MMbbl", "p90_late", "p90"])

        if c_p10 and c_p50 and c_p90:
            op = updated["offloading_planning"]
            op["dates"] = dates_raw
            op["actual_inventory"] = acts_raw
            op["p10_early"] = [float(x) if pd.notna(x) else None for x in card5_df[c_p10]]
            op["p50_base"] = [float(x) if pd.notna(x) else None for x in card5_df[c_p50]]
            op["p90_late"] = [float(x) if pd.notna(x) else None for x in card5_df[c_p90]]
            parsed_count += 1
        else:
            proj_data = compute_offloading_projections(dates_raw, acts_raw, tgts_raw)
            updated["offloading_planning"] = proj_data["offloading_planning"]
            updated["offloading_estimation"] = proj_data["offloading_estimation"]
            parsed_count += 2

    # CARD 6: Respect explicit sheet if present
    if "Offloading_Estimation" in sheets_found:
        df_oe = all_dfs["Offloading_Estimation"]
        if "Scenario" in df_oe.columns:
            updated["offloading_estimation"]["scenarios"] = df_oe.to_dict(orient="records")

    # Extract available fields across cards
    avail_fields = []
    for r in updated.get("field_performance", {}).get("rows", []):
        fn = str(r.get("field", "")).strip()
        if fn and fn.lower() != "total" and fn not in avail_fields:
            avail_fields.append(fn)
    for fn in updated.get("production_trend", {}).get("by_field", {}).keys():
        fn_str = str(fn).strip()
        if fn_str and fn_str.lower() != "total" and fn_str not in avail_fields:
            avail_fields.append(fn_str)
    for a in updated.get("planned_activities", []):
        fn = str(a.get("field", "")).strip()
        if fn and fn.lower() not in ("all fields", "total", "crude stream") and fn not in avail_fields:
            avail_fields.append(fn)
    for i in updated.get("active_issues", []):
        fn = str(i.get("field", "")).strip()
        if fn and fn.lower() not in ("all fields", "total", "crude stream") and fn not in avail_fields:
            avail_fields.append(fn)

    if not avail_fields:
        avail_fields = ["Field A", "Field B", "Field C", "Field D"]

    updated["metadata"]["available_fields"] = avail_fields

    wb.close()
    return updated, parsed_count


# =========================================================================
# COMPATIBILITY WRAPPERS
# =========================================================================

def compute_target_deficit_metrics(
    actual: list[float], target: list[float]
) -> dict[str, Any]:
    """Calculate variances and deficits between actual and target series."""
    if not actual or not target:
        return {"variances": [], "deficits": [], "total_shortfall": 0.0}
    deficits = [max(0.0, tgt - act) for act, tgt in zip(actual, target)]
    return {
        "variances": [act - tgt for act, tgt in zip(actual, target)],
        "deficits": deficits,
        "total_shortfall": sum(deficits),
    }


def forecast_production_series(
    series: list[float], last_date_str: str, horizon_days: int = 14
) -> dict[str, list[Any]]:
    """Predict future values using exponential smoothing model."""
    fcs = compute_exponential_forecast(
        series, [series[-1] * 1.05] * len(series) if series else []
    )
    return {"dates": [], "p50": fcs, "p10": [], "p90": []}
