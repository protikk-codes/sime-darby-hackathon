"""Township intelligence assistant.

Answers come from a deterministic query engine that reads the real database.
An optional language model can rephrase those grounded answers, but it is never
asked to invent facts. With no provider connected, the deterministic answer is
returned unchanged, and the result says which engine produced it.
"""
from datetime import date
from typing import Protocol

import config as cfg
from intelligence.analytics import dashboard_metrics
from intelligence.risk import assess_all
from services.complaints import days_open, is_open, list_complaints
from services.maintenance import list_records


class LanguageModelProvider(Protocol):
    """Interface for a future AI provider. Implement rephrase() and set name."""
    name: str

    def rephrase(self, question: str, grounded_answer: str) -> str: ...


class NoLanguageModel:
    name = "Deterministic query engine (no language model connected)"

    def rephrase(self, question, grounded_answer):
        return grounded_answer


FALLBACK = (
    "I can only answer questions about the stored township records. Try asking: "
    "'Which assets need maintenance soon?', 'Which assets have repeated repairs?', "
    "'What are the highest-risk assets and why?', 'How much has been spent on drainage?', "
    "'Which complaints have remained open the longest?', or "
    "'What should management prioritise this month?'"
)

SPEND_KEYWORDS = {
    "water": "Water pipeline", "pipe": "Water pipeline",
    "drain": "Drainage", "road": "Road",
    "streetlight": "Streetlight", "light": "Streetlight",
    "pump": "Pump", "generator": "Other",
}


class TownshipAssistant:
    def __init__(self, conn, today=None, provider=None):
        self.conn = conn
        self.today = today or date.today()
        self.provider = provider or NoLanguageModel()

    def ask(self, question):
        text = (question or "").strip()
        q = text.lower()
        if not q:
            return self._result("Please type a question about the township records.", [])

        routes = [
            (("priorit", "this month", "focus on"), self._priorities),
            (("repeat", "recurring", "again"), self._repeated),
            (("soon", "due", "overdue", "inspection"), self._due),
            (("risk", "highest", "worst", "critical"), self._risk),
            (("complaint",), self._complaints),
            (("spend", "spent", "cost", "how much"), self._spend),
        ]
        for keywords, handler in routes:
            if any(k in q for k in keywords):
                grounded, sources = handler(q)
                return self._result(grounded, sources)
        return self._result(FALLBACK, [])

    def _result(self, grounded, sources):
        try:
            answer = self.provider.rephrase("", grounded)
        except Exception:  # a broken provider must never break the grounded answer
            answer = grounded
        return {"answer": answer, "sources": sources, "engine": self.provider.name}

    # ----- handlers: each returns (grounded_text, list_of_sources) -----

    def _due(self, q):
        risks = assess_all(self.conn, self.today)
        overdue = sorted((r for r in risks if r.overdue), key=lambda r: r.days_to_due)
        upcoming = sorted(
            (r for r in risks if not r.overdue and r.days_to_due <= cfg.UPCOMING_WINDOW_DAYS),
            key=lambda r: r.days_to_due,
        )
        if not overdue and not upcoming:
            return "No inspections are overdue or due within the next 30 days.", []
        lines, sources = [], []
        if overdue:
            lines.append(f"Overdue inspections ({len(overdue)}):")
            for r in overdue:
                lines.append(f"- {r.asset_code} {r.name}: due {r.next_due}, overdue by {-r.days_to_due} days.")
                sources.append(f"{r.asset_code} (due {r.next_due})")
        if upcoming:
            lines.append(f"Due within {cfg.UPCOMING_WINDOW_DAYS} days ({len(upcoming)}):")
            for r in upcoming:
                lines.append(f"- {r.asset_code} {r.name}: due {r.next_due} (in {r.days_to_due} days).")
                sources.append(f"{r.asset_code} (due {r.next_due})")
        return "\n".join(lines), sources

    def _repeated(self, q):
        recurring = [r for r in assess_all(self.conn, self.today) if r.repair_count >= cfg.REPEAT_MIN_REPAIRS]
        if not recurring:
            return f"No asset has {cfg.REPEAT_MIN_REPAIRS} or more repairs in the last {cfg.REPEAT_WINDOW_DAYS} days.", []
        lines, sources = [f"Assets with repeated repairs in the last {cfg.REPEAT_WINDOW_DAYS} days:"], []
        for r in recurring:
            lines.append(f"- {r.asset_code} {r.name}: {r.repair_count} repairs on {', '.join(r.repair_dates)}.")
            lines.append(f"  Suggested action: {r.actions[-1] if r.actions else 'Investigate root cause.'}")
            sources.append(f"{r.asset_code} repairs {', '.join(r.repair_dates)}")
        return "\n".join(lines), sources

    def _risk(self, q):
        risks = assess_all(self.conn, self.today)[:5]
        if not risks:
            return "There are no assets in the register to assess.", []
        lines, sources = ["Highest-risk assets (rule-based score out of 100):"], []
        for i, r in enumerate(risks, 1):
            lines.append(f"{i}. {r.asset_code} {r.name}: {r.score}/100 ({r.level}). Reasons: {' '.join(r.reasons)}")
            sources.append(f"{r.asset_code} score {r.score}")
        lines.append("Scores are transparent rules, not trained predictions. Final decisions rest with management.")
        return "\n".join(lines), sources

    def _complaints(self, q):
        open_items = sorted(
            (c for c in list_complaints(self.conn) if is_open(c)),
            key=lambda c: c["date_reported"],
        )
        if not open_items:
            return "There are no open complaints in the records.", []
        lines, sources = [f"Open complaints, longest open first ({len(open_items)} open):"], []
        for c in open_items[:8]:
            lines.append(
                f"- #{c['id']} {c['title']} ({c['location']}): reported {c['date_reported']}, "
                f"{days_open(c, self.today)} days open, urgency {c['urgency']}, status {c['status']}."
            )
            sources.append(f"Complaint #{c['id']} reported {c['date_reported']}")
        return "\n".join(lines), sources

    def _spend(self, q):
        asset_type = next((t for k, t in SPEND_KEYWORDS.items() if k in q), None)
        records = list_records(self.conn)
        if asset_type:
            records = [r for r in records if r["asset_type"] == asset_type]
            label = f"{asset_type} assets"
        else:
            label = "all assets"
        total = sum(float(r["cost_rm"]) for r in records)
        if not records:
            return f"No maintenance records are stored for {label}.", []
        paid = [r for r in records if r["cost_rm"] > 0]
        sources = [f"{r['asset_code']} {r['record_date']} RM {r['cost_rm']:,.2f}" for r in paid[:8]]
        text = (
            f"Recorded spending on {label}: RM {total:,.2f} across {len(records)} maintenance records "
            f"({len(paid)} with a cost)."
        )
        return text, sources

    def _priorities(self, q):
        metrics = dashboard_metrics(self.conn, self.today)
        lines, sources = ["Suggested priorities for management this month (for human review):"], []
        if metrics["overdue"]:
            codes = ", ".join(r.asset_code for r in metrics["overdue"])
            lines.append(f"1. Clear overdue inspections ({len(metrics['overdue'])}): {codes}.")
            sources += [r.asset_code for r in metrics["overdue"]]
        top = [r for r in metrics["risks"] if r.level in ("Critical", "High")][:3]
        if top:
            lines.append("2. Review the highest-risk assets: " + "; ".join(
                f"{r.asset_code} ({r.score}/100)" for r in top) + ".")
            sources += [f"{r.asset_code} score {r.score}" for r in top]
        urgent = [c for c in list_complaints(self.conn) if is_open(c) and c["urgency"] in ("High", "Critical")]
        if urgent:
            lines.append(f"3. Triage urgent open complaints ({len(urgent)}): " + "; ".join(
                f"#{c['id']} {c['title']} ({c['urgency']})" for c in urgent[:5]) + ".")
            sources += [f"Complaint #{c['id']}" for c in urgent[:5]]
        if metrics["recurring"]:
            lines.append("4. Investigate recurring repairs: " + ", ".join(
                r.asset_code for r in metrics["recurring"]) + ".")
        if len(lines) == 1:
            return "No outstanding priorities were found in the current records.", []
        return "\n".join(lines), sources
