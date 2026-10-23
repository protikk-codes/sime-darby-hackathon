"""Asset register: validation, create, read, update, delete and search."""
import re
import sqlite3
from datetime import date

import config as cfg
from services.base import execute, fetch_all, fetch_one
from services.errors import NotFoundError, ValidationError

CODE_PATTERN = re.compile(r"[A-Z0-9-]{3,20}")


def _to_int(value, label, low, high, errors):
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        errors.append(f"{label} must be a whole number.")
        return None
    if not low <= number <= high:
        errors.append(f"{label} must be between {low} and {high}.")
        return None
    return number


def validate_asset(data):
    """Return a cleaned asset dict, or raise ValidationError listing every problem."""
    errors = []
    code = str(data.get("asset_code") or "").strip().upper()
    if not code:
        errors.append("Asset code is required.")
    elif not CODE_PATTERN.fullmatch(code):
        errors.append("Asset code may only contain letters, digits and hyphens (3-20 characters).")

    name = str(data.get("name") or "").strip()
    if not name:
        errors.append("Name is required.")
    asset_type = str(data.get("asset_type") or "").strip()
    if asset_type not in cfg.ASSET_TYPES:
        errors.append(f"Asset type must be one of: {', '.join(cfg.ASSET_TYPES)}.")
    location = str(data.get("location") or "").strip()
    if not location:
        errors.append("Location is required.")
    condition = str(data.get("condition") or "").strip()
    if condition not in cfg.CONDITIONS:
        errors.append(f"Condition must be one of: {', '.join(cfg.CONDITIONS)}.")

    last_inspection = None
    try:
        last_inspection = date.fromisoformat(str(data.get("last_inspection") or "").strip()).isoformat()
    except ValueError:
        errors.append("Last inspection must be a date in YYYY-MM-DD format.")

    install_year = _to_int(data.get("install_year"), "Installation year", 1900, date.today().year, errors)
    lifespan = _to_int(data.get("lifespan_years"), "Expected lifespan (years)", 1, 200, errors)
    interval = _to_int(data.get("maintenance_interval_days"), "Maintenance interval (days)", 1, 3650, errors)
    notes = str(data.get("notes") or "").strip()

    if errors:
        raise ValidationError(" ".join(errors))
    return {
        "asset_code": code, "name": name, "asset_type": asset_type, "location": location,
        "install_year": install_year, "lifespan_years": lifespan, "condition": condition,
        "last_inspection": last_inspection, "maintenance_interval_days": interval, "notes": notes,
    }


def create_asset(conn, data):
    clean = validate_asset(data)
    try:
        execute(conn, """
            INSERT INTO assets (asset_code, name, asset_type, location, install_year, lifespan_years,
                                condition, last_inspection, maintenance_interval_days, notes)
            VALUES (:asset_code, :name, :asset_type, :location, :install_year, :lifespan_years,
                    :condition, :last_inspection, :maintenance_interval_days, :notes)
        """, clean)
    except sqlite3.IntegrityError as exc:
        raise ValidationError(f"Asset code {clean['asset_code']} already exists.") from exc
    return clean["asset_code"]


def get_asset(conn, asset_code):
    code = str(asset_code or "").strip().upper()
    row = fetch_one(conn, "SELECT * FROM assets WHERE asset_code = ?", (code,))
    if row is None:
        raise NotFoundError(f"No asset with code {code or '(blank)'}.")
    return row


def update_asset(conn, asset_code, data):
    current = get_asset(conn, asset_code)
    clean = validate_asset({**data, "asset_code": current["asset_code"]})  # the code cannot change
    execute(conn, """
        UPDATE assets SET name = :name, asset_type = :asset_type, location = :location,
               install_year = :install_year, lifespan_years = :lifespan_years, condition = :condition,
               last_inspection = :last_inspection, maintenance_interval_days = :maintenance_interval_days,
               notes = :notes, updated_at = datetime('now')
        WHERE asset_code = :asset_code
    """, clean)
    return current["asset_code"]


def delete_asset(conn, asset_code):
    current = get_asset(conn, asset_code)
    execute(conn, "DELETE FROM assets WHERE asset_code = ?", (current["asset_code"],))


def list_assets(conn, search="", asset_type="", condition=""):
    sql = "SELECT * FROM assets WHERE 1=1"
    params = []
    if search and search.strip():
        sql += " AND (asset_code LIKE ? OR name LIKE ? OR location LIKE ?)"
        like = f"%{search.strip()}%"
        params += [like, like, like]
    if asset_type:
        sql += " AND asset_type = ?"
        params.append(asset_type)
    if condition:
        sql += " AND condition = ?"
        params.append(condition)
    sql += " ORDER BY asset_code"
    return fetch_all(conn, sql, tuple(params))
