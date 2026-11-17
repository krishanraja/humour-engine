"""Equivalent semantics across library, CLI, HTTP and MCP; fixture pack (classes 18, 19, 20)."""

import asyncio
import json

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from humour_engine.analysis.core import EngineDeps, analyse
from humour_engine.contracts.analysis import AnalysisRequest
from humour_engine.evaluation.diagnostics import run_pack
from humour_engine.interfaces.cli import app as cli_app
from humour_engine.interfaces.http import create_app
from humour_engine.interfaces.mcp_server import create_server
from humour_engine.models.providers import FixtureProvider

REQ = {
    "request_id": "eq",
    "focus_segment_ids": ["t1"],
    "segments": [{"segment_id": "t1", "speaker_id": "a", "sequence": 1,
                  "text": "The bank promised interest. I am still bored."}],
    "provider_policy": {"allowed_provider_ids": ["fixture"]},
}


def _semantic(d: dict) -> dict:
    keep = ("status", "analysis_mode", "comic_reading", "evidence", "task_results", "requested_tasks")
    out = {k: d[k] for k in keep}
    out["interpretations"] = [{k: v for k, v in i.items()} for i in d["interpretations"]]
    return out


def _deps():
    return EngineDeps(providers={"fixture": FixtureProvider()})


def test_library_http_cli_mcp_equivalent(tmp_path, monkeypatch):
    lib = analyse(AnalysisRequest.model_validate(REQ), _deps()).model_dump(mode="json")

    http = TestClient(create_app(_deps())).post("/v1/analyse", json=REQ).json()["result"]

    f = tmp_path / "req.json"
    f.write_text(json.dumps(REQ))
    monkeypatch.setenv("HUMOUR_ENGINE_STYLE_MODEL", str(tmp_path / "none.pkl"))
    out = CliRunner().invoke(cli_app, ["analyse", "--file", str(f), "--fixture", "--format", "json"])
    assert out.exit_code == 0, out.output
    cli = json.loads(out.output)

    server = create_server(_deps())
    mcp_raw = asyncio.run(server.call_tool("humour_analyse", {"request": REQ}))
    text = mcp_raw[0][0].text if isinstance(mcp_raw, tuple) else getattr(mcp_raw, "content", mcp_raw)[0].text
    mcp = json.loads(text)

    ref = _semantic(lib)
    for other in (http, cli, mcp):
        assert _semantic(other) == ref


def test_http_rejects_invalid_and_non_json():
    c = TestClient(create_app(_deps()))
    r = c.post("/v1/analyse", json={**REQ, "segments": []})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_request"
    r = c.post("/v1/analyse", content=b"x", headers={"content-type": "text/plain"})
    assert r.status_code == 415
    r = c.post("/v1/analyse", content=b"{" * 600_000, headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_http_metadata_routes():
    c = TestClient(create_app(_deps()))
    caps = c.get("/v1/capabilities").json()
    assert "fixture" in caps["providers_configured"]
    assert "image" in caps["modalities_unsupported"]
    assert c.get("/v1/taxonomy").json()["axes"]["mechanism"]


def test_http_compare_route():
    c = TestClient(create_app(_deps()))
    body = {
        "request_id": "c", "focus_segment_ids": ["t1"],
        "variant_a": {"label": "pun", "segments": REQ["segments"]},
        "variant_b": {"label": "broken", "segments": [{"segment_id": "t1", "sequence": 1,
                       "text": "The bank promised interest. The branch opens at nine."}]},
        "provider_policy": {"allowed_provider_ids": ["fixture"]},
        "budget": {"max_model_calls": 2},
    }
    r = c.post("/v1/compare", json=body).json()["result"]
    assert r["status"] == "complete"
    assert any(d["dimension"] == "comic_reading" for d in r["differences"])


def test_server_refuses_public_bind():
    import pytest

    from humour_engine.interfaces.http import serve

    with pytest.raises(SystemExit):
        serve(host="0.0.0.0")


def test_fixture_pack_engineering_checks_pass():
    rows = run_pack(_deps(), ["fixture"])
    assert all(r["mode"] == "fixture" for r in rows)
    assert [r["case"] for r in rows if not r["pass"]] == []


def test_unsupported_modality_is_explicit():
    req = {**REQ, "segments": [{**REQ["segments"][0], "modality": "audio"}]}
    res = analyse(AnalysisRequest.model_validate(req), _deps())
    assert res.status.value == "unsupported"
    assert res.task_results[0].errors[0].code == "unsupported_modality"
    assert res.modalities_actually_processed == []
