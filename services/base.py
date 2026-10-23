"""Small query helpers shared by the services. Always pass values as parameters."""
import sqlite3

from services.errors import DatabaseFailure


def fetch_all(conn, sql, params=()):
    try:
        return [dict(row) for row in conn.execute(sql, params).fetchall()]
    except sqlite3.Error as exc:
        raise DatabaseFailure(f"Database read failed: {exc}") from exc


def fetch_one(conn, sql, params=()):
    rows = fetch_all(conn, sql, params)
    return rows[0] if rows else None


def execute(conn, sql, params=()):
    """Run a write and commit. Returns lastrowid. IntegrityError is re-raised for callers to map."""
    try:
        cursor = conn.execute(sql, params)
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        conn.rollback()
        raise
    except sqlite3.Error as exc:
        conn.rollback()
        raise DatabaseFailure(f"Database write failed: {exc}") from exc
