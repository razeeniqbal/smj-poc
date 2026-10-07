"""
Maps the daily terminal summary (see terminal.py) onto the 6-card dashboard schema,
so the main dashboard can show terminals with the same charts and metrics as fields.

Card mapping:
1. Production Trend      - daily crude target vs actual per terminal, highlights as event pins
2. Field Performance     - one row per terminal (period averages)
3. Planned Activities    - "Tanker loading ... planned on ..." highlights
4. Active Issues         - unplanned crude highlights and LOPC days
5. Offloading Planning   - estimated inventory = production - liftings, target = nominated cargo
6. Offloading Estimation - P10/P50/P90 dates from the spread of observed daily rates
"""

from datetime import date, timedelta
import os
from pathlib import Path
import re
from statistics import mean, median
from typing import Any

from dashboard.analytics import compute_exponential_forecast
from dashboard.terminal import get_terminal_csv_path, load_terminal_data

ALL = "All Fields"  # the dashboard's "no filter" sentinel, shown as "All Terminals"
FORECAST_DAYS = 7
MIN_PROJECTION_DAYS = 14
MAX_PROJECTION_DAYS = 60

PLANNED_RE = re.compile(
    r'tanker loading\s+"(?P<tanker>[^"]+)"\s*~?(?P<size>[\d,]+)\s*bbls?\s*(?:\((?P<party>[^)]+)\))?'
    r".*?planned on\s+(?P<when>[\d/\-]+)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def _d(iso: str) -> date:
    return date.fromisoformat(iso)


def _label(d: date) -> str:
    """Chart label used across the dashboard, e.g. '1 Aug'."""
    return f"{d.day} {d.strftime('%b')}"


def _days(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def _quantile(values: list[float], q: float) -> float:
    s = sorted(values)
    pos = (len(s) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def _same_tanker(a: str | None, b: str | None) -> bool:
    """'MT OCEANA' and 'MT OCEANA RIVER' refer to the same vessel in these reports."""
    if not a or not b:
        return False
    a, b = a.upper().strip(), b.upper().strip()
    return a == b or a.startswith(b + " ") or b.startswith(a + " ")


def _valid_party(party: str | None) -> str | None:
    """Lifting party, ignoring cells that actually hold a tanker name (shifted source columns)."""
    party = (party or "").strip()
    return party if party and not party.upper().startswith("MT ") else None


def _parse_planned_window(when: str) -> tuple[date, date] | None:
    """Parse '20-21/8/2026' or '12-13/08/2026' or '30/7/2026' into (start, end)."""
    m = re.match(r"(\d{1,2})(?:-(\d{1,2}))?/(\d{1,2})/(\d{4})", when)
    if not m:
        return None
    d1, d2, mon, yr = m.groups()
    try:
        start = date(int(yr), int(mon), int(d1))
        end = date(int(yr), int(mon), int(d2 or d1))
    except ValueError:
        return None
    if end < start:  # window crosses a month end, e.g. 30-1/9
        end = date(start.year + (start.month == 12), start.month % 12 + 1, int(d2))
    return start, end


def _window_label(start: date, end: date) -> str:
    if start == end:
        return f"{_label(start)} {start.year}"
    if start.month == end.month:
        return f"{start.day}-{end.day} {start.strftime('%b')} {start.year}"
    return f"{_label(start)} - {_label(end)} {end.year}"


# ---------------------------------------------------------------------------
# per-terminal building blocks
# ---------------------------------------------------------------------------

def _planned_loadings(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Distinct planned tanker loadings mentioned in the key highlights, in report order."""
    plans: list[dict[str, Any]] = []
    for row in rows:
        m = PLANNED_RE.search(row.get("highlight") or "")
        if not m:
            continue
        window = _parse_planned_window(m.group("when"))
        if not window:
            continue
        tanker = m.group("tanker").strip()
        existing = next((p for p in plans if _same_tanker(p["tanker"], tanker)), None)
        if existing:
            # later reports may give a fuller name or a lifting party
            if len(tanker) > len(existing["tanker"]):
                existing["tanker"] = tanker
            existing["party"] = _valid_party(m.group("party")) or existing["party"]
            existing["start"], existing["end"] = window
            continue
        plans.append({
            "tanker": tanker,
            "size_kbbl": round(float(m.group("size").replace(",", "")) / 1000, 1),
            "party": _valid_party(m.group("party")) or _valid_party(row.get("lifting_party")),
            "start": window[0],
            "end": window[1],
            "first_mentioned": row["date"],
        })
    return plans


def _liftings_with_assumed(
    rows: list[dict[str, Any]], recorded: list[dict[str, Any]], last_day: date
) -> list[dict[str, Any]]:
    """
    Recorded liftings plus planned loadings whose window has passed with no recorded lift
    (e.g. no reports on the loading days). Those are assumed lifted at the nominated size.
    """
    events = [
        {"date": _d(e["date"]), "tanker": e["tanker"],
         "party": _valid_party(e["lifting_party"]), "volume": e["volume"], "assumed": False}
        for e in recorded
    ]
    for plan in _planned_loadings(rows):
        lifted = any(_same_tanker(plan["tanker"], e["tanker"]) for e in events)
        if not lifted and plan["end"] < last_day:
            events.append({
                "date": plan["end"], "tanker": plan["tanker"], "party": plan["party"],
                "volume": plan["size_kbbl"], "assumed": True,
            })
    return sorted(events, key=lambda e: e["date"])


def _inventory_model(
    days: list[date],
    actual_by_day: dict[date, float],
    liftings: list[dict[str, Any]],
    cargo_kbbl: float,
) -> dict[str, Any]:
    """
    Estimated terminal inventory (kbbl) and next-offload P10/P50/P90 projection.

    Opening stock is not reported, so it is set to the lowest value that keeps the
    balance non-negative (the minimum feasible inventory). Days without a report are
    filled with the mean reported rate.
    """
    reported = list(actual_by_day.values())
    fill_rate = mean(reported)
    lift_by_day: dict[date, float] = {}
    for e in liftings:
        lift_by_day[e["date"]] = lift_by_day.get(e["date"], 0.0) + e["volume"]

    balance, running = [], 0.0
    for d in days:
        running += actual_by_day.get(d, fill_rate) - lift_by_day.get(d, 0.0)
        balance.append(running)
    opening = max(0.0, -min(balance))
    inventory = [round(b + opening, 1) for b in balance]

    current = inventory[-1]
    rates = {
        "p10": _quantile(reported, 0.9),  # high rate -> fills early
        "p50": median(reported),
        "p90": _quantile(reported, 0.1),  # low rate -> fills late
    }

    future: list[date] = []
    paths: dict[str, list[float]] = {k: [] for k in rates}
    cross: dict[str, int | None] = {k: None for k in rates}
    lvl = {k: current for k in rates}
    i = 0
    while i < MAX_PROJECTION_DAYS and (i < MIN_PROJECTION_DAYS or cross["p90"] is None or i < cross["p90"] + 3):
        future.append(days[-1] + timedelta(days=i + 1))
        for k, rate in rates.items():
            lvl[k] += rate
            paths[k].append(round(lvl[k], 1))
            if cross[k] is None and lvl[k] >= cargo_kbbl:
                cross[k] = i
        i += 1

    return {
        "inventory": inventory,
        "current": current,
        "future": future,
        "paths": paths,
        "cross": cross,
        "rates": rates,
        "opening": round(opening, 1),
    }


def _offloading_cards(model: dict[str, Any], days: list[date], cargo_kbbl: float, name: str) -> dict[str, Any]:
    n_hist = len(days)
    all_days = days + model["future"]
    labels = [_label(d) for d in all_days]
    pad = [None] * (n_hist - 1)

    def series(key: str) -> list[float | None]:
        return pad + [model["current"]] + model["paths"][key]

    milestones, scenarios = {}, []
    titles = {"p10": "P10 (Early)", "p50": "P50 (Base)", "p90": "P90 (Late)"}
    for key, title in titles.items():
        idx = model["cross"][key]
        if idx is None:
            when, label, days_from = None, f"After {_label(model['future'][-1])}", f">{len(model['future'])} days"
        else:
            when = model["future"][idx]
            label, days_from = _label(when), f"{idx + 1} days"
        milestones[key] = {"date": label, "level": cargo_kbbl, "tag": f"{key.upper()} {label}"}
        scenarios.append({
            "scenario": title,
            "estimated_offload_date": f"{label} {when.year}" if when else label,
            "days_from_now": days_from,
            "tag_class": f"{key}-tag",
        })

    current = round(model["current"], 1)
    return {
        "offloading_planning": {
            "unit": "kbbl",
            "max_capacity": None,
            "target_offload": cargo_kbbl,
            "current_inventory": current,
            "current_date": _label(days[-1]),
            "dates": labels,
            "actual_inventory": model["inventory"] + [None] * len(model["future"]),
            "p10_early": series("p10"),
            "p50_base": series("p50"),
            "p90_late": series("p90"),
            "milestones": milestones,
            "estimate_note": (
                "Estimated: production minus liftings, opening stock set to the minimum "
                f"feasible level ({model['opening']} kbbl)."
            ),
        },
        "offloading_estimation": {
            "unit": "kbbl",
            "field": name,
            "current_inventory": current,
            "target_offload_level": cargo_kbbl,
            "maximum_capacity": None,
            "scenarios": scenarios,
        },
    }


def _events_from_highlights(rows: list[dict[str, Any]], name: str, lift_days: set[str]) -> list[dict[str, Any]]:
    """One pin per change of highlight text (reports repeat the same text for days)."""
    events, last_text, pinned_plans = [], None, []
    for row in rows:
        text = row.get("highlight")
        if not text or text == last_text:
            last_text = text or last_text
            continue
        last_text = text
        lifted = row["date"] in lift_days or "commenced loading" in text.lower()
        tanker = row.get("tanker") if row.get("tanker") not in (None, "TBA") else None
        m = PLANNED_RE.search(text)
        if m:
            planned = m.group("tanker").strip()
            if any(_same_tanker(planned, t) for t in pinned_plans):
                continue
            pinned_plans.append(planned)
            title = f"Tanker planned: {planned}"
        elif lifted:
            title = f"Lifting: {tanker}" if tanker else "Tanker lifting"
        else:
            title = text.split(".")[0][:40]
        events.append({
            "date": _label(_d(row["date"])),
            "title": title,
            "type": "activity",
            "field": name,
            "impact": "-",
            "status": "Completed" if lifted else "Planned",
            "description": text,
        })
    return events


def _terminal_block(name: str, rows: list[dict[str, Any]], recorded_lifts: list[dict[str, Any]]) -> dict[str, Any]:
    """Everything the 6 cards need for one terminal (or the all-terminals aggregate)."""
    first, last = _d(rows[0]["date"]), _d(rows[-1]["date"])
    days = _days(first, last)
    by_day = {_d(r["date"]): r for r in rows}

    actual = [by_day[d]["crude_actual"] if d in by_day else None for d in days]
    plan = [by_day[d]["crude_target"] if d in by_day else None for d in days]

    # Card 1 runs a week past the last report so the forecast is visible
    last_target = next((p for p in reversed(plan) if p is not None), None)
    fc_days = [last + timedelta(days=i) for i in range(1, FORECAST_DAYS + 1)]
    plan_ext = plan + [last_target] * FORECAST_DAYS
    actual_ext = actual + [None] * FORECAST_DAYS
    forecast = compute_exponential_forecast(actual_ext, plan_ext, alpha=0.35)

    liftings = _liftings_with_assumed(rows, recorded_lifts, last)
    lift_days = {e["date"].isoformat() for e in liftings if not e["assumed"]}

    cargo_sizes = [r["cargo_size"] for r in rows if r.get("cargo_size")]
    cargo_kbbl = cargo_sizes[-1] if cargo_sizes else 300.0
    actual_by_day = {d: by_day[d]["crude_actual"] for d in days if d in by_day and by_day[d]["crude_actual"] is not None}
    model = _inventory_model(days, actual_by_day, liftings, cargo_kbbl)

    paired = [(a, p) for a, p in zip(actual, plan) if a is not None and p is not None]
    avg_a = mean(a for a, _ in paired) if paired else 0.0
    avg_p = mean(p for _, p in paired) if paired else 0.0

    return {
        "days": days,
        "trend": {
            "dates": [_label(d) for d in days + fc_days],
            "plan": plan_ext,
            "actual": actual_ext,
            "forecast": forecast,
            "events": _events_from_highlights(rows, name, lift_days),
        },
        "performance": {
            "field": name,
            "plan": round(avg_p, 1),
            "actual": round(avg_a, 1),
            "variance": round(avg_a - avg_p, 1),
            "attainment": round(avg_a / avg_p * 100, 1) if avg_p else 0.0,
            "trend": [round(a, 1) for a in actual if a is not None][-30:],
        },
        "liftings": liftings,
        "model": model,
        "cargo_kbbl": cargo_kbbl,
        "offloading": _offloading_cards(model, days, cargo_kbbl, name),
    }


def _activities(name: str, rows: list[dict[str, Any]], liftings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    acts = []
    for plan in _planned_loadings(rows):
        lift = next((e for e in liftings if _same_tanker(plan["tanker"], e["tanker"])), None)
        party = f", {plan['party']}" if plan["party"] else ""
        activity = f"Tanker loading {plan['tanker']} (~{plan['size_kbbl']:g} kbbl{party})"
        if lift and lift["assumed"]:
            status = "Unconfirmed"
            activity += " - no reports on loading days, assumed lifted"
        elif lift:
            status = "Completed"
        else:
            status = "Planned"
        acts.append({
            "date": _window_label(plan["start"], plan["end"]),
            "activity": activity,
            "field": name,
            "expected_impact": "-",
            "status": status,
        })
    return acts


def _issues(name: str, rows: list[dict[str, Any]], raw_issue_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues = []
    for r in raw_issue_rows:
        text = r["upd_crude_highlight"]
        impact = r.get("upd_crude_volume_impact")
        issues.append({
            "issue": text.split(".")[0][:45],
            "field": name,
            "impact": f"-{abs(impact):.3f} kbopd" if impact else "-",
            "status": "Open",
            "recovery": "-",
            "date": _label(_d(r["date"])),
            "description": text,
            "remarks": text,
        })
    for r in rows:
        if r.get("lopc"):
            issues.append({
                "issue": f"LOPC reported ({r['lopc']:g})",
                "field": name,
                "impact": "-",
                "status": "Open",
                "recovery": "-",
                "date": _label(_d(r["date"])),
                "description": f"Loss of primary containment reported on {_label(_d(r['date']))}.",
                "remarks": f"Loss of primary containment reported on {_label(_d(r['date']))}.",
            })
    return issues


def _aggregate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sum production across terminals per day (for 'All Terminals' when there are several)."""
    by_day: dict[str, dict[str, Any]] = {}
    for r in rows:
        agg = by_day.setdefault(r["date"], {**r, "crude_actual": None, "crude_target": None, "lopc": 0.0})
        for key in ("crude_actual", "crude_target"):
            if r[key] is not None:
                agg[key] = (agg[key] or 0.0) + r[key]
        agg["lopc"] += r.get("lopc") or 0.0
    return [by_day[d] for d in sorted(by_day)]


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def build_terminal_dashboard(tdata: dict[str, Any], issue_rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Build the full 6-card dataset for the terminal view from load_terminal_data() output."""
    rows = tdata["rows"]
    names = sorted({r["operator"] for r in rows})
    issue_rows = issue_rows or []

    blocks = {
        n: _terminal_block(
            n,
            [r for r in rows if r["operator"] == n],
            [e for e in tdata["liftings"] if e["operator"] == n],
        )
        for n in names
    }
    total = blocks[names[0]] if len(names) == 1 else _terminal_block(ALL, _aggregate_rows(rows), tdata["liftings"])

    activities = [a for n in names for a in _activities(n, [r for r in rows if r["operator"] == n], blocks[n]["liftings"])]
    issues = [
        i for n in names
        for i in _issues(n, [r for r in rows if r["operator"] == n], [x for x in issue_rows if x["operator"] == n])
    ]

    perf_rows = [blocks[n]["performance"] for n in names]
    tot_p = round(sum(r["plan"] for r in perf_rows), 1)
    tot_a = round(sum(r["actual"] for r in perf_rows), 1)
    min_len = min(len(r["trend"]) for r in perf_rows)

    first, last = total["days"][0], total["days"][-1]
    period = first.strftime("%b %Y") if (first.year, first.month) == (last.year, last.month) else f"{_label(first)} - {_label(last)} {last.year}"

    p50 = total["offloading"]["offloading_estimation"]["scenarios"][1]["estimated_offload_date"]
    perf_total = total["performance"]
    assumed = [e for e in total["liftings"] if e["assumed"]]
    insight = (
        f"{' + '.join(names)} averaged {perf_total['actual']} kbbl/d against a {perf_total['plan']} kbbl/d target "
        f"({perf_total['attainment']}%) over {_label(first)}-{_label(last)}. "
        f"Estimated stock is {total['model']['current']:.0f} kbbl; the next ~{total['cargo_kbbl']:g} kbbl cargo "
        f"is ready around {p50} (P50)."
    )
    if assumed:
        insight += " Assumes " + ", ".join(e["tanker"] for e in assumed) + " lifted (no reports on loading days)."

    data = {
        "metadata": {
            "title": "Production Planning Dashboard",
            "subtitle": "Monitor. Analyse. Plan. Maximise Production.",
            "view": "terminal",
            "period": period,
            "selected_field": ALL,
            "available_fields": names,
            "facility": "Terminal",
            "last_updated": tdata["source"]["modified"],
            "operator": ", ".join(names),
            "source_file": tdata["source"]["file"],
        },
        "production_trend": {
            "unit": "kbopd",
            "frequency": "Daily",
            **total["trend"],
            "by_field": {n: blocks[n]["trend"] for n in names},
        },
        "field_performance": {
            "unit": "kbopd",
            "rows": perf_rows,
            "total": {
                "field": "Total",
                "plan": tot_p,
                "actual": tot_a,
                "variance": round(tot_a - tot_p, 1),
                "attainment": round(tot_a / tot_p * 100, 1) if tot_p else 0.0,
                "trend": [round(sum(r["trend"][k] for r in perf_rows), 1) for k in range(min_len)],
            },
        },
        "planned_activities": activities,
        "active_issues": issues,
        **total["offloading"],
        "offloading_by_field": {n: blocks[n]["offloading"] for n in names},
        "ai_insight": {"text": insight},
    }
    return data


_cache: dict[str, Any] = {"key": None, "data": None}


def get_terminal_dashboard() -> dict[str, Any]:
    """
    Terminal 6-card dataset, cached until the CSV changes on disk so that
    status edits made in the UI survive between requests.
    """
    path = get_terminal_csv_path()
    key = (str(path), os.path.getmtime(path))
    if _cache["key"] != key:
        tdata = load_terminal_data(path)
        _cache["data"] = build_terminal_dashboard(tdata, _load_issue_rows(path))
        _cache["key"] = key
    return _cache["data"]


def _load_issue_rows(path: Path) -> list[dict[str, Any]]:
    """Unplanned crude highlights, which load_terminal_data does not carry."""
    import pandas as pd

    from dashboard.terminal import NA_VALUES

    df = pd.read_csv(path, na_values=NA_VALUES)
    if "upd_crude_highlight" not in df.columns:
        return []
    df = df.dropna(subset=["upd_crude_highlight"])
    out, seen = [], set()
    for _, r in df.iterrows():
        when = pd.to_datetime(r.get("report_start_date"), errors="coerce")
        if pd.isna(when):
            continue
        impact = pd.to_numeric(r.get("upd_crude_volume_impact"), errors="coerce")
        key = (str(r.get("operator")), when.date(), str(r["upd_crude_highlight"]).strip())
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "date": when.strftime("%Y-%m-%d"),
            "operator": str(r.get("operator") or "Terminal").strip(),
            "upd_crude_highlight": str(r["upd_crude_highlight"]).strip(),
            "upd_crude_volume_impact": None if pd.isna(impact) else float(impact),
        })
    return out
