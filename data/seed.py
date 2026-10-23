"""Synthetic sample data. Every record is fictional and labelled as such.

Dates are generated relative to "today" so the demo always shows a mix of
overdue, upcoming and healthy inspections.
"""
from datetime import date, timedelta

from services import assets as asset_svc
from services import complaints as comp_svc
from services import maintenance as maint_svc

SAMPLE_BANNER = "SYNTHETIC SAMPLE DATA - fictional records for demonstration only"

# code, name, type, location, install_year, lifespan, condition, last_inspection_days_ago, interval_days
SAMPLE_ASSETS = [
    ("WP-001", "Jalan Utama water main, Block A", "Water pipeline", "Block A", 1998, 40, "Fair", 220, 180),
    ("WP-002", "Water main, Block C", "Water pipeline", "Block C", 2019, 40, "Good", 60, 180),
    ("WP-003", "Standpipe, Block F", "Water pipeline", "Block F", 2001, 40, "Fair", 120, 180),
    ("DR-001", "Main drain, Market Road", "Drainage", "Market Road", 1995, 35, "Poor", 200, 90),
    ("DR-002", "Culvert, Hillside", "Drainage", "Hillside", 2012, 30, "Fair", 30, 120),
    ("RD-001", "Access road, Stadium Lane", "Road", "Stadium Lane", 2005, 20, "Poor", 150, 365),
    ("RD-002", "Community road, Riverside", "Road", "Riverside", 2021, 20, "Good", 20, 365),
    ("SL-001", "Streetlight cluster, Park", "Streetlight", "Park", 2008, 15, "Fair", 100, 180),
    ("SL-002", "Streetlight, Block B gate", "Streetlight", "Block B", 2022, 15, "Good", 10, 180),
    ("PM-001", "Booster pump, Reservoir 2", "Pump", "Reservoir 2", 2000, 25, "Poor", 85, 90),
    ("PM-002", "Sump pump, Block D", "Pump", "Block D", 2016, 20, "Good", 200, 120),
    ("OT-001", "Community hall generator", "Other", "Community Hall", 2010, 25, "Fair", 30, 180),
]

# asset_code, days_ago, category, description, cost_rm, status
SAMPLE_RECORDS = [
    ("WP-001", 420, "Inspection", "Annual pressure test", 0, "Completed"),
    ("WP-001", 300, "Repair", "Burst joint near Block A valve chamber", 850, "Completed"),
    ("WP-001", 200, "Repair", "Leak at same joint after pressure surge", 1200, "Completed"),
    ("WP-001", 40, "Repair", "Recurring leak repaired with clamp", 640, "Completed"),
    ("WP-002", 60, "Inspection", "Routine pressure check", 0, "Completed"),
    ("WP-002", 150, "Preventive maintenance", "Valve greasing", 180, "Completed"),
    ("WP-003", 120, "Repair", "Standpipe tap replaced", 210, "Completed"),
    ("DR-001", 500, "Repair", "Blocked outlet cleared after storm", 420, "Completed"),
    ("DR-001", 200, "Inspection", "Sediment survey", 0, "Completed"),
    ("DR-001", 120, "Repair", "Collapsed grate replaced", 980, "Completed"),
    ("DR-002", 30, "Cleaning", "Silt removal at inlet", 300, "Completed"),
    ("RD-001", 250, "Repair", "Pothole patching", 560, "Completed"),
    ("RD-001", 150, "Inspection", "Surface condition survey", 0, "Completed"),
    ("RD-001", 90, "Repair", "Edge crack repair", 720, "Completed"),
    ("RD-002", 20, "Inspection", "Post-construction inspection", 0, "Completed"),
    ("SL-001", 100, "Repair", "Two lamps replaced", 240, "Completed"),
    ("SL-001", 10, "Preventive maintenance", "Lamp cleaning", 90, "Deferred"),
    ("SL-002", 10, "Inspection", "Commissioning check", 0, "Completed"),
    ("PM-001", 400, "Repair", "Seal failure repaired", 950, "Completed"),
    ("PM-001", 80, "Repair", "Impeller bearing replaced", 1800, "Completed"),
    ("PM-002", 200, "Inspection", "Float switch test", 0, "Completed"),
    ("OT-001", 30, "Preventive maintenance", "Generator service", 650, "Completed"),
]

# title, description, location, category, days_ago_reported, urgency, status, asset_code, assigned_to
SAMPLE_COMPLAINTS = [
    ("Low water pressure on Block A", "Taps run weak in the morning.", "Block A", "Water pipeline", 45, "High", "Open", "WP-001", ""),
    ("Drain overflow after rain", "Water pools across Market Road after heavy rain.", "Market Road", "Drainage", 60, "Critical", "In progress", "DR-001", "Drainage team"),
    ("Streetlight out near park gate", "Two lamps not working at night.", "Park", "Streetlight", 25, "Medium", "Assigned", "SL-001", "Electrical crew"),
    ("Pothole on Stadium Lane", "Deep pothole near the bus stop.", "Stadium Lane", "Road", 12, "High", "Under review", "RD-001", ""),
    ("Pump noise at Reservoir 2", "Loud grinding noise from the booster pump.", "Reservoir 2", "Pump", 3, "Medium", "Open", "PM-001", ""),
    ("Blocked culvert", "Culvert partly blocked with leaves.", "Hillside", "Drainage", 90, "Low", "Resolved", "DR-002", "Drainage team"),
    ("Dim light at Block B gate", "Gate light flickers.", "Block B", "Streetlight", 8, "Low", "Closed", "SL-002", ""),
    ("Water meter leak", "Small leak at the meter box.", "Block C", "Water pipeline", 15, "Medium", "Open", "WP-002", ""),
]


def _iso(today, days_ago):
    return (today - timedelta(days=days_ago)).isoformat()


def load_sample(conn, today=None):
    """Insert the synthetic sample dataset. Assumes the tables are empty."""
    today = today or date.today()
    for code, name, atype, location, year, life, cond, insp_ago, interval in SAMPLE_ASSETS:
        asset_svc.create_asset(conn, {
            "asset_code": code, "name": name, "asset_type": atype, "location": location,
            "install_year": year, "lifespan_years": life, "condition": cond,
            "last_inspection": _iso(today, insp_ago),
            "maintenance_interval_days": interval, "notes": SAMPLE_BANNER,
        })
    for code, ago, category, description, cost, status in SAMPLE_RECORDS:
        maint_svc.add_record(conn, {
            "asset_code": code, "record_date": _iso(today, ago), "category": category,
            "description": description, "cost_rm": cost, "status": status,
        })
    for title, desc, location, category, ago, urgency, status, asset_code, assigned in SAMPLE_COMPLAINTS:
        comp_svc.create_complaint(conn, {
            "title": title, "description": desc, "location": location, "category": category,
            "date_reported": _iso(today, ago), "urgency": urgency, "status": status,
            "asset_code": asset_code, "assigned_to": assigned,
            "reporter_name": "Sample resident", "reporter_contact": "sample-only",
        })


def seed_if_empty(conn, today=None):
    """Load sample data only if there are no assets. Never overwrites user records."""
    count = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
    if count:
        return False
    load_sample(conn, today)
    return True


def reset_and_seed(conn, today=None):
    """Explicit reset: deletes ALL records, then loads the sample dataset."""
    conn.executescript(
        "DELETE FROM complaint_history; DELETE FROM complaints; "
        "DELETE FROM maintenance_records; DELETE FROM assets;"
    )
    conn.commit()
    load_sample(conn, today)
