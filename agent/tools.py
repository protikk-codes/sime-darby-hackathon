"""Agent tool registry.

Read tools run immediately. Write tools never change data directly: they return
a preview, and the change is saved only when a person confirms it
(see agent.confirm). There is deliberately no delete tool.
"""
import re
from dataclasses import dataclass
from typing import Callable, Optional

import config as cfg
from intelligence.analytics import dashboard_metrics
from intelligence.assistant import TownshipAssistant
from intelligence.risk import assess_all, assess_asset
from services import assets as asset_svc
from services import complaints as comp_svc
from services import maintenance as maint_svc
from services.errors import ValidationError

TYPE_MAP = {"string": str, "integer": int, "number": float}


@dataclass
class ToolSpec:
    name: str
    description: str
    params: dict  # name -> (json_type, description, required)
    writes: bool = False
    run: Optional[Callable] = None      # read tools: run(conn, args, today) -> {"text", "sources"}
    preview: Optional[Callable] = None  # write tools: preview(conn, args) -> str

    def schema(self):
        properties = {n: {"type": t, "description": d} for n, (t, d, _r) in self.params.items()}
        required = [n for n, (_t, _d, r) in self.params.items() if r]
        return {"type": "object", "properties": properties, "required": required}

    def check_args(self, args):
        """Keep only known fields, convert types, and raise ValueError for missing or bad values."""
        clean = {}
        for name, (json_type, _desc, required) in self.params.items():
            value = args.get(name)
            if value is None or value == "":
                if required:
                    raise ValueError(f"Missing required field: {name}.")
                continue
            try:
                converted = TYPE_MAP[json_type](value)
            except (TypeError, ValueError):
                raise ValueError(f"Field {name} must be a {json_type}.")
            clean[name] = converted.strip() if isinstance(converted, str) else converted
        return clean


# ----- urgency and category suggestions (explainable keyword rules) -----

CATEGORY_KEYWORDS = {
    "Water pipeline": ["water", "pipe", "leak", "pressure", "meter", "tap"],
    "Drainage": ["drain", "flood", "overflow", "blocked", "culvert", "sewer", "pool"],
    "Road": ["road", "pothole", "asphalt", "crack"],
    "Streetlight": ["streetlight", "lamp", "light"],
    "Pump": ["pump", "motor", "impeller", "noise"],
    "Other": ["generator", "hall"],
}
CRITICAL_WORDS = ("burst", "collapse", "sewage", "spark", "electric", "emergency", "danger", "flood")
HIGH_WORDS = ("urgent", "overflow", "blocked", "no water", "leak", "pothole")
LOW_WORDS = ("minor", "small", "flicker", "cosmetic")


def _found(text, words):
    """Whole-word-start matching, so 'light' does not match 'highlight'."""
    return [w for w in words if re.search(r"\b" + re.escape(w), text)]


def suggest_triage(text):
    """Return (category, urgency, reasons). A person must still approve the result."""
    lowered = (text or "").lower()
    matches = {cat: _found(lowered, words) for cat, words in CATEGORY_KEYWORDS.items()}
    best = max(matches, key=lambda c: len(matches[c]))
    if matches[best]:
        category, category_hits = best, matches[best]
    else:
        category, category_hits = "Other", []

    critical = _found(lowered, CRITICAL_WORDS)
    high = _found(lowered, HIGH_WORDS)
    low = _found(lowered, LOW_WORDS)
    if critical:
        urgency, signals = "Critical", critical
    elif high:
        urgency, signals = "High", high
    elif low:
        urgency, signals = "Low", low
    else:
        urgency, signals = "Medium", []

    reasons = [
        f"Category keywords found: {', '.join(category_hits)}." if category_hits
        else "No category keywords found, so Other is suggested.",
        f"Urgency signals found: {', '.join(signals)}." if signals
        else "No urgency signals found, so Medium is suggested.",
    ]
    return category, urgency, reasons


# ----- read tools -----

def _search_assets(conn, args, today):
    rows = asset_svc.list_assets(conn, search=args.get("query", ""))[:10]
    if not rows:
        return {"text": "No assets match that search.", "sources": []}
    lines = [f"- {r['asset_code']} {r['name']} ({r['location']}, condition {r['condition']})" for r in rows]
    return {"text": f"Matching assets ({len(rows)}):\n" + "\n".join(lines),
            "sources": [r["asset_code"] for r in rows]}


def _asset_details(conn, args, today):
    code = args["asset_code"]
    asset = asset_svc.get_asset(conn, code)
    records = maint_svc.list_records(conn, code)
    risk = assess_asset(asset, records, today)
    lines = [
        f"{asset['asset_code']} {asset['name']}",
        f"Type: {asset['asset_type']}. Location: {asset['location']}. Condition: {asset['condition']}.",
        f"Installed {asset['install_year']}, lifespan {asset['lifespan_years']} years "
        f"({risk.lifespan_used_pct}% used).",
        f"Next inspection {risk.next_due}" + (" (OVERDUE)." if risk.overdue else "."),
        f"Risk {risk.score}/100 ({risk.level}). Reasons: " + " ".join(risk.reasons),
        "Recent records:",
    ]
    recent = records[-5:]
    if recent:
        lines += [f"- {r['record_date']} {r['category']}: {r['description']} (RM {r['cost_rm']:,.2f})"
                  for r in recent]
    else:
        lines.append("- none")
    return {"text": "\n".join(lines), "sources": [asset["asset_code"]]}


def _overdue(conn, args, today):
    items = [r for r in assess_all(conn, today) if r.overdue]
    if not items:
        return {"text": "No inspections are overdue.", "sources": []}
    lines = [f"- {r.asset_code} {r.name}: due {r.next_due}, {-r.days_to_due} days overdue" for r in items]
    return {"text": f"Overdue inspections ({len(items)}):\n" + "\n".join(lines),
            "sources": [r.asset_code for r in items]}


def _risk_ranking(conn, args, today):
    limit = int(args.get("limit", 5))
    items = assess_all(conn, today)[:limit]
    lines = [f"{i}. {r.asset_code} {r.name}: {r.score}/100 ({r.level}). {' '.join(r.reasons)}"
             for i, r in enumerate(items, 1)]
    return {"text": "\n".join(lines) or "No assets to rank.", "sources": [r.asset_code for r in items]}


def _spending(conn, args, today):
    asset_type = args.get("asset_type", "")
    total = maint_svc.total_cost(conn, asset_type=asset_type)
    label = asset_type or "all assets"
    return {"text": f"Recorded spending on {label}: RM {total:,.2f}.", "sources": []}


def _complaints(conn, args, today):
    rows = comp_svc.list_complaints(conn, status=args.get("status", ""), urgency=args.get("urgency", ""))
    if not rows:
        return {"text": "No complaints match.", "sources": []}
    lines = [f"- #{r['id']} {r['title']} ({r['location']}): {r['status']}, urgency {r['urgency']}" for r in rows]
    return {"text": f"Complaints ({len(rows)}):\n" + "\n".join(lines),
            "sources": [f"Complaint #{r['id']}" for r in rows]}


def _dashboard(conn, args, today):
    m = dashboard_metrics(conn, today)
    risk_line = ", ".join(f"{k} {v}" for k, v in m["by_risk"].items())
    text = (
        f"Assets: {m['total_assets']}\n"
        f"Risk levels: {risk_line}\n"
        f"Overdue inspections: {len(m['overdue'])}\n"
        f"Due within 30 days: {len(m['upcoming'])}\n"
        f"Open complaints: {m['open_complaints']} ({m['urgent_open_complaints']} urgent)\n"
        f"Recorded spend: RM {m['total_spend']:,.2f}\n"
        f"Assets with repeated repairs: {len(m['recurring'])}"
    )
    return {"text": text, "sources": []}


def _question(conn, args, today):
    result = TownshipAssistant(conn, today=today).ask(args["question"])
    return {"text": result["answer"], "sources": result["sources"]}


def _triage_tool(conn, args, today):
    category, urgency, reasons = suggest_triage(args["text"])
    return {"text": f"Suggested category: {category}. Suggested urgency: {urgency}. " + " ".join(reasons),
            "sources": []}


# ----- write previews and execution (only reached through confirmation) -----

def _preview_complaint(conn, args):
    if args.get("asset_code"):
        asset_svc.get_asset(conn, args["asset_code"])  # raises NotFoundError if unknown
    return (f"New complaint: '{args['title']}' at {args['location']}. "
            f"Category {args['category']}, urgency {args['urgency']}. "
            f"Details: {args.get('description') or '-'}")


def _preview_record(conn, args):
    asset_svc.get_asset(conn, args["asset_code"])  # raises NotFoundError if unknown
    cost = float(args.get("cost_rm") or 0)
    return (f"New {args['category']} record for {args['asset_code']} on {args['record_date']}: "
            f"{args['description']}. Cost RM {cost:,.2f}, status {args['status']}.")


def _preview_update(conn, args):
    c = comp_svc.get_complaint(conn, args["complaint_id"])
    changes = [f"{k} '{c[k] or '-'}' -> '{args[k]}'" for k in ("status", "urgency", "assigned_to") if args.get(k)]
    if not changes:
        raise ValidationError("Nothing to change on this complaint.")
    return f"Complaint #{c['id']} '{c['title']}': " + "; ".join(changes) + "."


def execute_write(conn, name, args):
    """Save a confirmed change. Called only from ConfirmationQueue.confirm()."""
    if name == "create_complaint":
        new_id = comp_svc.create_complaint(conn, args)
        return f"Complaint #{new_id} logged."
    if name == "add_maintenance_record":
        new_id = maint_svc.add_record(conn, args)
        return f"Maintenance record #{new_id} saved for {args['asset_code']}."
    if name == "update_complaint":
        changes = {k: args[k] for k in ("status", "urgency", "assigned_to") if args.get(k)}
        if not changes:
            raise ValidationError("Nothing to change on this complaint.")
        comp_svc.update_complaint(conn, args["complaint_id"], changes, args.get("note", ""))
        summary = ", ".join(f"{k} = {v}" for k, v in changes.items())
        return f"Complaint #{args['complaint_id']} updated: {summary}."
    raise ValidationError(f"Unknown write tool: {name}.")


# ----- registry -----

_CATEGORY_CHOICES = "One of: " + ", ".join(cfg.ASSET_TYPES)
_RECORD_CATEGORY_CHOICES = "One of: " + ", ".join(cfg.RECORD_CATEGORIES)

READ_TOOLS = [
    ToolSpec(name="search_assets", description="Search assets by code, name or location.",
             params={"query": ("string", "Text to search for", True)}, run=_search_assets),
    ToolSpec(name="asset_details",
             description="Show one asset with its risk score, reasons and recent maintenance records.",
             params={"asset_code": ("string", "Asset code such as WP-001", True)}, run=_asset_details),
    ToolSpec(name="overdue_inspections", description="List assets whose inspection is overdue.",
             params={}, run=_overdue),
    ToolSpec(name="risk_ranking", description="List the highest-risk assets with reasons.",
             params={"limit": ("integer", "How many to list (default 5)", False)}, run=_risk_ranking),
    ToolSpec(name="spending_summary", description="Total recorded maintenance spend, optionally for one asset type.",
             params={"asset_type": ("string", "Asset type such as Drainage", False)}, run=_spending),
    ToolSpec(name="complaints_list", description="List complaints, optionally filtered by status or urgency.",
             params={"status": ("string", "Status to filter by", False),
                     "urgency": ("string", "Urgency to filter by", False)}, run=_complaints),
    ToolSpec(name="dashboard_summary", description="Summary of the management dashboard figures.",
             params={}, run=_dashboard),
    ToolSpec(name="township_question",
             description="Answer a question about the stored records: risk, spending, repairs, complaints or priorities.",
             params={"question": ("string", "The question, in the user's words", True)}, run=_question),
    ToolSpec(name="triage_suggestion",
             description="Suggest a category and urgency for a complaint description, with reasons.",
             params={"text": ("string", "Complaint text", True)}, run=_triage_tool),
]

WRITE_TOOLS = [
    ToolSpec(name="create_complaint", writes=True,
             description="Propose logging a new complaint. A person must confirm before it is saved.",
             params={
                 "title": ("string", "Short title", True),
                 "description": ("string", "Full description", False),
                 "location": ("string", "Where the problem is", True),
                 "category": ("string", _CATEGORY_CHOICES, True),
                 "urgency": ("string", "One of: Low, Medium, High, Critical", True),
                 "asset_code": ("string", "Linked asset code, optional", False),
             }, preview=_preview_complaint),
    ToolSpec(name="add_maintenance_record", writes=True,
             description="Propose adding a maintenance or inspection record. A person must confirm before it is saved.",
             params={
                 "asset_code": ("string", "Asset code such as WP-002", True),
                 "record_date": ("string", "Date in YYYY-MM-DD format", True),
                 "category": ("string", _RECORD_CATEGORY_CHOICES, True),
                 "description": ("string", "What was done or found", True),
                 "cost_rm": ("number", "Cost in RM, 0 if unknown", False),
                 "status": ("string", "One of: Completed, Scheduled, Deferred", True),
             }, preview=_preview_record),
    ToolSpec(name="update_complaint", writes=True,
             description="Propose changing a complaint's status, urgency or assignee. A person must confirm.",
             params={
                 "complaint_id": ("integer", "Complaint ID number", True),
                 "status": ("string", "New status", False),
                 "urgency": ("string", "New urgency", False),
                 "assigned_to": ("string", "Assignee name", False),
                 "note": ("string", "Reason for the change", False),
             }, preview=_preview_update),
]

TOOLS = {tool.name: tool for tool in READ_TOOLS + WRITE_TOOLS}
