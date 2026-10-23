"""Local planner: turns a request into a tool plan using explicit rules. No model and no key needed.

A plan is a dict:
  {"type": "tool", "tool": name, "args": {...}, "notes": [...]}   run a tool
  {"type": "ask", "question": "..."}                              need one more detail
"""
import re
from datetime import date

from agent.tools import suggest_triage

ASSET_RE = re.compile(r"\b([A-Za-z]{2}-\d{3})\b")
COMPLAINT_ID_RE = re.compile(r"complaint\s*#?\s*(\d+)", re.I)
COST_RE = re.compile(r"rm\s*([\d,]+(?:\.\d{1,2})?)", re.I)
LOCATION_RE = re.compile(
    r"\b(?:at|on|near)\s+(.+?)(?=[,.;]|\s+(?:urgent|urgently|critical|high|medium|low)\b|$)", re.I
)
ASSIGN_RE = re.compile(r"assign(?:ed)?\s+to\s+([A-Za-z][A-Za-z ]*?)(?=[,.;]|$)", re.I)
STATUS_RE = re.compile(r"\b(in progress|under review|resolved?|closed?|open)\b", re.I)
URGENCY_RE = re.compile(r"\b(critical|high|medium|low)\b", re.I)
MAINT_RE = re.compile(r"\b(repair|inspect|clean|replac|servic|greas|maintenan|fix)", re.I)
RECORD_WORDS_RE = re.compile(r"\b(record|log|add|done|completed)\b", re.I)
COMPLAINT_CREATE_RE = re.compile(r"\b(log|report|file|submit|new)\b[^.]*\bcomplaint\b", re.I)

STATUS_WORDS = {
    "in progress": "In progress", "under review": "Under review",
    "resolved": "Resolved", "resolve": "Resolved",
    "closed": "Closed", "close": "Closed", "open": "Open",
}
# Checked in order: the first matching category wins.
RECORD_CATEGORY_RULES = [
    (r"repair|fix|burst|leak", "Repair"),
    (r"inspect", "Inspection"),
    (r"clean", "Cleaning"),
    (r"replac", "Replacement"),
    (r"servic|greas|preventive|maintenan", "Preventive maintenance"),
]


class LocalPlanner:
    def __init__(self, today=None):
        self.today = today or date.today()

    def plan(self, text):
        lowered = text.lower()

        # Complaint updates need a complaint number plus a change word.
        complaint_id = COMPLAINT_ID_RE.search(text)
        if complaint_id and (STATUS_RE.search(text) or URGENCY_RE.search(text) or ASSIGN_RE.search(text)):
            return self._update_plan(text, int(complaint_id.group(1)))

        if COMPLAINT_CREATE_RE.search(text) or lowered.startswith("complaint"):
            return self._complaint_plan(text)

        code = ASSET_RE.search(text)
        if code and MAINT_RE.search(text) and RECORD_WORDS_RE.search(text):
            return self._record_plan(text, code.group(1).upper())
        if code:
            return self._tool("asset_details", {"asset_code": code.group(1).upper()})

        if re.search(r"\boverdue\b", lowered):
            return self._tool("overdue_inspections", {})
        if re.search(r"\b(briefing|dashboard|overview|summary)\b", lowered):
            return self._tool("dashboard_summary", {})
        if re.search(r"\b(triage|suggest category|which category|what category)\b", lowered):
            return self._tool("triage_suggestion", {"text": text})
        search = re.match(r"\s*(?:search|find)\s+(.+)", text, re.I)
        if search:
            return self._tool("search_assets", {"query": search.group(1).strip()})

        return self._tool("township_question", {"question": text})

    @staticmethod
    def _tool(name, args, notes=None):
        return {"type": "tool", "tool": name, "args": args, "notes": notes or []}

    def _complaint_plan(self, text):
        location = LOCATION_RE.search(text)
        if not location:
            return {"type": "ask",
                    "question": "Where is the problem? For example: 'log complaint: water leaking at Block C'."}
        category, urgency, reasons = suggest_triage(text)
        body = re.sub(
            r"^\s*(?:(?:log|report|file|submit|new)\b.*?\bcomplaint|complaint)\s*:?\s*", "", text, flags=re.I
        )
        title = re.split(r"(?i)[.,;:]| at | on | near ", body, maxsplit=1)[0].strip()[:80]
        args = {
            "title": title or "Resident complaint",
            "description": text,
            "location": location.group(1).strip(),
            "category": category,
            "urgency": urgency,
        }
        notes = [f"Suggested category {category} and urgency {urgency}. " + " ".join(reasons)
                 + " Check these before confirming."]
        return self._tool("create_complaint", args, notes)

    def _record_plan(self, text, code):
        category = next((c for pattern, c in RECORD_CATEGORY_RULES if re.search(pattern, text, re.I)), "Repair")
        cost_match = COST_RE.search(text)
        cost = float(cost_match.group(1).replace(",", "")) if cost_match else 0.0
        notes = [] if cost_match else ["No cost found in the request, so RM 0.00 is proposed."]

        after_code = re.search(r"[A-Za-z]{2}-\d{3}\s*[:\-]?\s*(.*)", text)
        description = after_code.group(1) if after_code else text
        description = re.sub(r",?\s*(?:cost\s*)?RM\s*[\d,.]+", "", description, flags=re.I).strip(" ,.") or text

        args = {
            "asset_code": code,
            "record_date": self.today.isoformat(),
            "category": category,
            "description": description,
            "cost_rm": cost,
            "status": "Completed",
        }
        return self._tool("add_maintenance_record", args, notes)

    def _update_plan(self, text, complaint_id):
        args = {"complaint_id": complaint_id, "note": text}
        status = STATUS_RE.search(text)
        if status:
            args["status"] = STATUS_WORDS[status.group(1).lower()]
        urgency = URGENCY_RE.search(text)
        if urgency:
            args["urgency"] = urgency.group(1).capitalize()
        assignee = ASSIGN_RE.search(text)
        if assignee:
            args["assigned_to"] = assignee.group(1).strip()
        if not any(k in args for k in ("status", "urgency", "assigned_to")):
            return {"type": "ask",
                    "question": f"What should change on complaint #{complaint_id}: status, urgency or assignee?"}
        return self._tool("update_complaint", args)
