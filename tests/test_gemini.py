import json
import urllib.error

import pytest

from agent import provider as provider_module
from agent.core import TownshipAgent
from agent.provider import GeminiProvider, ProviderError, select_provider_from_env
from agent.tools import TOOLS
from services import complaints as comp_svc


class FakeResponse:
    def __init__(self, data):
        self._bytes = json.dumps(data).encode("utf-8")

    def read(self):
        return self._bytes

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def fake_urlopen(payload=None, http_code=None):
    def opener(request, timeout=None):
        if http_code:
            raise urllib.error.HTTPError(request.full_url, http_code, "error", hdrs=None, fp=None)
        return FakeResponse(payload)
    return opener


@pytest.fixture
def gemini_env(monkeypatch):
    monkeypatch.setenv("TOWNSHIPOS_AGENT_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("TOWNSHIPOS_MODEL", raising=False)


def test_gemini_off_without_mode_or_key(monkeypatch):
    monkeypatch.delenv("TOWNSHIPOS_AGENT_PROVIDER", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert select_provider_from_env() is None
    monkeypatch.setenv("TOWNSHIPOS_AGENT_PROVIDER", "gemini")
    assert GeminiProvider.from_env() is None  # mode set, but no key


def test_gemini_selected_with_key(gemini_env):
    provider = select_provider_from_env()
    assert isinstance(provider, GeminiProvider)
    assert provider.model == "gemini-3.8-flash"


def test_google_api_key_name_also_accepted(monkeypatch):
    monkeypatch.setenv("TOWNSHIPOS_AGENT_PROVIDER", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "other-key")
    assert GeminiProvider.from_env().api_key == "other-key"


def test_schema_types_are_upper_case_for_gemini():
    declarations = GeminiProvider.build_declarations([TOOLS["asset_details"]])
    params = declarations[0]["parameters"]
    assert params["type"] == "OBJECT"
    assert params["properties"]["asset_code"]["type"] == "STRING"


def test_tools_without_parameters_omit_the_schema():
    declarations = GeminiProvider.build_declarations([TOOLS["overdue_inspections"]])
    assert "parameters" not in declarations[0]


def test_function_call_becomes_a_tool_plan(monkeypatch, gemini_env):
    payload = {"candidates": [{"content": {"parts": [
        {"functionCall": {"name": "asset_details", "args": {"asset_code": "WP-001"}}}]}}]}
    monkeypatch.setattr(provider_module.urllib.request, "urlopen", fake_urlopen(payload))
    plan = GeminiProvider("k").plan("show WP-001", [TOOLS["asset_details"]])
    assert plan == {"type": "tool", "tool": "asset_details", "args": {"asset_code": "WP-001"}}


def test_text_response_becomes_an_answer(monkeypatch):
    payload = {"candidates": [{"content": {"parts": [{"text": "Hello there."}]}}]}
    monkeypatch.setattr(provider_module.urllib.request, "urlopen", fake_urlopen(payload))
    plan = GeminiProvider("k").plan("hi", list(TOOLS.values()))
    assert plan == {"type": "answer", "text": "Hello there."}


def test_rate_limit_gives_a_friendly_error(monkeypatch):
    monkeypatch.setattr(provider_module.urllib.request, "urlopen", fake_urlopen(http_code=429))
    with pytest.raises(ProviderError, match="rate limit"):
        GeminiProvider("k").plan("hi", list(TOOLS.values()))


def test_blocked_response_gives_a_clear_error(monkeypatch):
    monkeypatch.setattr(provider_module.urllib.request, "urlopen", fake_urlopen({"candidates": []}))
    with pytest.raises(ProviderError, match="safety filter"):
        GeminiProvider("k").plan("hi", list(TOOLS.values()))


def test_agent_falls_back_when_gemini_is_down(monkeypatch, seeded, today, gemini_env):
    monkeypatch.setattr(provider_module.urllib.request, "urlopen", fake_urlopen(http_code=500))
    agent = TownshipAgent(seeded, today=today)  # reads the Gemini env settings
    assert isinstance(agent.provider, GeminiProvider)
    reply = agent.handle("show WP-001")
    assert reply.mode == "local"
    assert "Gemini" in reply.notice
    assert "WP-001" in reply.message


def test_gemini_write_still_needs_confirmation(monkeypatch, seeded, today, gemini_env):
    payload = {"candidates": [{"content": {"parts": [{"functionCall": {"name": "create_complaint", "args": {
        "title": "Lamp out", "location": "Park", "category": "Streetlight", "urgency": "Low"}}}]}}]}
    monkeypatch.setattr(provider_module.urllib.request, "urlopen", fake_urlopen(payload))
    agent = TownshipAgent(seeded, today=today)
    before = len(comp_svc.list_complaints(seeded))
    reply = agent.handle("the lamp in the park is out")
    assert reply.mode == "model"
    assert len(reply.pending) == 1
    assert len(comp_svc.list_complaints(seeded)) == before
