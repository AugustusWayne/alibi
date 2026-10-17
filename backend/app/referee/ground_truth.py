"""Reads `world:{seed}` — what actually happened. Referee only, scoring only.

This is the only module that opens the ground-truth graph. It exists so
origin-identification accuracy can be *measured* rather than asserted (spec
5.7 and section 8): the trace says where it thinks an account began, and this
says where the generator actually planted it.

Nothing here is reachable from the audit path. The audit engine imports
nothing from this module, and must not — an audit that could consult the
answer key would not be auditing anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.app.minds.access import _rows
from backend.app.world import queries as q
from backend.app.world.generator import world_graph_name


@dataclass(frozen=True)
class Fabrication:
    """One thing the generator instructed an agent to assert."""

    claim_key: str
    by_person: str
    reason: str
    pathology: str
    src_fact_id: str


class GroundTruth:
    def __init__(self, db: Any, seed: int) -> None:
        self._graph = db.select_graph(world_graph_name(seed))

    def people(self) -> dict[str, str]:
        """Agent id to the role the generator gave it."""
        return {r["id"]: r["role"] for r in _rows(self._graph.ro_query(q.ALL_PEOPLE))}

    def culprit(self) -> str:
        return next(pid for pid, role in sorted(self.people().items()) if role == "culprit")

    def fabrications(self) -> list[Fabrication]:
        return [
            Fabrication(
                claim_key=r["claim_key"],
                by_person=r["by_person"],
                reason=r["reason"],
                pathology=r["pathology"],
                src_fact_id=r["src_fact_id"],
            )
            for r in _rows(self._graph.ro_query(q.ALL_PLANTED_FABRICATIONS))
        ]

    def presences(self) -> list[dict]:
        return _rows(self._graph.ro_query(q.ALL_PRESENCES))
