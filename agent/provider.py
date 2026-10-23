"""Optional model providers. The app works fully without them.

Choose one with TOWNSHIPOS_AGENT_PROVIDER:
  local      default; no model, no key needed
  gemini     Google Gemini API (free tier available); needs GEMINI_API_KEY
  anthropic  Claude API; needs ANTHROPIC_API_KEY  (also accepted as "model")

Optional: TOWNSHIPOS_MODEL overrides the default model name for the chosen provider.

A provider only chooses a tool and its arguments. Write tools still need a person
to press Confirm. Only the Python standard library is used, so no extra packages.
"""
import json
import os
import urllib.error
import urllib.request

AGENT_SYSTEM_PROMPT = (
    "You are the assistant for TownshipOS, a township asset and complaint system. "
    "Choose the one tool that best fulfils the request, and fill its fields only from what the user said. "
    "Never invent asset codes, complaint IDs, dates or costs. If a required detail is missing, reply with a "
    "short question instead of calling a tool. Write tools only propose changes that a person must confirm. "
    "Answer briefly."
)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
ANTHROPIC_DEFAULT_MODEL = "claude-sonnet-5-5"

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_DEFAULT_MODEL = "gemini-3.8-flash"


class ProviderError(Exception):
    """The model could not produce a plan. The agent falls back to the local planner."""


def _post_json(url, body, headers, timeout, label):
    request = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"content-type": "application/json", **headers},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise ProviderError(f"{label} rate limit reached, try again shortly") from exc
        raise ProviderError(f"{label} HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise ProviderError(f"{label} network error: {exc}") from exc


class AnthropicProvider:
    name = "Claude model (Anthropic API)"

    def __init__(self, api_key, model=ANTHROPIC_DEFAULT_MODEL, timeout=30):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    @classmethod
    def from_env(cls):
        mode = os.environ.get("TOWNSHIPOS_AGENT_PROVIDER", "local").strip().lower()
        if mode not in ("model", "anthropic"):
            return None
        key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not key:
            return None
        model = os.environ.get("TOWNSHIPOS_MODEL", "").strip() or ANTHROPIC_DEFAULT_MODEL
        return cls(key, model)

    def plan(self, request, tools):
        body = {
            "model": self.model,
            "max_tokens": 1024,
            "system": AGENT_SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": request}],
            "tools": [{"name": t.name, "description": t.description, "input_schema": t.schema()} for t in tools],
        }
        payload = _post_json(ANTHROPIC_URL, body, {
            "x-api-key": self.api_key,
            "anthropic-version": ANTHROPIC_VERSION,
        }, self.timeout, "Anthropic")

        blocks = payload.get("content") or []
        for block in blocks:
            if block.get("type") == "tool_use":
                return {"type": "tool", "tool": block.get("name", ""), "args": block.get("input") or {}}
        text = " ".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
        if not text:
            raise ProviderError("the model returned an empty response")
        return {"type": "answer", "text": text}


def _gemini_type_names(node):
    """Gemini expects upper-case OpenAPI type names (STRING, OBJECT, INTEGER, NUMBER)."""
    if isinstance(node, dict):
        return {k: (v.upper() if k == "type" and isinstance(v, str) else _gemini_type_names(v))
                for k, v in node.items()}
    if isinstance(node, list):
        return [_gemini_type_names(v) for v in node]
    return node


class GeminiProvider:
    name = "Google Gemini API (free tier)"

    def __init__(self, api_key, model=GEMINI_DEFAULT_MODEL, timeout=30):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    @classmethod
    def from_env(cls):
        mode = os.environ.get("TOWNSHIPOS_AGENT_PROVIDER", "local").strip().lower()
        if mode != "gemini":
            return None
        key = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()
        if not key:
            return None
        model = os.environ.get("TOWNSHIPOS_MODEL", "").strip() or GEMINI_DEFAULT_MODEL
        return cls(key, model)

    @staticmethod
    def build_declarations(tools):
        declarations = []
        for tool in tools:
            declaration = {"name": tool.name, "description": tool.description}
            if tool.params:
                declaration["parameters"] = _gemini_type_names(tool.schema())
            declarations.append(declaration)
        return declarations

    def plan(self, request, tools):
        body = {
            "systemInstruction": {"parts": [{"text": AGENT_SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": request}]}],
            "tools": [{"functionDeclarations": self.build_declarations(tools)}],
            "generationConfig": {"maxOutputTokens": 1024, "temperature": 0},
        }
        payload = _post_json(
            GEMINI_URL.format(model=self.model), body,
            {"x-goog-api-key": self.api_key}, self.timeout, "Gemini",
        )

        candidates = payload.get("candidates") or []
        if not candidates:
            raise ProviderError("Gemini returned no answer (it may have been blocked by a safety filter)")
        parts = (candidates[0].get("content") or {}).get("parts") or []
        for part in parts:
            if "functionCall" in part:
                call = part["functionCall"]
                return {"type": "tool", "tool": call.get("name", ""), "args": call.get("args") or {}}
        text = " ".join(p.get("text", "") for p in parts if "text" in p).strip()
        if not text:
            raise ProviderError("Gemini returned an empty response")
        return {"type": "answer", "text": text}


def select_provider_from_env():
    """Return the provider named by TOWNSHIPOS_AGENT_PROVIDER, or None for the local planner."""
    mode = os.environ.get("TOWNSHIPOS_AGENT_PROVIDER", "local").strip().lower()
    if mode == "gemini":
        return GeminiProvider.from_env()
    if mode in ("model", "anthropic"):
        return AnthropicProvider.from_env()
    return None
