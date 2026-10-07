"""
Synthetic placeholder data and Excel mapping schema for the 6-Card Production Planning Dashboard.

CARDS SPECIFICATION (from screenshot):
1. Production Trend (Daily plan, actual, forecast, and interactive event pins tied to Active Issues)
2. Field Performance (Table with Plan, Actual, Variance, Attainment %, and 30-day sparklines)
3. Planned Activities (Upcoming) (Date, Activity, Field, Expected Impact, Status)
4. Active Issues & Mitigation (Issue, Field, Impact, Status, Recovery, Root Cause)
5. Offloading Planning (Inventory time series, 3.5 MMbbl capacity, 3.0 MMbbl target, P10/P50/P90 projections)
6. Offloading Estimation (Stat callouts & P10/P50/P90 scenario forecast dates)

Zero access to data/ or output/. In-memory synthetic models only.
"""

from typing import Any

# Declarative mapping defining how each of the 6 cards maps to an Excel Workbook sheet
EXCEL_SHEET_MAPPING: dict[str, dict[str, Any]] = {
    "card_1_production_trend": {
        "sheet_name": "Production_Trend / Single Sheet",
        "description": "Daily crude production trend, planned targets, ML forecast, and operational highlights.",
        "columns": [
            "report_start_date",
            "crude_daily_target",
            "crude_daily_actual",
            "forecast (auto-computed via Exponential Smoothing Model)",
            "pd_crude_highlight"
        ]
    },
    "card_2_field_performance": {
        "sheet_name": "Field_Performance / Single Sheet",
        "description": "Production performance per field stream.",
        "columns": [
            "field_name",
            "crude_daily_target",
            "crude_daily_actual",
            "variance (auto-computed: crude_daily_actual - crude_daily_target)",
            "attainment (auto-computed: actual / target * 100)",
            "trend (auto-computed: 7-30 day time-series or sparkline)"
        ]
    },
    "card_3_planned_activities": {
        "sheet_name": "Planned_Activities / Single Sheet",
        "description": "Upcoming scheduled operations, maintenance shutdowns, and tests.",
        "columns": [
            "report_start_date (Date)",
            "pd_crude_highlight (Activity)",
            "field_name (Field)",
            "pd_crude_volume_impact (Expected Impact)",
            "status (Interactive Front-End Dropdown: Planned / In Progress / Completed / Deferred)"
        ]
    },
    "card_4_active_issues": {
        "sheet_name": "Active_Issues / Single Sheet",
        "description": "Active operational issues, deferments, impacts, and recovery timeline.",
        "columns": [
            "upd_crude_highlight (Issue)",
            "field_name (Field)",
            "upd_crude_volume_impact (Impact)",
            "status (Interactive Front-End Dropdown: Open / Monitoring / In Progress / Closed)",
            "report_start_date (Recovery Date)"
        ]
    },
    "card_5_offloading_planning": {
        "sheet_name": "Offloading_Planning / Single Sheet",
        "description": "Terminal crude inventory curve and P10/P50/P90 forecast trajectories.",
        "columns": [
            "report_start_date (Date)",
            "crude_daily_actual (Cumulative Inventory)",
            "crude_daily_target (Cumulative Target Forecast)",
            "P10 / P50 / P90 (Auto-projected Offload Milestones with Vertical Guides & Confidence Band)"
        ]
    },
    "card_6_offloading_estimation": {
        "sheet_name": "Offloading_Estimation / Auto-Derived from Card 5",
        "description": "Executive milestone summary of Card 5: storage limits and P10/P50/P90 target offload dates.",
        "columns": [
            "Current Inventory (Derived from cumulative actuals in Card 5)",
            "Target Offload Level (3.0 MMbbl threshold)",
            "Maximum Capacity (3.5 MMbbl safety limit)",
            "Scenarios (P10 Early, P50 Base, P90 Late offload forecast dates & days remaining)"
        ]
    }
}


def get_default_dataset() -> dict[str, Any]:
    """Return default synthetic operational dataset matching the 6 dashboard cards."""
    return {
        "metadata": {
            "title": "Production Planning Dashboard",
            "subtitle": "Monitor. Analyse. Plan. Maximise Production.",
            "period": "Sep 2026",
            "selected_field": "All Fields",
            "available_fields": ["Field A", "Field B", "Field C", "Field D"],
            "facility": "Central Offshore Complex",
            "last_updated": "21 Sep 2026 10:30",
            "operator": "Operations"
        },
        
        # -------------------------------------------------------------
        # CARD 1: Production Trend
        # -------------------------------------------------------------
        "production_trend": {
            "unit": "kbopd",
            "frequency": "Daily",
            "dates": [
                "1 Sep", "2 Sep", "3 Sep", "4 Sep", "5 Sep", "6 Sep", "7 Sep", "8 Sep",
                "9 Sep", "10 Sep", "11 Sep", "12 Sep", "13 Sep", "14 Sep", "15 Sep",
                "16 Sep", "17 Sep", "18 Sep", "19 Sep", "20 Sep", "21 Sep",
                "22 Sep", "23 Sep", "24 Sep", "25 Sep", "26 Sep", "27 Sep", "28 Sep",
                "29 Sep", "30 Sep"
            ],
            # Total / All Fields aggregated daily targets
            "plan": [
                45.0, 45.0, 45.0, 45.0, 45.2, 45.2, 45.5, 45.5, 45.8, 45.8, 46.0,
                46.0, 46.0, 46.2, 46.2, 46.4, 46.4, 46.6, 46.6, 46.8, 46.8,
                47.0, 47.0, 47.2, 47.2, 47.5, 47.5, 47.8, 48.0, 48.2
            ],
            # Total / All Fields actuals up to 21 Sep
            "actual": [
                41.5, 42.0, 45.2, 43.8, 42.5, 40.5, 39.8, 41.2, 42.0, 40.8, 38.5,
                34.0, 32.5, 31.0, 30.2, 34.8, 36.5, 37.0, 39.2, 36.0, 34.5,
                None, None, None, None, None, None, None, None, None
            ],
            # Total / All Fields forecast
            "forecast": [
                None, None, None, None, None, None, None, None, None, None, None,
                None, None, None, None, None, None, None, None, None, 34.5,
                36.0, 37.8, 39.5, 41.2, 43.0, 44.5, 46.0, 47.2, 48.0
            ],
            # Clean per-field production datasets avoiding overlapping chart confusion
            "by_field": {
                "Field A": {
                    "dates": [
                        "1 Sep", "2 Sep", "3 Sep", "4 Sep", "5 Sep", "6 Sep", "7 Sep", "8 Sep",
                        "9 Sep", "10 Sep", "11 Sep", "12 Sep", "13 Sep", "14 Sep", "15 Sep",
                        "16 Sep", "17 Sep", "18 Sep", "19 Sep", "20 Sep", "21 Sep",
                        "22 Sep", "23 Sep", "24 Sep", "25 Sep", "26 Sep", "27 Sep", "28 Sep",
                        "29 Sep", "30 Sep"
                    ],
                    "plan": [
                        12.0, 12.0, 12.0, 12.0, 12.0, 12.0, 12.1, 12.1, 12.2, 12.2, 12.2,
                        12.2, 12.2, 12.3, 12.3, 12.3, 12.3, 12.4, 12.4, 12.4, 12.4,
                        12.5, 12.5, 12.5, 12.5, 12.6, 12.6, 12.6, 12.7, 12.7
                    ],
                    "actual": [
                        11.5, 11.6, 12.0, 11.9, 11.8, 11.7, 11.8, 11.9, 12.1, 11.9, 11.7,
                        11.6, 11.5, 11.6, 11.7, 11.8, 11.9, 11.8, 11.9, 11.8, 11.8,
                        None, None, None, None, None, None, None, None, None
                    ],
                    "forecast": [
                        None, None, None, None, None, None, None, None, None, None, None,
                        None, None, None, None, None, None, None, None, None, 11.8,
                        11.9, 12.0, 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7
                    ],
                    "events": [
                        {
                            "date": "3 Sep",
                            "title": "SGS",
                            "type": "activity",
                            "field": "Field A",
                            "impact": "-0.3 kbopd",
                            "status": "Completed",
                            "description": "Subsea Gas Surge flowline pressure validation completed."
                        },
                        {
                            "date": "30 Sep",
                            "title": "Well Intervention",
                            "type": "activity",
                            "field": "Field A",
                            "impact": "-0.4 kbopd",
                            "status": "Planned",
                            "description": "Scheduled wireline intervention on Well A-12."
                        }
                    ]
                },
                "Field B": {
                    "dates": [
                        "1 Sep", "2 Sep", "3 Sep", "4 Sep", "5 Sep", "6 Sep", "7 Sep", "8 Sep",
                        "9 Sep", "10 Sep", "11 Sep", "12 Sep", "13 Sep", "14 Sep", "15 Sep",
                        "16 Sep", "17 Sep", "18 Sep", "19 Sep", "20 Sep", "21 Sep",
                        "22 Sep", "23 Sep", "24 Sep", "25 Sep", "26 Sep", "27 Sep", "28 Sep",
                        "29 Sep", "30 Sep"
                    ],
                    "plan": [
                        14.5, 14.5, 14.5, 14.5, 14.5, 14.5, 14.6, 14.6, 14.7, 14.7, 14.8,
                        14.8, 14.8, 14.8, 14.9, 14.9, 14.9, 15.0, 15.0, 15.0, 15.0,
                        15.1, 15.1, 15.2, 15.2, 15.3, 15.3, 15.4, 15.5, 15.5
                    ],
                    "actual": [
                        14.2, 14.4, 14.6, 14.3, 14.0, 13.5, 13.2, 13.6, 13.8, 13.2, 12.5,
                        10.6, 9.8, 9.5, 9.2, 11.5, 12.8, 13.0, 13.6, 13.3, 13.4,
                        None, None, None, None, None, None, None, None, None
                    ],
                    "forecast": [
                        None, None, None, None, None, None, None, None, None, None, None,
                        None, None, None, None, None, None, None, None, None, 13.4,
                        13.8, 14.2, 14.5, 14.8, 15.0, 15.1, 15.2, 15.4, 15.5
                    ],
                    "events": [
                        {
                            "date": "12 Sep",
                            "endDate": "15 Sep",
                            "title": "Planned Shutdown",
                            "type": "activity",
                            "field": "Field B",
                            "impact": "-2.8 kbopd",
                            "status": "Planned",
                            "description": "Scheduled biennial maintenance shutdown of train B separation."
                        }
                    ]
                },
                "Field C": {
                    "dates": [
                        "1 Sep", "2 Sep", "3 Sep", "4 Sep", "5 Sep", "6 Sep", "7 Sep", "8 Sep",
                        "9 Sep", "10 Sep", "11 Sep", "12 Sep", "13 Sep", "14 Sep", "15 Sep",
                        "16 Sep", "17 Sep", "18 Sep", "19 Sep", "20 Sep", "21 Sep",
                        "22 Sep", "23 Sep", "24 Sep", "25 Sep", "26 Sep", "27 Sep", "28 Sep",
                        "29 Sep", "30 Sep"
                    ],
                    "plan": [
                        10.2, 10.2, 10.2, 10.2, 10.3, 10.3, 10.3, 10.3, 10.4, 10.4, 10.4,
                        10.4, 10.4, 10.5, 10.5, 10.5, 10.5, 10.5, 10.5, 10.6, 10.6,
                        10.6, 10.6, 10.7, 10.7, 10.7, 10.7, 10.8, 10.8, 10.9
                    ],
                    "actual": [
                        10.2, 10.1, 10.3, 10.0, 9.8, 9.5, 9.2, 9.6, 9.8, 9.4, 8.8,
                        8.2, 7.8, 7.5, 7.2, 8.0, 8.2, 7.0, 8.2, 8.5, 8.8,
                        None, None, None, None, None, None, None, None, None
                    ],
                    "forecast": [
                        None, None, None, None, None, None, None, None, None, None, None,
                        None, None, None, None, None, None, None, None, None, 8.8,
                        9.2, 9.5, 9.8, 10.1, 10.3, 10.5, 10.6, 10.7, 10.8
                    ],
                    "events": [
                        {
                            "date": "18 Sep",
                            "title": "Compressor Trip",
                            "type": "issue",
                            "field": "Field C",
                            "impact": "-1.5 kbopd",
                            "status": "Open",
                            "recovery": "22 Sep",
                            "description": "Compressor A high discharge temperature trip. Lube oil filter replacement in progress."
                        }
                    ]
                },
                "Field D": {
                    "dates": [
                        "1 Sep", "2 Sep", "3 Sep", "4 Sep", "5 Sep", "6 Sep", "7 Sep", "8 Sep",
                        "9 Sep", "10 Sep", "11 Sep", "12 Sep", "13 Sep", "14 Sep", "15 Sep",
                        "16 Sep", "17 Sep", "18 Sep", "19 Sep", "20 Sep", "21 Sep",
                        "22 Sep", "23 Sep", "24 Sep", "25 Sep", "26 Sep", "27 Sep", "28 Sep",
                        "29 Sep", "30 Sep"
                    ],
                    "plan": [
                        8.5, 8.5, 8.5, 8.5, 8.5, 8.5, 8.5, 8.5, 8.5, 8.5, 8.6,
                        8.6, 8.6, 8.6, 8.6, 8.7, 8.7, 8.7, 8.7, 8.8, 8.8,
                        8.8, 8.8, 8.8, 8.8, 8.9, 8.9, 9.0, 9.0, 9.1
                    ],
                    "actual": [
                        8.4, 8.3, 8.5, 8.2, 8.1, 8.2, 8.2, 8.1, 8.3, 8.1, 8.0,
                        7.8, 7.8, 7.7, 7.6, 7.8, 8.0, 8.2, 8.2, 8.1, 8.2,
                        None, None, None, None, None, None, None, None, None
                    ],
                    "forecast": [
                        None, None, None, None, None, None, None, None, None, None, None,
                        None, None, None, None, None, None, None, None, None, 8.2,
                        8.3, 8.4, 8.5, 8.6, 8.7, 8.7, 8.8, 8.9, 9.0
                    ],
                    "events": [
                        {
                            "date": "27 Sep",
                            "title": "FGS",
                            "type": "activity",
                            "field": "Field D",
                            "impact": "-0.2 kbopd",
                            "status": "Planned",
                            "description": "Facility Gas Shutdown for emergency depressurization valve testing."
                        }
                    ]
                }
            },
            # Event Pins on the chart that link directly to Card 3 & Card 4
            "events": [
                {
                    "date": "3 Sep",
                    "title": "SGS",
                    "type": "activity",
                    "field": "Field A",
                    "impact": "-0.300 kbopd",
                    "status": "Completed",
                    "description": "Subsea Gas Surge flowline pressure validation completed."
                },
                {
                    "date": "12 Sep",
                    "endDate": "15 Sep",
                    "title": "Planned Shutdown",
                    "type": "activity",
                    "field": "Field B",
                    "impact": "-2.800 kbopd",
                    "status": "Planned",
                    "description": "Scheduled biennial maintenance shutdown of train B separation."
                },
                {
                    "date": "18 Sep",
                    "title": "Compressor Trip",
                    "type": "issue",
                    "field": "Field C",
                    "impact": "-1.500 kbopd",
                    "status": "Open",
                    "recovery": "22 Sep",
                    "description": "Compressor A high discharge temperature trip. Lube oil filter replacement in progress."
                },
                {
                    "date": "27 Sep",
                    "title": "FGS",
                    "type": "activity",
                    "field": "Field D",
                    "impact": "-0.200 kbopd",
                    "status": "Planned",
                    "description": "Facility Gas Shutdown for emergency depressurization valve testing."
                }
            ]
        },

        # -------------------------------------------------------------
        # CARD 2: Field Performance
        # -------------------------------------------------------------
        "field_performance": {
            "unit": "kbopd",
            "rows": [
                {
                    "field": "Field A",
                    "plan": 12.0,
                    "actual": 11.8,
                    "variance": -0.2,
                    "attainment": 98.0,
                    "trend": [11.5, 11.8, 12.0, 11.9, 11.8, 11.7, 11.8]
                },
                {
                    "field": "Field B",
                    "plan": 14.5,
                    "actual": 13.4,
                    "variance": -1.1,
                    "attainment": 92.0,
                    "trend": [14.2, 13.8, 13.0, 12.5, 13.1, 13.3, 13.4]
                },
                {
                    "field": "Field C",
                    "plan": 10.2,
                    "actual": 8.8,
                    "variance": -1.4,
                    "attainment": 86.0,
                    "trend": [10.2, 10.0, 9.5, 8.5, 8.6, 8.7, 8.8]
                },
                {
                    "field": "Field D",
                    "plan": 8.5,
                    "actual": 8.2,
                    "variance": -0.3,
                    "attainment": 96.0,
                    "trend": [8.4, 8.3, 8.5, 8.2, 8.1, 8.2, 8.2]
                }
            ],
            "total": {
                "field": "Total",
                "plan": 45.2,
                "actual": 42.6,
                "variance": -2.6,
                "attainment": 94.2,
                "trend": [44.3, 43.9, 43.0, 41.1, 41.6, 41.9, 42.6]
            }
        },

        # -------------------------------------------------------------
        # CARD 3: Planned Activities (Upcoming)
        # -------------------------------------------------------------
        "planned_activities": [
            {
                "date": "22 Sep 2026",
                "activity": "SGS",
                "field": "Field A",
                "expected_impact": "-0.300 kbopd",
                "status": "Planned"
            },
            {
                "date": "24-26 Sep 2026",
                "activity": "Planned Shutdown",
                "field": "Field B",
                "expected_impact": "-2.800 kbopd",
                "status": "Planned"
            },
            {
                "date": "27 Sep 2026",
                "activity": "FGS",
                "field": "Field D",
                "expected_impact": "-0.200 kbopd",
                "status": "Planned"
            },
            {
                "date": "30 Sep 2026",
                "activity": "Well Intervention",
                "field": "Field A",
                "expected_impact": "-0.400 kbopd",
                "status": "Planned"
            },
            {
                "date": "2 Oct 2026",
                "activity": "Separator Maintenance",
                "field": "Field C",
                "expected_impact": "-0.300 kbopd",
                "status": "Planned"
            }
        ],

        # -------------------------------------------------------------
        # CARD 4: Active Issues & Mitigation
        # -------------------------------------------------------------
        "active_issues": [
            {
                "issue": "Compressor A Trip",
                "field": "Field C",
                "impact": "-1.500 kbopd",
                "status": "Open",
                "recovery": "22 Sep",
                "description": "Lube oil pressure failure on 18 Sep. Replacement cartridge dispatched; restart at 14:00.",
                "remarks": "Lube oil pressure failure on 18 Sep. Replacement cartridge dispatched; restart at 14:00."
            },
            {
                "issue": "Well A-12 ESP",
                "field": "Field A",
                "impact": "-0.600 kbopd",
                "status": "Monitoring",
                "recovery": "23 Sep",
                "description": "Electrical submersible pump variable speed drive hunting. Operating on reduced choke.",
                "remarks": "Electrical submersible pump variable speed drive hunting. Operating on reduced choke."
            },
            {
                "issue": "Separator Pressure",
                "field": "Field B",
                "impact": "-0.400 kbopd",
                "status": "In Progress",
                "recovery": "21 Sep",
                "description": "Backpressure regulator diaphragm inspection underway on production separator V-101.",
                "remarks": "Backpressure regulator diaphragm inspection underway on production separator V-101."
            },
            {
                "issue": "High Gas Lift Rate",
                "field": "Field D",
                "impact": "-0.300 kbopd",
                "status": "Monitoring",
                "recovery": "28 Sep",
                "description": "Subsea gas lift distribution valve optimization in progress to prevent reservoir breakthrough.",
                "remarks": "Subsea gas lift distribution valve optimization in progress to prevent reservoir breakthrough."
            },
            {
                "issue": "Instrument Failure",
                "field": "Field B",
                "impact": "-0.200 kbopd",
                "status": "Closed",
                "recovery": "-",
                "description": "Transmitter PT-401 swapped and loop calibrated successfully.",
                "remarks": "Transmitter PT-401 swapped and loop calibrated successfully."
            }
        ],

        # -------------------------------------------------------------
        # CARD 5: Offloading Planning
        # -------------------------------------------------------------
        "offloading_planning": {
            "unit": "MMbbl",
            "max_capacity": 3.5,
            "target_offload": 3.0,
            "current_inventory": 2.4,
            "current_date": "21 Sep 2026",
            "dates": [
                "1 Sep", "3 Sep", "5 Sep", "7 Sep", "9 Sep", "11 Sep", "13 Sep",
                "15 Sep", "17 Sep", "19 Sep", "21 Sep",
                "23 Sep", "25 Sep", "27 Sep", "29 Sep", "1 Oct", "3 Oct", "5 Oct",
                "7 Oct", "9 Oct", "11 Oct", "13 Oct", "15 Oct"
            ],
            # Actual inventory curve up to 21 Sep
            "actual_inventory": [
                1.1, 1.25, 1.4, 1.55, 1.8, 1.9, 2.05, 2.15, 2.22, 2.32, 2.4,
                None, None, None, None, None, None, None, None, None, None, None, None
            ],
            # Scenario forecasts from 21 Sep reaching 3.0 target
            "p10_early": [
                None, None, None, None, None, None, None, None, None, None, 2.4,
                2.52, 2.65, 2.78, 2.9, 2.98, 3.05, 3.12, 3.18, 3.25, 3.3, 3.35, 3.4
            ],
            "p50_base": [
                None, None, None, None, None, None, None, None, None, None, 2.4,
                2.48, 2.56, 2.65, 2.73, 2.81, 2.89, 2.97, 3.04, 3.12, 3.19, 3.25, 3.3
            ],
            "p90_late": [
                None, None, None, None, None, None, None, None, None, None, 2.4,
                2.44, 2.5, 2.56, 2.62, 2.68, 2.75, 2.82, 2.88, 2.95, 3.02, 3.08, 3.14
            ],
            "milestones": {
                "p10": {"date": "5 Oct", "level": 3.05, "tag": "P10 5 Oct"},
                "p50": {"date": "8 Oct", "level": 3.08, "tag": "P50 8 Oct"},
                "p90": {"date": "12 Oct", "level": 3.02, "tag": "P90 12 Oct"}
            }
        },

        # -------------------------------------------------------------
        # CARD 6: Offloading Estimation
        # -------------------------------------------------------------
        "offloading_estimation": {
            "current_inventory": 2.4,
            "target_offload_level": 3.0,
            "maximum_capacity": 3.5,
            "scenarios": [
                {
                    "scenario": "P10 (Early)",
                    "estimated_offload_date": "5 Oct 2026",
                    "days_from_now": "14 days",
                    "tag_class": "p10-tag"
                },
                {
                    "scenario": "P50 (Base)",
                    "estimated_offload_date": "8 Oct 2026",
                    "days_from_now": "17 days",
                    "tag_class": "p50-tag"
                },
                {
                    "scenario": "P90 (Late)",
                    "estimated_offload_date": "12 Oct 2026",
                    "days_from_now": "21 days",
                    "tag_class": "p90-tag"
                }
            ]
        },

        # Footer AI Insight
        "ai_insight": {
            "text": "Production is expected to recover by 1.5 kbopd after Field C compressor restart on 22 Sep. Overall EOM forecast is 43.5 kbopd, assuming no additional unplanned downtime."
        }
    }
