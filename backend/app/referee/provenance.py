"""Q3. The cross-graph provenance trace (spec 5.7). Referee only.

A HEARSAY verdict says a claim's grounding lives in someone else's memory.
This module goes and looks. It starts in the speaker's mind, reads the
`Transmission` that produced the supporting fact, follows `src_agent` and
`src_fact_id` into *that* agent's graph, audits the same claim there, and
repeats until the chain resolves or fails.

**Why only the referee can do this.** `src_fact_id` names a fact in another
graph, and FalkorDB graphs have no edges between them. Resolving the reference
means switching graphs, which no tool exposed to an agent is permitted to do
(PROJECT_RULES.md rule 6). The isolation is the architecture; the referee standing
outside it is what makes the trace meaningful rather than a self-report.

**What the trace is careful not to claim.** An origin is the end of the chain
the referee can *see*. `CHAIN_BROKEN` is ambiguous — the cited agent may have
had nothing to record, or may never have recorded what it was told — so it is
reported as its own state and never as an origin. See `terminals.py`.

**Nothing here invents provenance** (PROJECT_RULES.md rule 5). The walk reads links
the generator created and records what it found. Where a link is missing, that
absence is the finding.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.app.audit.engine import AuditEngine
from backend.app.audit.verdicts import CONTRADICTED, WITNESSED
from backend.app.case.graph import CaseGraph
from backend.app.minds.access import MindAccess, _rows
from backend.app.referee import queries as q
from backend.app.referee.terminals import (
    CHAIN_BROKEN,
    CHAIN_CYCLE,
    CHAIN_TEMPORAL_VIOLATION,
    CHAIN_TOO_DEEP,
    DEPTH_CAP,
    ORIGIN_CONTRADICTED,
    ORIGIN_TERMINALS,
    ORIGIN_UNSUPPORTED,
    ORIGIN_WITNESSED,
    UNGROUNDED_ORIGINS,
)


@dataclass(frozen=True)
class Hop:
    """One step of the chain, recorded whether or not it resolved.

    Spec 5.7 asks for agent, fact id, transmission id, tick and verdict per
    hop. `verdict` is what the claim would get in *this* agent's mind, and is
    None where the hop failed before it could be evaluated.
    """

    depth: int
    agent: str
    fact_id: str
    src: str | None
    transmission_id: str | None
    tick: int | None
    verdict: str | None
    learned_at: int | None = None


@dataclass(frozen=True)
class Chain:
    """A completed trace of one claim."""

    claim_id: str
    speaker: str
    terminal: str
    origin_agent: str | None
    hops: tuple[Hop, ...]
    detail: str

    @property
    def is_origin(self) -> bool:
        """Did the chain resolve to a named agent?

        False for every `CHAIN_*` state, including `CHAIN_BROKEN`, which names
        the agent it stopped at but does not identify it as an origin.
        """
        return self.terminal in ORIGIN_TERMINALS

    @property
    def is_ungrounded(self) -> bool:
        """Did the chain fail to reach anyone whose own memory held this?

        True for everything except `ORIGIN_WITNESSED`. A chain ending in
        someone who actually saw the thing is an honest chain.
        """
        return self.terminal != ORIGIN_WITNESSED

    @property
    def carriers(self) -> tuple[str, ...]:
        """Agents on the chain that are links rather than its origin.

        The speaker is included: repeating something is carrying it. That is
        not a fault, and the scoreboard weights it accordingly — the innocent
        repeater is by construction a carrier.
        """
        return tuple(h.agent for h in self.hops if h.agent != self.origin_agent)


class Referee:
    """Reads any mind, and the ground-truth world. Never exposed to an agent."""

    def __init__(self, db: Any, seed: int) -> None:
        self._db = db
        self._seed = seed
        self._case = CaseGraph(db, seed)
        self._engine = AuditEngine(db, seed)
        self._minds: dict[str, MindAccess] = {}

    def _mind(self, agent: str) -> MindAccess:
        if agent not in self._minds:
            self._minds[agent] = MindAccess(self._db, self._seed, agent)
        return self._minds[agent]

    def _fact_graph(self, agent: str):
        return self._db.select_graph(f"mind:{self._seed}:{agent}")

    def _fact_with_provenance(self, agent: str, fact_id: str) -> dict | None:
        """One fact in `agent`'s mind, or None if that mind never recorded it.

        None is a finding, not an error: it is exactly what separates
        CHAIN_BROKEN from an agent who recorded something unsupported.
        """
        rows = _rows(
            self._fact_graph(agent).ro_query(q.FACT_WITH_PROVENANCE, {"fact_id": fact_id})
        )
        return rows[0] if rows else None

    def hearsay_entries(self, claim: dict) -> list[dict]:
        """The secondhand memories in the speaker's mind that bear on a claim."""
        return _rows(
            self._fact_graph(claim["speaker"]).ro_query(
                q.HEARSAY_SUPPORT_FOR_CLAIM,
                {
                    "subject": claim["subject"],
                    "place": claim["place"],
                    "t0": claim["t0"],
                    "t1": claim["t1"],
                },
            )
        )

    def trace_claim(self, claim_id: str) -> Chain | None:
        """Walk a claim's provenance. None if it rests on no secondhand memory.

        Returns the first chain found, walking the speaker's hearsay support in
        a deterministic order. A claim resting on several secondhand memories
        has several chains; `hearsay_entries` exposes them all, and the eval
        traces each.
        """
        claim = self._case.claim(claim_id)
        entries = self.hearsay_entries(claim)
        if not entries:
            return None
        return self._walk(claim, entries[0])

    def _walk(self, claim: dict, entry: dict) -> Chain:
        """Follow one chain from the speaker's secondhand memory to its end."""
        speaker = claim["speaker"]
        hops: list[Hop] = [
            Hop(
                depth=0,
                agent=speaker,
                fact_id=entry["fact_id"],
                src="hearsay",
                transmission_id=entry["transmission_id"],
                tick=entry["tick"],
                verdict=None,
                learned_at=entry["learned_at"],
            )
        ]
        visited = {speaker}
        next_agent = entry["src_agent"]
        next_fact_id = entry["src_fact_id"]
        tick = entry["tick"]
        depth = 1

        while True:
            # Every condition for this hop is computed before any is consulted,
            # then one ordered table selects the outcome — the same shape as
            # the verdict decision table, and for the same reason (rule 3).
            too_deep = depth > DEPTH_CAP
            cycled = next_agent in visited
            source = None if (too_deep or cycled) else self._fact_with_provenance(
                next_agent, next_fact_id
            )
            missing = not (too_deep or cycled) and source is None
            too_early = (
                source is not None
                and source["learned_at"] is not None
                and tick is not None
                and source["learned_at"] > tick
            )

            verdict = None
            if source is not None and not too_early:
                verdict = self._engine.evaluate_in_mind(
                    agent=next_agent,
                    subject=claim["subject"],
                    place=claim["place"],
                    t0=claim["t0"],
                    t1=claim["t1"],
                    modality=claim["modality"],
                ).verdict

            contradicts_what_it_passed_on = verdict == CONTRADICTED
            holds_it_firsthand = source is not None and source["src"] == WITNESSED
            can_continue = (
                source is not None
                and not too_early
                and not contradicts_what_it_passed_on
                and not holds_it_firsthand
                and source["transmission_id"] is not None
            )
            dead_ends_here = source is not None and not too_early and not can_continue

            rows: list[tuple[bool, str, str | None, str]] = [
                (too_deep, CHAIN_TOO_DEEP, None,
                 f"depth cap of {DEPTH_CAP} reached before the chain resolved"),
                (cycled, CHAIN_CYCLE, None,
                 f"the walk returned to {next_agent}, which it had already visited"),
                (missing, CHAIN_BROKEN, None,
                 f"{next_agent} has no record {next_fact_id!r}; ambiguous, not an origin"),
                (too_early, CHAIN_TEMPORAL_VIOLATION, None,
                 f"told at tick {tick} but the cited record was learned at "
                 f"{source['learned_at'] if source else '?'}"),
                (contradicts_what_it_passed_on, ORIGIN_CONTRADICTED, next_agent,
                 f"{next_agent}'s own memory conflicts with what it passed on"),
                (holds_it_firsthand, ORIGIN_WITNESSED, next_agent,
                 f"{next_agent} holds this as witnessed memory"),
                (dead_ends_here, ORIGIN_UNSUPPORTED, next_agent,
                 f"{next_agent} holds the record but nothing witnessed backs it"),
            ]
            terminal = next(((s, a, d) for cond, s, a, d in rows if cond), None)

            if source is not None:
                hops.append(
                    Hop(
                        depth=depth,
                        agent=next_agent,
                        fact_id=next_fact_id,
                        src=source["src"],
                        transmission_id=source["transmission_id"],
                        tick=source["tick"],
                        verdict=verdict,
                        learned_at=source["learned_at"],
                    )
                )

            if terminal is not None:
                state, origin, detail = terminal
                return Chain(
                    claim_id=claim["id"],
                    speaker=speaker,
                    terminal=state,
                    origin_agent=origin,
                    hops=tuple(hops),
                    detail=detail,
                )

            visited.add(next_agent)
            tick = source["tick"]
            next_fact_id = source["src_fact_id"]
            next_agent = source["src_agent"]
            depth += 1

    # -- materialization -----------------------------------------------------

    def materialize_chain(self, chain: Chain) -> None:
        """Record a traced chain's conclusion in the case graph.

        Only the conclusion: which agent the chain reached, in what role, and
        how it ended. No private fact content crosses over, which is the same
        seam the `Evidence` shadows use — the detective learns *that* a claim's
        provenance ended somewhere, not what anyone's memory contains.

        **Who may call this.** In the application, only `polygraph` — the
        detective's budgeted tool — so a `TRACED_TO` edge exists exactly where
        a polygraph was spent. The referee's eval runs and the human
        operator's board call it directly, outside any detective's case.
        """
        if chain.origin_agent is not None:
            self._case.materialize_trace(
                claim_id=chain.claim_id,
                agent=chain.origin_agent,
                role="origin",
                terminal=chain.terminal,
                ungrounded=chain.terminal in UNGROUNDED_ORIGINS,
                depth=len(chain.hops) - 1,
            )
        for agent in dict.fromkeys(chain.carriers):
            self._case.materialize_trace(
                claim_id=chain.claim_id,
                agent=agent,
                role="carrier",
                terminal=chain.terminal,
                ungrounded=chain.is_ungrounded,
                depth=len(chain.hops) - 1,
            )

    def trace_all_hearsay(self) -> list[Chain]:
        """Trace every claim the audit grounded in secondhand memory.

        **Reads only. It writes no `TRACED_TO` edge.** Materializing a chain
        is a separate, deliberate act (`materialize_chain`), and in the
        application only `polygraph` performs it — the detective's budgeted
        tool, two per case (spec 7).

        That timing is the whole substance of the rule. The edges belong in
        the case graph, so Q8 keeps aggregating in Cypher and the privacy seam
        holds; what they must not be is present before anyone asked. A case
        graph pre-loaded with the referee's conclusions would hand the
        detective "this began with p4, and p4 has nothing behind it" for
        nothing, make the two-call budget decorative, and leave the
        graph-versus-transcript arm of the benchmark (spec 8.3) measuring who
        was handed the answer rather than graph reasoning.

        So this is the referee's own view, for eval runs and for the human
        operator's board — the operator may see everything; only the agent is
        rationed. A caller that wants these conclusions in the case graph
        materializes them itself, in one visible line, and no such caller sits
        inside a detective's case.
        """
        from backend.app.audit.verdicts import HEARSAY

        chains = []
        for claim in self._case.all_claims():
            if claim["verdict"] != HEARSAY:
                continue
            chain = self.trace_claim(claim["id"])
            if chain is None:
                continue
            chains.append(chain)
        return chains
