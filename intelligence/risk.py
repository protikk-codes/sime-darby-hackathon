"""Explainable, rule-based risk engine.

Scores are transparent weighted rules (see config.RISK_WEIGHTS). They are NOT
trained predictions and do not prove that an asset will fail. Every point in
the score is traceable to a listed reason.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta

import config as cfg
from services.assets import list_assets
from services.maintenance import list_records


@dataclass
class RiskResult:
    asset_code: str
    name: str
    asset_type: str
    age_years: int
    lifespan_years: int
    lifespan_used_pct: float
    next_due: str
    days_to_due: int
    overdue: bool
    repair_count: int
    repair_dates: list = field(default_factory=list)
    score: int = 0
    level: str = "Low"
    reasons: list = field(default_factory=list)
    actions: list = field(default_factory=list)


def level_for_score(score):
    for level, threshold in cfg.RISK_LEVEL_THRESHOLDS:
        if score >= threshold:
            return level
    return "Low"


def assess_asset(asset, records, today=None):
    """Score one asset from its row and its maintenance records (dicts)."""
    today = today or date.today()
    weights = cfg.RISK_WEIGHTS
    reasons, actions = [], []
    points = 0.0

    # Age: share of expected lifespan used, capped so very old assets still score at most the full weight.
    age = max(0, today.year - int(asset["install_year"]))
    lifespan = int(asset["lifespan_years"])
    used = age / lifespan
    points += min(used, 1.5) / 1.5 * weights["age"]
    if used >= cfg.AGE_CONCERN_RATIO:
        reasons.append(f"Age of {age} years is {used * 100:.0f}% of the expected {lifespan}-year lifespan.")
        actions.append("Review replacement or renewal options in the capital plan.")

    # Condition
    condition = asset["condition"]
    points += weights["condition"].get(condition, 0)
    if condition == "Poor":
        reasons.append("Recorded condition is Poor.")
        actions.append("Prioritise repair or a detailed condition survey.")
    elif condition == "Fair":
        reasons.append("Recorded condition is Fair.")

    # Inspection schedule
    last = date.fromisoformat(asset["last_inspection"])
    next_due = last + timedelta(days=int(asset["maintenance_interval_days"]))
    days_to_due = (next_due - today).days
    overdue = days_to_due < 0
    if overdue:
        points += weights["overdue"]
        reasons.append(f"Inspection overdue by {-days_to_due} days (due {next_due.isoformat()}).")
        actions.append("Schedule the overdue inspection now.")
    elif days_to_due <= cfg.UPCOMING_WINDOW_DAYS:
        reasons.append(f"Inspection due in {days_to_due} days ({next_due.isoformat()}).")
        actions.append("Plan the inspection before the due date.")

    # Repeated repairs inside the look-back window (only past or current records count)
    window_start = today - timedelta(days=cfg.REPEAT_WINDOW_DAYS)
    repair_dates = []
    for record in records:
        if record["category"] != "Repair":
            continue
        when = date.fromisoformat(record["record_date"])
        if window_start <= when <= today:
            repair_dates.append(when.isoformat())
    repair_dates.sort()
    if len(repair_dates) >= cfg.REPEAT_MIN_REPAIRS:
        points += weights["repeat"]
        reasons.append(
            f"{len(repair_dates)} repairs in the last {cfg.REPEAT_WINDOW_DAYS} days "
            f"({', '.join(repair_dates)})."
        )
        actions.append("Investigate the root cause of the recurring repairs.")

    if not reasons:
        reasons.append("No risk factors found in the current records.")
    if not actions:
        actions.append("Continue routine monitoring.")

    score = min(100, round(points))
    return RiskResult(
        asset_code=asset["asset_code"],
        name=asset["name"],
        asset_type=asset["asset_type"],
        age_years=age,
        lifespan_years=lifespan,
        lifespan_used_pct=round(used * 100, 1),
        next_due=next_due.isoformat(),
        days_to_due=days_to_due,
        overdue=overdue,
        repair_count=len(repair_dates),
        repair_dates=repair_dates,
        score=score,
        level=level_for_score(score),
        reasons=reasons,
        actions=list(dict.fromkeys(actions)),
    )


def assess_all(conn, today=None):
    """Assess every asset in the database. Highest score first."""
    today = today or date.today()
    records_by_asset = {}
    for record in list_records(conn):
        records_by_asset.setdefault(record["asset_code"], []).append(record)
    results = [
        assess_asset(asset, records_by_asset.get(asset["asset_code"], []), today)
        for asset in list_assets(conn)
    ]
    results.sort(key=lambda r: (-r.score, r.asset_code))
    return results
