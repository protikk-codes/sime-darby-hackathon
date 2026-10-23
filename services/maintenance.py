"""Maintenance and inspection records linked to assets."""
from datetime import date

import config as cfg
from services.assets import get_asset
from services.base import execute, fetch_all
from services.errors import ValidationError

_JOIN = """
    FROM maintenance_records r
    JOIN assets a ON a.asset_code = r.asset_code
"""


def add_record(conn, data):
    code = str(data.get("asset_code") or "").strip().upper()
    get_asset(conn, code)  # raises NotFoundError if the asset does not exist

    try:
        record_date = date.fromisoformat(str(data.get("record_date") or "").strip()).isoformat()
    except ValueError:
        raise ValidationError("Record date must be in YYYY-MM-DD format.")

    category = str(data.get("category") or "").strip()
    if category not in cfg.RECORD_CATEGORIES:
        raise ValidationError(f"Category must be one of: {', '.join(cfg.RECORD_CATEGORIES)}.")
    description = str(data.get("description") or "").strip()
    if not description:
        raise ValidationError("Description is required.")
    try:
        cost = round(float(data.get("cost_rm") or 0), 2)
    except (TypeError, ValueError):
        raise ValidationError("Cost must be a number.")
    if cost < 0:
        raise ValidationError("Cost cannot be negative.")
    status = str(data.get("status") or "").strip()
    if status not in cfg.RECORD_STATUSES:
        raise ValidationError(f"Status must be one of: {', '.join(cfg.RECORD_STATUSES)}.")

    return execute(conn, """
        INSERT INTO maintenance_records (asset_code, record_date, category, description, cost_rm, status)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (code, record_date, category, description, cost, status))


def list_records(conn, asset_code=None):
    """All records in chronological order, optionally for one asset."""
    sql = f"""
        SELECT r.id, r.asset_code, r.record_date, r.category, r.description,
               r.cost_rm, r.status, a.name AS asset_name, a.asset_type
        {_JOIN}
    """
    params = ()
    if asset_code:
        sql += " WHERE r.asset_code = ?"
        params = (str(asset_code).strip().upper(),)
    sql += " ORDER BY r.record_date, r.id"
    return fetch_all(conn, sql, params)


def total_cost(conn, category="", asset_type=""):
    """Sum of recorded costs in RM, optionally filtered by category or asset type."""
    sql = f"SELECT COALESCE(SUM(r.cost_rm), 0) AS total {_JOIN} WHERE 1=1"
    params = []
    if category:
        sql += " AND r.category = ?"
        params.append(category)
    if asset_type:
        sql += " AND a.asset_type = ?"
        params.append(asset_type)
    return float(fetch_all(conn, sql, tuple(params))[0]["total"])
