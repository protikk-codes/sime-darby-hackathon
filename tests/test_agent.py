import pytest

from agent.core import TownshipAgent
from agent.planner import LocalPlanner
from agent.provider import AnthropicProvider, ProviderError
from agent.tools import TOOLS, suggest_triage
from services import complaints as comp_svc
from services import maintenance as maint_svc
from services.errors import TownshipError


@pytest.fixture
def agent(seeded, today):
    # use_env=False keeps tests independent of any API key on the machine
    return TownshipAgent(seeded, today=today, use_env=False)


def audit_rows(conn):
    return conn.execute("SELECT * FROM agent_audit").fetchall()


# ----- safety rules -----

def test_no_delete_tool_exists():
    assert not any("delete" in name or "remove" in name for name in TOOLS)


def test_write_tools_are_flagged_as_writes():
    for name in ("create_complaint", "add_maintenance_record", "update_complaint"):
        assert TOOLS[name].writes is True
    for name, tool in TOOLS.items():
        if not tool.writes:
            assert tool.run is not None, f"read tool {name} needs a run function"


def test_complaint_is_not_saved_until_confirmed(agent, seeded):
    before = len(comp_svc.list_complaints(seeded))
    reply = agent.handle("Log complaint: water leaking at Block C, urgent")
    assert len(reply.pending) == 1
    assert reply.pending[0].status == "pending"
    assert len(comp_svc.list_complaints(seeded)) == before

    done = agent.confirm(reply.pending[0].id)
    assert done.status == "done"
    assert len(comp_svc.list_complaints(seeded)) == before + 1
    newest = comp_svc.list_complaints(seeded)[-1]
    assert newest["location"] == "Block C"
    assert newest["category"] == "Water pipeline"
    assert newest["urgency"] == "High"


def test_cancel_saves_nothing(agent, seeded):
    before = len(maint_svc.list_records(seeded))
    reply = agent.handle("Record repair for WP-002: valve replaced, cost RM 120")
    cancelled = agent.cancel(reply.pending[0].id)
    assert cancelled.status == "cancelled"
    assert len(maint_svc.list_records(seeded)) == before


def test_proposal_cannot_be_confirmed_twice(agent):
    reply = agent.handle("Mark complaint 1 resolved")
    agent.confirm(reply.pending[0].id)
    with pytest.raises(TownshipError, match="already"):
        agent.confirm(reply.pending[0].id)


def test_every_proposal_and_decision_is_audited(agent, seeded):
    reply = agent.handle("Mark complaint 1 resolved")
    agent.confirm(reply.pending[0].id)
    statuses = [row["status"] for row in audit_rows(seeded)]
    assert statuses == ["proposed", "done"]


# ----- planner routing -----

def test_read_request_runs_immediately(agent):
    reply = agent.handle("show WP-001")
    assert "WP-001" in reply.message
    assert reply.pending == []


def test_overdue_request_lists_real_assets(agent):
    reply = agent.handle("overdue inspections")
    for code in ("WP-001", "DR-001", "PM-002"):
        assert code in reply.message


def test_missing_location_asks_a_question(agent, seeded):
    reply = agent.handle("log complaint: lamp broken")
    assert reply.pending == []
    assert "Where is the problem" in reply.message
    assert len(comp_svc.list_complaints(seeded)) == 8


def test_record_proposal_saves_cost_and_category_after_confirm(agent, seeded):
    before = maint_svc.list_records(seeded, "WP-002")
    reply = agent.handle("Record repair for WP-002: burst valve replaced, cost RM 350")
    proposal = reply.pending[0]
    assert "WP-002" in proposal.preview and "Repair" in proposal.preview
    agent.confirm(proposal.id)
    after = maint_svc.list_records(seeded, "WP-002")
    assert len(after) == len(before) + 1
    assert after[-1]["cost_rm"] == 350.0
    assert after[-1]["category"] == "Repair"


def test_record_without_cost_states_it_in_notes(agent):
    reply = agent.handle("Record inspection for WP-002: pressure fine")
    assert "RM 0.00" in reply.message


def test_unknown_asset_is_refused_clearly(agent, seeded):
    reply = agent.handle("Record repair for ZZ-999: fixed, cost RM 5")
    assert reply.pending == []
    assert "No asset" in reply.message


def test_complaint_update_resolves_only_after_confirm(agent, seeded):
    reply = agent.handle("Mark complaint 1 resolved")
    assert comp_svc.get_complaint(seeded, 1)["status"] == "Open"
    agent.confirm(reply.pending[0].id)
    assert comp_svc.get_complaint(seeded, 1)["status"] == "Resolved"
    assert comp_svc.complaint_history(seeded, 1)[-1]["new_value"] == "Resolved"


def test_unanswerable_question_routes_to_assistant(agent):
    reply = agent.handle("What is the weather on Mars?")
    assert "only answer questions" in reply.message


def test_status_text_says_local_when_no_key(agent):
    assert "local planner" in agent.status_text()


# ----- triage suggestions -----

def test_triage_suggests_category_and_urgency_with_reasons():
    category, urgency, reasons = suggest_triage("Water leaking from the pipe, urgent")
    assert category == "Water pipeline"
    assert urgency == "High"
    assert reasons


def test_triage_flags_critical_words():
    _category, urgency, _reasons = suggest_triage("Burst pipe on main road")
    assert urgency == "Critical"


def test_triage_does_not_match_inside_words():
    category, _urgency, _reasons = suggest_triage("The highlight of the park")
    assert category != "Streetlight"


# ----- model provider (optional) -----

def test_provider_is_off_without_env(monkeypatch):
    monkeypatch.delenv("TOWNSHIPOS_AGENT_PROVIDER", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert AnthropicProvider.from_env() is None


def test_provider_needs_both_mode_and_key(monkeypatch):
    monkeypatch.setenv("TOWNSHIPOS_AGENT_PROVIDER", "model")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert AnthropicProvider.from_env() is None
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    provider = AnthropicProvider.from_env()
    assert provider is not None and provider.api_key == "test-key"


class FailingProvider:
    name = "failing"

    def plan(self, request, tools):
        raise ProviderError("HTTP 500")


def test_model_failure_falls_back_to_local(seeded, today):
    agent = TownshipAgent(seeded, today=today, provider=FailingProvider(), use_env=False)
    reply = agent.handle("show WP-001")
    assert reply.mode == "local"
    assert "Model unavailable" in reply.notice
    assert "WP-001" in reply.message


class StubProvider:
    name = "stub"

    def __init__(self, plan):
        self._plan = plan

    def plan(self, request, tools):
        return self._plan


def test_model_write_still_needs_confirmation(seeded, today):
    plan = {"type": "tool", "tool": "create_complaint",
            "args": {"title": "x", "location": "Park", "category": "Road", "urgency": "Low"}}
    agent = TownshipAgent(seeded, today=today, provider=StubProvider(plan), use_env=False)
    before = len(comp_svc.list_complaints(seeded))
    reply = agent.handle("anything")
    assert reply.mode == "model"
    assert len(reply.pending) == 1
    assert len(comp_svc.list_complaints(seeded)) == before


def test_model_cannot_call_unknown_tools(seeded, today):
    plan = {"type": "tool", "tool": "drop_all_tables", "args": {}}
    agent = TownshipAgent(seeded, today=today, provider=StubProvider(plan), use_env=False)
    reply = agent.handle("do something")
    assert "unknown tool" in reply.message


def test_model_bad_arguments_are_refused(seeded, today):
    plan = {"type": "tool", "tool": "asset_details", "args": {}}
    agent = TownshipAgent(seeded, today=today, provider=StubProvider(plan), use_env=False)
    reply = agent.handle("tell me about an asset")
    assert "Missing required field" in reply.message


def test_planner_plan_shape(seeded, today):
    plan = LocalPlanner(today).plan("show WP-001")
    assert plan["type"] == "tool" and plan["tool"] == "asset_details"


# ----- resident restrictions -----

def test_residents_cannot_log_or_change_records(agent, seeded):
    before = len(comp_svc.list_complaints(seeded))
    reply = agent.handle("Log complaint: lamp broken at Park", residents=True)
    assert reply.pending == []
    assert "Report a problem" in reply.message
    assert len(comp_svc.list_complaints(seeded)) == before


def test_residents_get_questions_answered(agent):
    reply = agent.handle("overdue inspections", residents=True)
    assert reply.pending == []
    assert "WP-001" in reply.message or "overdue" in reply.message.lower()


def test_resident_lookup_by_contact(seeded):
    seeded.execute("UPDATE complaints SET reporter_contact = 'Amy@Example.com' WHERE id = 1")
    seeded.commit()
    found = comp_svc.list_complaints_by_contact(seeded, "amy@example.com")
    assert [c["id"] for c in found] == [1]
    assert comp_svc.list_complaints_by_contact(seeded, "") == []
