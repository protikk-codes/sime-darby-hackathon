"""Complaint management. Status changes are recorded in complaint_history.

Nothing in this module closes a complaint automatically. Status changes come
only from an explicit call with a value chosen by a person.
"""
import sqlite3
from datetime import date

import config as cfg
from services.assets import get_asset
from services.base import execute, fetch_all, fetch_one
from services.errors import DatabaseFailure, NotFoundError, ValidationError

EDITABLE_FIELDS = ("status", "urgency", "assigned_to")


def _choice(value, options, label):
    text = str(value or "").strip()
    if text not in options:
        raise ValidationError(f"{label} must be one of: {', '.join(options)}.")
    return text


def create_complaint(conn, data):
    title = str(data.get("title") or "").strip()
    if not title:
        raise ValidationError("Complaint title is required.")
    location = str(data.get("location") or "").strip()
    if not location:
        raise ValidationError("Location is required.")
    category = _choice(data.get("category"), cfg.ASSET_TYPES, "Category")
    urgency = _choice(data.get("urgency"), cfg.URGENCIES, "Urgency")
    status = _choice(data.get("status") or "Open", cfg.COMPLAINT_STATUSES, "Status")
    try:
        reported = date.fromisoformat(str(data.get("date_reported") or date.today().isoformat())).isoformat()
    except ValueError:
        raise ValidationError("Date reported must be in YYYY-MM-DD format.")

    asset_code = str(data.get("asset_code") or "").strip().upper() or None
    if asset_code:
        get_asset(conn, asset_code)  # raises NotFoundError if unknown

    return execute(conn, """
        INSERT INTO complaints (title, description, location, category, date_reported, urgency, status,
                                reporter_name, reporter_contact, assigned_to, asset_code)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        title,
        str(data.get("description") or "").strip(),
        location, category, reported, urgency, status,
        str(data.get("reporter_name") or "").strip(),
        str(data.get("reporter_contact") or "").strip(),
        str(data.get("assigned_to") or "").strip(),
        asset_code,
    ))


def get_complaint(conn, complaint_id):
    row = fetch_one(conn, "SELECT * FROM complaints WHERE id = ?", (int(complaint_id),))
    if row is None:
        raise NotFoundError(f"No complaint with ID {complaint_id}.")
    return row


def update_complaint(conn, complaint_id, changes, note=""):
    """Apply changes (status, urgency, assigned_to). Each real change is logged to history."""
    current = get_complaint(conn, complaint_id)
    updates = {}
    for field, value in changes.items():
        if field not in EDITABLE_FIELDS:
            raise ValidationError(f"Field '{field}' cannot be changed here.")
        if field == "assigned_to":
            new_value = str(value or "").strip()
        elif field == "status":
            new_value = _choice(value, cfg.COMPLAINT_STATUSES, "Status")
        else:
            new_value = _choice(value, cfg.URGENCIES, "Urgency")
        if str(current[field] or "") != new_value:
            updates[field] = new_value
    if not updates:
        return current

    try:
        for field, new_value in updates.items():
            conn.execute(
                "INSERT INTO complaint_history (complaint_id, field, old_value, new_value, note) "
                "VALUES (?, ?, ?, ?, ?)",
                (current["id"], field, str(current[field] or ""), new_value, str(note or "").strip()),
            )
            # field is restricted to EDITABLE_FIELDS above, so this f-string is safe.
            conn.execute(
                f"UPDATE complaints SET {field} = ?, updated_at = datetime('now') WHERE id = ?",
                (new_value, current["id"]),
            )
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        raise DatabaseFailure(f"Could not update complaint: {exc}") from exc
    return get_complaint(conn, complaint_id)


def list_complaints(conn, status="", urgency=""):
    sql = "SELECT * FROM complaints WHERE 1=1"
    params = []
    if status:
        sql += " AND status = ?"
        params.append(status)
    if urgency:
        sql += " AND urgency = ?"
        params.append(urgency)
    sql += " ORDER BY date_reported, id"
    return fetch_all(conn, sql, tuple(params))


def complaint_history(conn, complaint_id):
    return fetch_all(
        conn,
        "SELECT * FROM complaint_history WHERE complaint_id = ? ORDER BY id",
        (int(complaint_id),),
    )


def is_open(complaint):
    return complaint["status"] in cfg.OPEN_STATUSES


def days_open(complaint, today=None):
    today = today or date.today()
    return (today - date.fromisoformat(complaint["date_reported"])).days


def list_complaints_by_contact(conn, contact):
    """Reports left by one resident, matched on the contact they gave. Not a secure login."""
    text = str(contact or "").strip()
    if not text:
        return []
    return fetch_all(
        conn,
        "SELECT * FROM complaints WHERE lower(reporter_contact) = lower(?) ORDER BY id DESC",
        (text,),
    )
