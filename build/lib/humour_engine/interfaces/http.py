"""HTTP adapter. Binds to loopback by default; no auth, so never expose publicly."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from humour_engine.analysis.render import render_compare_markdown, render_markdown
from humour_engine.interfaces.service import (
    build_deps,
    capabilities,
    run_analyse,
    run_compare,
    taxonomy_payload,
)

MAX_BODY = 512_000


def create_app(deps=None) -> FastAPI:
    deps = deps or build_deps()
    app = FastAPI(title="humour-engine", version="1", docs_url=None, redoc_url=None)

    async def _body(request: Request) -> dict:
        raw = await request.body()
        if len(raw) > MAX_BODY:
            raise HTTPException(413, "request too large")
        if request.headers.get("content-type", "").split(";")[0] != "application/json":
            raise HTTPException(415, "application/json required")
        import json

        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            raise HTTPException(400, "invalid JSON") from e

    @app.exception_handler(ValidationError)
    async def _invalid(_, exc: ValidationError):
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "invalid_request", "details": exc.errors(include_url=False, include_input=False)}},
        )

    @app.exception_handler(ValueError)
    async def _bad_value(_, exc: ValueError):
        return JSONResponse(status_code=422, content={"error": {"code": "invalid_request", "details": str(exc)[:500]}})

    def _shape(res, md_fn, format: str):
        if format not in ("json", "markdown", "both"):
            raise HTTPException(400, "format must be json, markdown or both")
        out = {}
        if format in ("json", "both"):
            out["result"] = res.model_dump(mode="json")
        if format in ("markdown", "both"):
            out["markdown"] = md_fn(res)
        return out

    @app.post("/v1/analyse")
    async def analyse_route(request: Request, format: str = "json"):
        return _shape(run_analyse(await _body(request), deps), render_markdown, format)

    @app.post("/v1/compare")
    async def compare_route(request: Request, format: str = "json"):
        return _shape(run_compare(await _body(request), deps), render_compare_markdown, format)

    @app.get("/v1/capabilities")
    async def caps():
        return capabilities(deps)

    @app.get("/v1/taxonomy")
    async def tax():
        return taxonomy_payload()

    return app


def serve(host: str = "127.0.0.1", port: int = 8765, allow_non_loopback: bool = False) -> None:
    import uvicorn

    if host not in ("127.0.0.1", "localhost", "::1") and not allow_non_loopback:
        raise SystemExit("refusing to bind a non-loopback address; this service has no authentication")
    uvicorn.run(create_app(), host=host, port=port, log_level="warning", access_log=False)
