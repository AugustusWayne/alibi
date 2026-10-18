"""The FastAPI orchestrator.

M0 shipped `/health`. M4 mounts the case routes and the SSE stream from
`backend/app/api`, which is where the privacy seam is documented and tested:
every route serves the public case graph, and none of them can reach a mind
or a ground-truth label.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from backend.app import db
from backend.app.api.routes import router as case_router
from backend.app.config import settings

app = FastAPI(
    title="Alibi",
    version="0.4.0-m4",
    summary="An epistemic audit layer for multi-agent systems, on FalkorDB.",
)
app.include_router(case_router)


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
