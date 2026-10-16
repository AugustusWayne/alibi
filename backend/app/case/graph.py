"""`CaseGraph` — the detective's file. Public information only.

The case graph holds claims, the public floor plan, the travel matrix, and the
redacted `Evidence` shadows the audit creates when it cites a private fact. It
never holds a private fact itself. That seam is what lets the detective walk
`SUPPORTED_BY` to see *that* a claim is grounded in an observation at a place
and time, without getting a window into the suspect's whole memory.
"""

from __future__ import annotations

from itertools import permutations
from typing import Any

from backend.app.case import queries as q
from backend.app.minds.access import _rows


def case_graph_name(seed: int) -> str:
    """`case:{seed}` — the one place this string is built."""
    return f"case:{seed}"


class CaseGraph:
    def __init__(self, db: Any, seed: int) -> None:
        self._seed = seed
        self._graph = db.select_graph(case_graph_name(seed))

    # -- floor plan ----------------------------------------------------------

    def upsert_place(self, place_id: str, name: str) -> None:
        self._graph.query(q.UPSERT_PLACE, {"id": place_id, "name": name})

    def upsert_adjacency(self, a: str, b: str, minutes: int) -> None:
        """Write a corridor in both directions, so adjacency is symmetric."""
        self._graph.query(q.UPSERT_ADJACENCY, {"a": a, "b": b, "minutes": minutes})

    def shortest_path(self, a: str, b: str) -> tuple[int, list[str]] | None:
        """Weighted shortest walk between two places, via `algo.SPpaths`.

        Also the live demo call: rendering the corridor-by-corridor route on
        the floor plan beats rendering a number.
        """
        rows = _rows(self._graph.ro_query(q.SHORTEST_PATH, {"a": a, "b": b}))
        if not rows:
            return None
        return int(rows[0]["weight"]), list(rows[0]["route"])

    def build_travel_matrix(self, place_ids: list[str]) -> int:
        """Precompute all-pairs travel times into `TRAVEL_TIME` edges.

        One standalone `algo.SPpaths` call per ordered pair, run once per world
        — about 110 calls for 11 places. The audit-time travel check then needs
        no procedure call per matched row, which was v1's biggest schedule risk.

        Raises if a pair is unreachable: a disconnected floor plan would make
        the travel check silently vacuous for those pairs, and a world
        generator that produced one is broken (PROJECT_RULES.md rule 8).
        """
        written = 0
        for a, b in permutations(sorted(place_ids), 2):
            found = self.shortest_path(a, b)
            if found is None:
                raise RuntimeError(
                    f"no path between {a!r} and {b!r} on the floor plan; "
                    f"the travel matrix would be incomplete and the impossible-travel "
                    f"check vacuous for this pair"
                )
            minutes, _route = found
            self._graph.query(q.UPSERT_TRAVEL_TIME, {"a": a, "b": b, "minutes": minutes})
            written += 1
        return written

    def travel_minutes(self, a: str, b: str) -> int | None:
        """Read the precomputed matrix. None means the matrix has no such cell."""
        rows = _rows(self._graph.ro_query(q.TRAVEL_TIME_LOOKUP, {"a": a, "b": b}))
        return int(rows[0]["minutes"]) if rows else None

    def places(self) -> list[dict]:
        return _rows(self._graph.ro_query(q.ALL_PLACES))

    # -- suspects, incident, claims ------------------------------------------

    def upsert_suspect(self, suspect_id: str, name: str) -> None:
        self._graph.query(q.UPSERT_SUSPECT, {"id": suspect_id, "name": name})

    def upsert_incident(self, incident_id: str, place: str, t0: int, t1: int) -> None:
        self._graph.query(
            q.UPSERT_INCIDENT, {"id": incident_id, "place": place, "t0": t0, "t1": t1}
        )

    def ingest_claim(
        self,
        *,
        claim_id: str,
        speaker: str,
        subject: str,
        place: str,
        t0: int,
        t1: int,
        turn: int,
        modality: str,
        relayed_from: str | None = None,
    ) -> None:
        """Q4. Record what a suspect said. The verdict starts PENDING."""
        self._graph.query(
            q.INGEST_CLAIM,
            {
                "id": claim_id,
                "speaker": speaker,
                "subject": subject,
                "place": place,
                "t0": t0,
                "t1": t1,
                "turn": turn,
                "modality": modality,
            },
        )
        if relayed_from is not None:
            self._graph.query(
                q.LINK_RELAYED_FROM, {"id": claim_id, "relayed_from": relayed_from}
            )

    def claim(self, claim_id: str) -> dict:
        rows = _rows(self._graph.ro_query(q.CLAIM_BY_ID, {"claim_id": claim_id}))
        if not rows:
            raise KeyError(f"no claim {claim_id!r} in {case_graph_name(self._seed)}")
        return rows[0]

    def all_claims(self) -> list[dict]:
        return _rows(self._graph.ro_query(q.ALL_CLAIMS))

    def claim_evidence(self, claim_id: str) -> dict:
        """The materialized path behind one claim: support, conflict, gaps."""
        rows = _rows(self._graph.ro_query(q.CLAIM_EVIDENCE, {"claim_id": claim_id}))
        if not rows:
            return {"supported_by": [], "conflicts_with": [], "gaps": []}
        row = rows[0]
        return {
            "supported_by": [x for x in row["supported_by"] if x is not None],
            "conflicts_with": [x for x in row["conflicts_with"] if x is not None],
            "gaps": sorted(g for g in row["gaps"] if g and g[0] is not None),
        }

    # -- audit materialization (spec 5.6) ------------------------------------

    def materialize_support(
        self, *, claim_id: str, evidence: dict, agent: str, covers: tuple[int, int]
    ) -> str:
        """Attach a redacted public shadow of a supporting private fact."""
        evidence_id = f"{claim_id}|{evidence['fact_id']}"
        self._graph.query(
            q.MATERIALIZE_SUPPORT,
            {
                "claim_id": claim_id,
                "evidence_id": evidence_id,
                "fact_id": evidence["fact_id"],
                "src": evidence["src"],
                "t0": evidence["t0"],
                "t1": evidence["t1"],
                "place": evidence["place"],
                "agent": agent,
                "covers_t0": covers[0],
                "covers_t1": covers[1],
            },
        )
        return evidence_id

    def materialize_conflict(self, *, claim_id: str, evidence: dict, agent: str) -> str:
        evidence_id = f"{claim_id}|{evidence['fact_id']}"
        self._graph.query(
            q.MATERIALIZE_CONFLICT,
            {
                "claim_id": claim_id,
                "evidence_id": evidence_id,
                "fact_id": evidence["fact_id"],
                "src": evidence["src"],
                "t0": evidence["t0"],
                "t1": evidence["t1"],
                "place": evidence["place"],
                "agent": agent,
            },
        )
        return evidence_id

    def materialize_gap(self, *, claim_id: str, g0: int, g1: int) -> None:
        self._graph.query(q.MATERIALIZE_GAP, {"claim_id": claim_id, "g0": g0, "g1": g1})

    def set_verdict(self, *, claim_id: str, verdict: str, coverage: float, uncovered: int) -> None:
        self._graph.query(
            q.SET_VERDICT,
            {
                "claim_id": claim_id,
                "verdict": verdict,
                "coverage": coverage,
                "uncovered": uncovered,
            },
        )

    # -- cross-claim checks (Q5, Q6, Q7) -------------------------------------

    def find_exclusive_presence(self) -> list[dict]:
        """Q5. Same person, two places, overlapping time."""
        return _rows(self._graph.query(q.EXCLUSIVE_PRESENCE))

    def find_impossible_travel(self) -> list[dict]:
        """Q6. Not enough time between two claimed places to walk between them."""
        return _rows(self._graph.query(q.IMPOSSIBLE_TRAVEL))

    def find_corroboration(self) -> list[dict]:
        """Q7. Two different speakers placing the same person in the same place."""
        return _rows(self._graph.query(q.CORROBORATION))

    def contradictions(self) -> list[dict]:
        return _rows(self._graph.ro_query(q.ALL_CONTRADICTIONS))

    def scoreboard_rows(self) -> list[dict]:
        """Q8. Raw per-suspect counts. The weighting lives in `scoreboard.py`."""
        return _rows(self._graph.ro_query(q.SCOREBOARD))

    def verdict_tally(self) -> dict[str, int]:
        return {r["verdict"]: r["n"] for r in _rows(self._graph.ro_query(q.VERDICT_TALLY))}

    def delete(self) -> None:
        self._graph.delete()
