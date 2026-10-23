"""SQLite connection handling and schema. All SQL in the app is parameterised."""
import sqlite3
from pathlib import Path

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    asset_type TEXT NOT NULL,
    location TEXT NOT NULL,
    install_year INTEGER NOT NULL,
    lifespan_years INTEGER NOT NULL,
    condition TEXT NOT NULL,
    last_inspection TEXT NOT NULL,
    maintenance_interval_days INTEGER NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS maintenance_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_code TEXT NOT NULL REFERENCES assets(asset_code) ON DELETE CASCADE,
    record_date TEXT NOT NULL,
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    cost_rm REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS complaints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    location TEXT NOT NULL,
    category TEXT NOT NULL,
    date_reported TEXT NOT NULL,
    urgency TEXT NOT NULL,
    status TEXT NOT NULL,
    reporter_name TEXT NOT NULL DEFAULT '',
    reporter_contact TEXT NOT NULL DEFAULT '',
    assigned_to TEXT NOT NULL DEFAULT '',
    asset_code TEXT REFERENCES assets(asset_code) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS complaint_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    complaint_id INTEGER NOT NULL REFERENCES complaints(id) ON DELETE CASCADE,
    changed_at TEXT NOT NULL DEFAULT (datetime('now')),
    field TEXT NOT NULL,
    old_value TEXT,
    new_value TEXT,
    note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS agent_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL DEFAULT (datetime('now')),
    proposal_ref TEXT NOT NULL,
    tool TEXT NOT NULL,
    args_json TEXT NOT NULL,
    status TEXT NOT NULL,
    result TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_records_asset ON maintenance_records(asset_code);
"""


def connect(path=None):
    """Open a connection. Pass ":memory:" for tests.

    check_same_thread is False because the Flet UI may call the database from
    its own thread. The app only ever uses one connection, so this is safe here.
    """
    target = str(path if path is not None else DB_PATH)
    if target != ":memory:":
        Path(target).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path=None):
    """Open a connection and create any missing tables. Never drops data."""
    conn = connect(path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn
