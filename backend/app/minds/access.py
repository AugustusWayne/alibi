"""`MindAccess` — the only way to touch a private mind graph.

Isolation is application-enforced. FalkorDB graphs are genuinely separate, so
there is no edge from one mind to another; what this class adds is that the
*choice* of graph is made here, at construction, and never from an argument
supplied by a caller further down.

Project rules, rule 6: no tool exposed to an agent accepts a graph name or an
agent id. A scripted or LLM suspect is handed a `MindAccess` already bound to
its own mind, so "read someone else's memory" is not a malformed request — it
is not a request the type system can express. Only the referee constructs a
second one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.app.minds import queries as q


def mind_graph_name(seed: int, agent: str) -> str:
    """`mind:{seed}:{agent}` — the one place this string is built."""
    return f"mind:{seed}:{agent}"


@dataclass(frozen=True)
class Fact:
    """A memory as this mind holds it.

    `src` is how it was acquired — `witnessed`, `hearsay` or `inferred` — and
    is the field the audit's decision table turns on. `learned_at` is when this
    mind came to hold it, which is not when it happened: a fact about 21:00 may
    have been learned at 21:30. Without that distinction the provenance
    temporal check is impossible.
    """

    id: str
    kind: str
    src: str
    subject: str
    place: str
    t0: int
    t1: int
    learned_at: int
    heard_from: str | None = None
    src_fact_id: str | None = None
    heard_tick: int | None = None


class MindAccess:
    """A handle on exactly one agent's memory."""

    def __init__(self, db: Any, seed: int, agent: str) -> None:
        self._agent = agent
        self._seed = seed
        self._graph = db.select_graph(mind_graph_name(seed, agent))

    @property
    def agent(self) -> str:
        return self._agent

    # -- writes: the generator and the transmission step only ---------------

    def upsert_place(self, place_id: str, name: str) -> None:
        self._graph.query(q.UPSERT_PLACE, {"id": place_id, "name": name})

    def upsert_person(self, person_id: str, name: str) -> None:
        self._graph.query(q.UPSERT_PERSON, {"id": person_id, "name": name})

    def write_fact(
        self,
        *,
        fact_id: str,
        kind: str,
        src: str,
        subject: str,
        place: str,
        t0: int,
        t1: int,
        learned_at: int,
    ) -> None:
        self._graph.query(
            q.WRITE_FACT,
            {
                "id": fact_id,
                "kind": kind,
                "src": src,
                "subject": subject,
                "place": place,
                "t0": t0,
                "t1": t1,
                "learned_at": learned_at,
            },
        )

    def write_transmission(
        self,
        *,
        fact_id: str,
        transmission_id: str,
        tick: int,
        src_agent: str,
        src_fact_id: str,
    ) -> None:
        """Record that `fact_id` arrived by hearsay.

        `src_fact_id` points at a fact in *another* graph. That reference is
        soft by design: graphs are isolated, so only the referee can resolve it
        by switching graphs, which is exactly why only the referee can trace a
        chain.
        """
        self._graph.query(
            q.WRITE_TRANSMISSION,
            {
                "id": fact_id,
                "transmission_id": transmission_id,
                "tick": tick,
                "src_agent": src_agent,
                "src_fact_id": src_fact_id,
            },
        )

    def write_derivation(self, *, fact_id: str, from_fact_id: str) -> None:
        self._graph.query(q.WRITE_DERIVATION, {"id": fact_id, "from_fact_id": from_fact_id})

    # -- reads ---------------------------------------------------------------

    def gather_evidence(self, *, subject: str, place: str, t0: int, t1: int) -> list[dict]:
        """Q2. Every overlapping fact about `subject`, support and conflict together.

        No LIMIT and no ordering by relevance: the caller must see the whole
        set before deciding anything.
        """
        res = self._graph.ro_query(
            q.GATHER_EVIDENCE, {"subject": subject, "place": place, "t0": t0, "t1": t1}
        )
        return _rows(res)

    def recall(
        self,
        *,
        subject: str | None = None,
        place: str | None = None,
        t_range: tuple[int, int] | None = None,
    ) -> list[Fact]:
        """The suspect's own recall tool, over its own mind only.

        Note what is absent from this signature: there is no agent or graph
        parameter. A suspect cannot ask this for anyone else's memory.
        """
        t0, t1 = t_range if t_range else (None, None)
        res = self._graph.ro_query(
            q.RECALL, {"subject": subject, "place": place, "t0": t0, "t1": t1}
        )
        return [
            Fact(
                id=r["fact_id"],
                kind=r["kind"],
                src=r["src"],
                subject=r["subject"],
                place=r["place"],
                t0=r["t0"],
                t1=r["t1"],
                learned_at=r["learned_at"],
                heard_from=r["heard_from"],
                src_fact_id=r["src_fact_id"],
                heard_tick=r["heard_tick"],
            )
            for r in _rows(res)
        ]

    def fact_by_id(self, fact_id: str) -> dict | None:
        """One fact, or None if this mind never recorded it.

        None is a real finding, not an error: it is what distinguishes
        CHAIN_BROKEN from a source that recorded something unsupported.
        """
        rows = _rows(self._graph.ro_query(q.FACT_BY_ID, {"fact_id": fact_id}))
        return rows[0] if rows else None

    def count_facts(self) -> int:
        return _rows(self._graph.ro_query(q.COUNT_FACTS))[0]["facts"]

    def delete(self) -> None:
        """Drop this mind. Test teardown and world regeneration only."""
        self._graph.delete()


def _rows(result: Any) -> list[dict]:
    """Zip a FalkorDB result set into dicts keyed by the RETURN aliases.

    Deliberately not wrapped in try/except. A query that fails must raise
    (project rules, rule 8) — an audit that silently sees no evidence would
    report UNSUPPORTED for a claim it never actually examined, which is the worst
    failure this system can have.
    """
    header = [h[1] if isinstance(h, (list, tuple)) else h for h in result.header]
    header = [h.decode() if isinstance(h, bytes) else h for h in header]
    return [dict(zip(header, row, strict=True)) for row in result.result_set]
