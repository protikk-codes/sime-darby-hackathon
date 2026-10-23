"""Impact estimates for the pilot case.

Every figure is calculated from stored records. Values that depend on an
assumption are labelled as estimates, and the assumptions are returned with
the results so the UI can show them. None of these are measured outcomes.
"""
from datetime import date, timedelta

import config as cfg
from intelligence.risk import assess_all
from services.base import fetch_all
from services.complaints import days_open, is_open, list_complaints


def impact_summary(conn, today=None):
    today = today or date.today()
    risks = assess_all(conn, today)
    recurring = [r for r in risks if r.repair_count >= cfg.REPEAT_MIN_REPAIRS]
    recurring_codes = {r.asset_code for r in recurring}

    window_start = today - timedelta(days=cfg.REPEAT_WINDOW_DAYS)
    records = fetch_all(conn, "SELECT asset_code, record_date, category, cost_rm FROM maintenance_records")
    repeat_spend = sum(
        r["cost_rm"] for r in records
        if r["category"] == "Repair" and r["asset_code"] in recurring_codes
        and window_start <= date.fromisoformat(r["record_date"]) <= today
    )

    complaints = list_complaints(conn)
    open_items = [c for c in complaints if is_open(c)]
    open_ages = [days_open(c, today) for c in open_items]
    avoidable_share = cfg.IMPACT_ASSUMPTIONS["avoidable_repeat_repair_share"]
    staff_cost = cfg.IMPACT_ASSUMPTIONS["staff_cost_per_complaint_rm"]

    return {
        "total_assets": len(risks),
        "overdue_inspections": sum(1 for r in risks if r.overdue),
        "high_risk_assets": sum(1 for r in risks if r.level in ("High", "Critical")),
        "recurring_defect_assets": len(recurring),
        "repeat_repair_spend_rm": round(repeat_spend, 2),
        "estimated_avoidable_spend_rm": round(repeat_spend * avoidable_share, 2),
        "open_complaints": len(open_items),
        "oldest_open_complaint_days": max(open_ages) if open_ages else 0,
        "avg_open_complaint_days": round(sum(open_ages) / len(open_ages), 1) if open_ages else 0,
        "estimated_complaint_handling_cost_rm": round(len(complaints) * staff_cost, 2),
        "assumptions": [
            f"Assumes {avoidable_share:.0%} of repeat-repair spend could be avoided with earlier inspection.",
            f"Assumes RM {staff_cost:,.2f} of staff time per complaint handled by hand.",
            "All figures come from the sample records and are not measured results.",
        ],
    }
