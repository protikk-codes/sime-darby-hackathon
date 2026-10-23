"""Dashboard metrics. Every figure is computed from the database or the risk engine."""
from datetime import date

import config as cfg
from intelligence.risk import assess_all
from services.base import fetch_all, fetch_one
from services.maintenance import total_cost


def dashboard_metrics(conn, today=None):
    today = today or date.today()
    open_placeholders = ",".join("?" for _ in cfg.OPEN_STATUSES)
    open_params = tuple(cfg.OPEN_STATUSES)

    total_assets = fetch_one(conn, "SELECT COUNT(*) AS n FROM assets")["n"]
    risks = assess_all(conn, today)

    by_risk = {level: 0 for level in ("Low", "Medium", "High", "Critical")}
    for result in risks:
        by_risk[result.level] += 1

    overdue = [r for r in risks if r.overdue]
    upcoming = [r for r in risks if not r.overdue and r.days_to_due <= cfg.UPCOMING_WINDOW_DAYS]
    recurring = [r for r in risks if r.repair_count >= cfg.REPEAT_MIN_REPAIRS]

    open_complaints = fetch_one(
        conn, f"SELECT COUNT(*) AS n FROM complaints WHERE status IN ({open_placeholders})", open_params
    )["n"]
    urgent_open = fetch_one(
        conn,
        f"SELECT COUNT(*) AS n FROM complaints WHERE status IN ({open_placeholders}) "
        "AND urgency IN ('High', 'Critical')",
        open_params,
    )["n"]

    recent = fetch_all(conn, """
        SELECT r.record_date, r.asset_code, a.name, r.category, r.description, r.cost_rm, r.status
        FROM maintenance_records r
        JOIN assets a ON a.asset_code = r.asset_code
        ORDER BY r.record_date DESC, r.id DESC
        LIMIT 5
    """)

    return {
        "total_assets": total_assets,
        "by_risk": by_risk,
        "overdue": overdue,
        "upcoming": upcoming,
        "recurring": recurring,
        "open_complaints": open_complaints,
        "urgent_open_complaints": urgent_open,
        "total_spend": total_cost(conn),
        "recent_records": recent,
        "risks": risks,
    }
