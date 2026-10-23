"""TownshipAgent: the single entry point the UI uses.

Flow for each request:
  1. If a model provider is configured, ask it for a plan.
  2. If that is not configured, or fails, use the local planner.
  3. Residents may only use RESIDENT_TOOLS. Staff may use every tool.
  4. Read tools run immediately. Write tools become proposals that wait for Confirm.
"""
from dataclasses import dataclass, field
from datetime import date

from agent.confirm import ConfirmationQueue
from agent.planner import LocalPlanner
from agent.provider import ProviderError, select_provider_from_env
from agent.tools import TOOLS
from services.errors import TownshipError

HELP = (
    "I can log a complaint ('log complaint: water leaking at Block C, urgent'), record maintenance "
    "('record repair for WP-002: valve replaced, cost RM 350'), update a complaint ('mark complaint 3 resolved'), "
    "show an asset ('show WP-001'), list overdue inspections, give a dashboard summary, "
    "or answer questions about the records."
)
RESIDENT_TOOLS = ("township_question",)
RESIDENT_REFUSAL = ("To report a problem, use 'Report a problem' on the home page. "
                    "Here I can answer general questions about township services.")


@dataclass
class AgentReply:
    mode: str                                    # "local" or "model"
    message: str
    sources: list = field(default_factory=list)
    pending: list = field(default_factory=list)  # Proposal objects awaiting Confirm
    notice: str = ""


def _join_text(*parts):
    return "\n".join(p for p in parts if p)


def _restrict_for_residents(plan, text):
    """Residents can only ask questions. Anything else is answered as a question or refused."""
    if plan.get("type") != "tool" or plan.get("tool") in RESIDENT_TOOLS:
        return plan
    spec = TOOLS.get(plan.get("tool", ""))
    if spec is not None and spec.writes:
        return {"type": "answer", "text": RESIDENT_REFUSAL}
    return {"type": "tool", "tool": "township_question", "args": {"question": text}}


class TownshipAgent:
    def __init__(self, conn, today=None, provider=None, use_env=True, queue=None):
        self.conn = conn
        self.today = today or date.today()
        if provider is None and use_env:
            provider = select_provider_from_env()
        self.provider = provider
        self.planner = LocalPlanner(self.today)
        self.queue = queue or ConfirmationQueue()

    def status_text(self):
        if self.provider is not None:
            return f"Mode: {self.provider.name}. The local planner is used if the model is unavailable."
        return ("Mode: local planner (no model key set). It works fully offline. To add a free Gemini model, set "
                "TOWNSHIPOS_AGENT_PROVIDER=gemini and GEMINI_API_KEY.")

    def handle(self, request, residents=False):
        text = (request or "").strip()
        if not text:
            return AgentReply(mode="local", message=HELP)

        tools = [t for t in TOOLS.values() if not residents or t.name in RESIDENT_TOOLS]
        mode, notice, plan = "local", "", None
        if self.provider is not None:
            try:
                plan = self.provider.plan(text, tools)
                mode = "model"
            except ProviderError as exc:
                notice = f"Model unavailable ({exc}). Answered with the local planner."
        if plan is None:
            plan = self.planner.plan(text)
        if residents:
            plan = _restrict_for_residents(plan, text)
        return self._run(plan, mode, notice)

    def _run(self, plan, mode, notice):
        kind = plan.get("type")
        if kind == "answer":
            return AgentReply(mode=mode, message=plan.get("text", ""), notice=notice)
        if kind == "ask":
            return AgentReply(mode=mode, message=plan.get("question", ""), notice=notice)
        if kind != "tool":
            return AgentReply(mode=mode, message=HELP, notice=notice)

        name = plan.get("tool", "")
        spec = TOOLS.get(name)
        if spec is None:
            return AgentReply(mode=mode, message=f"The agent asked for an unknown tool '{name}', so nothing was done.",
                              notice=notice)
        notes = _join_text(*plan.get("notes", []))
        try:
            args = spec.check_args(plan.get("args") or {})
            if spec.writes:
                preview = spec.preview(self.conn, args)
                proposal = self.queue.propose(self.conn, name, args, preview)
                message = _join_text("Proposed change. Nothing is saved until you press Confirm.", notes)
                return AgentReply(mode=mode, message=message, pending=[proposal], notice=notice)
            result = spec.run(self.conn, args, self.today)
            return AgentReply(mode=mode, message=_join_text(result["text"], notes),
                              sources=result.get("sources", []), notice=notice)
        except (ValueError, TownshipError) as exc:
            return AgentReply(mode=mode, message=f"Could not do that: {exc}", notice=notice)

    def confirm(self, proposal_id):
        return self.queue.confirm(self.conn, proposal_id)

    def cancel(self, proposal_id):
        return self.queue.cancel(self.conn, proposal_id)
