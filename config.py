"""Central configuration. Risk thresholds and choice lists live here, not in code."""
import os
from pathlib import Path

DB_PATH = Path(os.environ.get("TOWNSHIPOS_DB", "townshipos.db"))

ASSET_TYPES = ("Water pipeline", "Drainage", "Road", "Streetlight", "Pump", "Other")
CONDITIONS = ("Good", "Fair", "Poor")
URGENCIES = ("Low", "Medium", "High", "Critical")
COMPLAINT_STATUSES = ("Open", "Under review", "Assigned", "In progress", "Resolved", "Closed")
OPEN_STATUSES = ("Open", "Under review", "Assigned", "In progress")
RECORD_CATEGORIES = ("Inspection", "Repair", "Preventive maintenance", "Replacement", "Cleaning")
RECORD_STATUSES = ("Scheduled", "Completed", "Deferred")

# Risk engine. Points per factor add up to at most 100.
RISK_WEIGHTS = {
    "age": 40,                                   # share of lifespan used, capped at 150%
    "condition": {"Good": 0, "Fair": 10, "Poor": 25},
    "overdue": 15,                               # inspection past its due date
    "repeat": 15,                                # repeated repairs inside the window
}
# Score thresholds, checked from highest to lowest. Anything below the lowest is "Low".
RISK_LEVEL_THRESHOLDS = (("Critical", 75), ("High", 50), ("Medium", 25))
AGE_CONCERN_RATIO = 0.8        # age reason is shown from 80% of lifespan
UPCOMING_WINDOW_DAYS = 30      # inspections due within this many days are "upcoming"
REPEAT_WINDOW_DAYS = 365       # look-back window for repeated repairs
REPEAT_MIN_REPAIRS = 2         # this many repairs in the window counts as recurring

# Impact estimates. These are ASSUMPTIONS for planning, not measured results.
# Replace them with figures from the pilot once real data exists.
IMPACT_ASSUMPTIONS = {
    "avoidable_repeat_repair_share": 0.30,   # share of repeat-repair spend an earlier inspection could avoid
    "staff_cost_per_complaint_rm": 40.0,     # staff time to handle one complaint by hand
}
MIN_STAFF_PIN_LENGTH = 6
