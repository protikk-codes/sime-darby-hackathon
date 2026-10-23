"""Human confirmation for agent writes.

A proposal is saved only when confirm() is called, and the UI calls it only
after a person presses Confirm. Every proposal and decision is written to the
agent_audit table.
"""
import json
import uuid
from dataclasses import dataclass, field

from agent.tools import execute_write
from services.base import execute
from services.errors import TownshipError


@dataclass
class Proposal:
    id: int                 # short number shown in the session
    ref: str                # unique reference written to the audit log
    tool: str
    args: dict
    preview: str
    status: str = "pending"  # pending, done, failed or cancelled
    result: str = ""


class ConfirmationQueue:
    def __init__(self):
        self._items = {}
        self._next_id = 1

    def pending(self):
        return [p for p in self._items.values() if p.status == "pending"]

    def propose(self, conn, tool, args, preview):
        proposal = Proposal(id=self._next_id, ref=uuid.uuid4().hex, tool=tool, args=args, preview=preview)
        self._next_id += 1
        self._items[proposal.id] = proposal
        _audit(conn, proposal, "proposed", "")
        return proposal

    def confirm(self, conn, proposal_id):
        proposal = self._require_pending(proposal_id)
        try:
            proposal.result = execute_write(conn, proposal.tool, proposal.args)
            proposal.status = "done"
        except TownshipError as exc:
            proposal.result = str(exc)
            proposal.status = "failed"
        _audit(conn, proposal, proposal.status, proposal.result)
        return proposal

    def cancel(self, conn, proposal_id):
        proposal = self._require_pending(proposal_id)
        proposal.status = "cancelled"
        proposal.result = "Cancelled by the user."
        _audit(conn, proposal, "cancelled", proposal.result)
        return proposal

    def _require_pending(self, proposal_id):
        proposal = self._items.get(proposal_id)
        if proposal is None:
            raise TownshipError(f"No proposal #{proposal_id} in this session.")
        if proposal.status != "pending":
            raise TownshipError(f"Proposal #{proposal_id} is already {proposal.status}.")
        return proposal


def _audit(conn, proposal, status, result):
    execute(
        conn,
        "INSERT INTO agent_audit (proposal_ref, tool, args_json, status, result) VALUES (?, ?, ?, ?, ?)",
        (proposal.ref, proposal.tool, json.dumps(proposal.args, default=str), status, result),
    )
