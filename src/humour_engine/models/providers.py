"""Provider adapters. Each declares identity, capabilities, limits and processing location.

- FixtureProvider: returns hand-authored responses for registered diagnostic inputs only.
  Anything else raises ProviderUnavailable; it never invents an answer.
- AnthropicProvider: real inference over the Messages API. Disabled unless the request's
  provider policy allows external inference, names this provider, and a key is present in
  the environment. Credentials are read at call time and never logged.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import yaml

from humour_engine.analysis.text import sha
from humour_engine.contracts.analysis import AnalysisMode

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PATH = REPO_ROOT / "data" / "fixtures" / "diagnostic_cases.yaml"


class ProviderUnavailable(RuntimeError):
    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class ProviderTimeout(ProviderUnavailable):
    def __init__(self, message: str):
        super().__init__("provider_timeout", message, retryable=True)


@dataclass
class ProviderCapabilities:
    provider_id: str
    model: str
    mode: AnalysisMode
    modalities: tuple[str, ...]
    structured_output: str
    max_context_tokens: int
    max_output_tokens: int
    timeout_s: float
    max_retries: int
    remote: bool
    retention_note: str
    requires_remote_code: bool = False
    price_per_mtok_in: float | None = None
    price_per_mtok_out: float | None = None
    pricing_source: str | None = None


@dataclass
class ProviderResponse:
    payload: dict
    input_tokens: int | None
    output_tokens: int | None
    raw_text: str | None = None
    meta: dict = field(default_factory=dict)


class Provider(Protocol):
    caps: ProviderCapabilities

    def interpret(self, system: str, user: str, tool: dict, max_output_tokens: int) -> ProviderResponse: ...


def material_key(material: dict) -> str:
    """Fixture lookup key over everything that can change a reading: focus, every segment's id,
    speaker and text, quoted voices, provided facts and declared intent."""

    def seg(s):
        return [s["segment_id"], s.get("speaker_id"), s["text"], s.get("quoted_from")]

    segs = sorted([seg(s) for s in material.get("context_segments", [])] + [seg(s) for s in material["segments"]])
    blob = {
        "focus": sorted(material.get("focus_segment_ids") or [s["segment_id"] for s in material["segments"]]),
        "segments": segs,
        "facts": material.get("provided_facts", []),
        "intent": [material.get("declared_intent"), material.get("declared_intent_by")],
    }
    return sha(json.dumps(blob, ensure_ascii=False))[:24]


class FixtureProvider:
    """Hand-authored, unreviewed responses keyed by exact input. Always labelled fixture."""

    def __init__(self, path: Path = FIXTURE_PATH):
        self.caps = ProviderCapabilities(
            provider_id="fixture",
            model="fixture-pack-v1",
            mode=AnalysisMode.fixture,
            modalities=("text", "transcript"),
            structured_output="pre-authored JSON",
            max_context_tokens=100_000,
            max_output_tokens=4000,
            timeout_s=0,
            max_retries=0,
            remote=False,
            retention_note="local file; nothing leaves the machine",
        )
        self._by_key: dict[str, dict] = {}
        self._critiques: dict[str, dict] = {}
        if path.exists():
            data = yaml.safe_load(path.read_text())
            for case in data.get("cases", []):
                if "fixture_response" not in case:
                    continue
                key = material_key(_case_material(case))
                self._by_key[key] = case["fixture_response"]
                if "fixture_critique" in case:
                    self._critiques[key] = case["fixture_critique"]
        self.last_key: str | None = None

    def set_material(self, material: dict) -> None:
        self.last_key = material_key(material)

    def interpret(self, system: str, user: str, tool: dict, max_output_tokens: int) -> ProviderResponse:
        key = self.last_key
        store = self._critiques if tool["name"] == "submit_critique" else self._by_key
        if key is None or key not in store:
            raise ProviderUnavailable(
                "fixture_missing", "no fixture is registered for this exact input; fixture mode cannot analyse new text"
            )
        return ProviderResponse(payload=json.loads(json.dumps(store[key])), input_tokens=0, output_tokens=0)


def _case_material(case: dict) -> dict:
    req = case["request"]
    ctx = req.get("context", {})
    focus = req.get("focus") or [s["segment_id"] for s in req["segments"]]

    def seg(s):
        return {"segment_id": s["segment_id"], "speaker_id": s.get("speaker_id"), "text": s["text"],
                "quoted_from": s.get("quoted_from")}

    return {
        "focus_segment_ids": focus,
        "segments": [seg(s) for s in req["segments"] if s["segment_id"] in focus],
        "context_segments": [seg(s) for s in req["segments"] if s["segment_id"] not in focus]
        + [seg(s) for s in ctx.get("prior_segments", [])],
        "provided_facts": ctx.get("provided_facts", []),
        "declared_intent": ctx.get("declared_intent"),
        "declared_intent_by": ctx.get("declared_intent_by"),
    }


class AnthropicProvider:
    """Real inference adapter. Pricing is unknown unless supplied by the operator."""

    API_URL = "https://api.anthropic.com/v1/messages"
    KEY_ENV = "ANTHROPIC_API_KEY"

    def __init__(
        self,
        model: str | None = None,
        timeout_s: float = 60.0,
        max_retries: int = 1,
        price_in: float | None = None,
        price_out: float | None = None,
        transport=None,
    ):
        model = model or os.environ.get("HUMOUR_ENGINE_MODEL", "claude-sonnet-5-5")
        self.caps = ProviderCapabilities(
            provider_id="anthropic",
            model=model,
            mode=AnalysisMode.live,
            modalities=("text", "transcript"),
            structured_output="forced tool use with JSON schema",
            max_context_tokens=200_000,
            max_output_tokens=4000,
            timeout_s=timeout_s,
            max_retries=max_retries,
            remote=True,
            retention_note="input is sent to the Anthropic API; retention follows the account's API data policy",
            price_per_mtok_in=price_in,
            price_per_mtok_out=price_out,
            pricing_source="operator-supplied" if price_in is not None else None,
        )
        self._transport = transport or self._http

    @classmethod
    def available(cls) -> bool:
        return bool(os.environ.get(cls.KEY_ENV))

    def _http(self, body: dict) -> dict:
        key = os.environ.get(self.KEY_ENV)
        if not key:
            raise ProviderUnavailable("provider_unconfigured", f"{self.KEY_ENV} is not set")
        req = urllib.request.Request(
            self.API_URL,
            data=json.dumps(body).encode(),
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.caps.timeout_s) as r:
                return json.loads(r.read())
        except TimeoutError as e:
            raise ProviderTimeout("provider request timed out; charges may still have been incurred") from e
        except urllib.error.HTTPError as e:
            retry = e.code in (429, 500, 502, 503, 529)
            raise ProviderUnavailable(f"provider_http_{e.code}", f"provider returned HTTP {e.code}", retryable=retry) from e
        except urllib.error.URLError as e:
            raise ProviderUnavailable("provider_unreachable", "provider endpoint unreachable", retryable=True) from e

    def interpret(self, system: str, user: str, tool: dict, max_output_tokens: int) -> ProviderResponse:
        body = {
            "model": self.caps.model,
            "max_tokens": max_output_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "tools": [tool],
            "tool_choice": {"type": "tool", "name": tool["name"]},
        }
        t0 = time.monotonic()
        data = self._transport(body)
        blocks = [b for b in data.get("content", []) if b.get("type") == "tool_use" and b.get("name") == tool["name"]]
        usage = data.get("usage", {})
        if not blocks:
            raise ProviderUnavailable("provider_no_structured_output", "provider returned no tool_use block", retryable=True)
        return ProviderResponse(
            payload=blocks[0]["input"],
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            meta={"stop_reason": data.get("stop_reason"), "latency_ms": int((time.monotonic() - t0) * 1000)},
        )


class ControlCenterProvider:
    """Real inference through Control Center, which holds the Anthropic key.

    Two doors, both on Control Center's own key and model (docs: control-center
    docs/app/everywhere/humour.md):
      - a growth engine posts to /api/growth/engines/<slug>/humour on its own bearer
        (env HUMOUR_ENGINE_CC_ENGINE and HUMOUR_ENGINE_CC_BEARER);
      - nothing else here: cloud sessions use the gateway operation anthropic.humour
        through the Control Center connector, which needs owner approval per call.
    Control Center accepts only this package's published prompts (schemas/prompt_hashes.json).
    """

    BASE_ENV = "HUMOUR_ENGINE_CC_URL"
    ENGINE_ENV = "HUMOUR_ENGINE_CC_ENGINE"
    BEARER_ENV = "HUMOUR_ENGINE_CC_BEARER"
    DEFAULT_BASE = "https://controlcenter.krishraja.com"

    def __init__(self, timeout_s: float = 150.0, transport=None):
        self.caps = ProviderCapabilities(
            provider_id="controlcenter",
            model="control-center:SYNTHESIS_MODEL",
            mode=AnalysisMode.live,
            modalities=("text", "transcript"),
            structured_output="forced tool use, run by Control Center",
            max_context_tokens=17_000,  # Control Center caps material at 60,000 characters
            max_output_tokens=4000,
            timeout_s=timeout_s,
            max_retries=0,
            remote=True,
            retention_note="input goes to Control Center, which calls the Anthropic API; metered as humour-<engine>",
        )
        self._transport = transport or self._http

    @classmethod
    def available(cls) -> bool:
        return bool(os.environ.get(cls.ENGINE_ENV) and os.environ.get(cls.BEARER_ENV))

    def _http(self, url: str, body: dict) -> tuple[int, dict]:
        bearer = os.environ.get(self.BEARER_ENV)
        if not bearer:
            raise ProviderUnavailable("provider_unconfigured", f"{self.BEARER_ENV} is not set")
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers={"authorization": f"Bearer {bearer}", "content-type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.caps.timeout_s) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read())
            except Exception:  # noqa: BLE001 - body is optional on errors
                return e.code, {}
        except TimeoutError as e:
            raise ProviderTimeout("Control Center request timed out; the model call may still have been charged") from e
        except urllib.error.URLError as e:
            raise ProviderUnavailable("provider_unreachable", "Control Center unreachable", retryable=True) from e

    def interpret(self, system: str, user: str, tool: dict, max_output_tokens: int) -> ProviderResponse:
        engine = os.environ.get(self.ENGINE_ENV)
        if not engine:
            raise ProviderUnavailable("provider_unconfigured", f"{self.ENGINE_ENV} is not set")
        base = os.environ.get(self.BASE_ENV, self.DEFAULT_BASE).rstrip("/")
        if not base.startswith("https://"):
            raise ProviderUnavailable("provider_unconfigured", "Control Center URL must be https")
        body = {"system": system, "user": user, "tool": tool, "max_output_tokens": min(max_output_tokens, 4000)}
        status, data = self._transport(f"{base}/api/growth/engines/{engine}/humour", body)
        if status != 200 or not data.get("ok"):
            code = str(data.get("error") or f"http_{status}")
            raise ProviderUnavailable(f"controlcenter_{code}"[:80], f"Control Center refused or failed: {code}",
                                      retryable=status in (429, 502, 503, 504))
        usage = data.get("usage") or {}
        return ProviderResponse(
            payload=data["payload"],
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            meta={"model": data.get("model"), "prompt": data.get("prompt"), "cost_usd": data.get("cost_usd"),
                  "cap": data.get("cap"), "used": data.get("used")},
        )
