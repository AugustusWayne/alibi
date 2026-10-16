"""FastAPI skeleton.

M0 ships one route. The orchestrator, SSE stream and agent routes arrive with
the milestones that need them (spec section 3).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from backend.app import db
from backend.app.config import settings

app = FastAPI(
    title="Alibi",
    version="0.0.1-m0",
    summary="An epistemic audit layer for multi-agent systems, on FalkorDB.",
)


@app.get("/health")
def health() -> JSONResponse:
    """Report whether FalkorDB is reachable, and say so honestly when it is not.

    The error text is surfaced rather than swallowed: a health check that
    returns `ok` while the database is down is worse than no health check.
    """
    try:
        graphs = db.list_graphs()
    except Exception as exc:  # noqa: BLE001 — the whole point is to report it
        return JSONResponse(
            status_code=503,
            content={
                "status": "falkordb_unreachable",
                "host": settings.falkor_host,
                "port": settings.falkor_port,
                "error": f"{type(exc).__name__}: {exc}",
            },
        )
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "host": settings.falkor_host,
            "port": settings.falkor_port,
            "graphs": graphs,
        },
    )
