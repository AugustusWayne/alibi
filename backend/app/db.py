"""The single place that opens a FalkorDB connection.

Graph-name selection lives behind this module and will move behind `MindAccess`
in M1. No tool exposed to an agent may accept a graph name or an agent id
(project rules, rule 6), so nothing here is ever handed to an agent directly.
"""

from __future__ import annotations

from falkordb import FalkorDB

from backend.app.config import Settings, settings


def connect(cfg: Settings | None = None) -> FalkorDB:
    """Open a client.

    Raises if FalkorDB is unreachable. It never returns a degraded client:
    a dead database must be loud, not empty (project rules, rule 8).
    """
    cfg = cfg or settings
    return FalkorDB(host=cfg.falkor_host, port=cfg.falkor_port)


def list_graphs(cfg: Settings | None = None) -> list[str]:
    """Liveness probe that touches the server without running any Cypher."""
    return connect(cfg).list_graphs()
