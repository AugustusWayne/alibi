"""The audit engine: gather, decide, materialize.

One claim at a time, three steps that stay strictly in this order:

1. **Gather.** Q2 in the *speaker's own* mind graph returns every fact that
   overlaps the claim window and is about its subject — same-place and
   different-place together, in one query with no LIMIT.
2. **Decide.** `decide()` applies the table in spec 5.5 over that complete set.
   No LLM is involved at any point; a model never classifies a claim.
3. **Materialize.** What was proved is written back into the case graph as
   `SUPPORTED_BY` / `CONFLICTS_WITH` / `HAS_GAP` paths, plus the verdict.

The audit is audited against the speaker's *own* memory. That is the whole
idea: the question is never "is this true" but "does this agent's own record
account for what it said".

**The audit never invents a link** (project rules, rule 5). Every edge written
here corresponds to a fact the gather step actually returned.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.app.audit.coverage import Span
from backend.app.audit.decide import Decision, decide
from backend.app.case.graph import CaseGraph
from backend.app.minds.access import MindAccess


@dataclass(frozen=True)
class AuditResult:
    """One claim's audit, as computed and as written."""

    claim_id: str
    speaker: str
    subject: str
    place: str
    t0: int
    t1: int
    modality: str
    verdict: str
    coverage: float
    covered_minutes: int
    uncovered: int
    gaps: list[Span]
    supporting: list[dict]
    conflicting: list[dict]
    hearsay_support: list[dict]
    evidence: list[dict]
    reason: str


class AuditEngine:
    def __init__(self, db: Any, seed: int) -> None:
        self._db = db
        self._seed = seed
        self._case = CaseGraph(db, seed)
        self._minds: dict[str, MindAccess] = {}

    def _mind(self, agent: str) -> MindAccess:
        """Open the speaker's mind.

        The engine is part of the referee's trust boundary, not an agent tool:
        it is the one component that legitimately opens a mind by name, and it
        is never exposed to a suspect (project rules, rule 6).
        """
        if agent not in self._minds:
            self._minds[agent] = MindAccess(self._db, self._seed, agent)
        return self._minds[agent]

    def audit_claim(self, claim_id: str) -> AuditResult:
        claim = self._case.claim(claim_id)
        mind = self._mind(claim["speaker"])

        evidence = mind.gather_evidence(
            subject=claim["subject"],
            place=claim["place"],
            t0=claim["t0"],
            t1=claim["t1"],
        )
        decision = decide(
            claim_t0=claim["t0"],
            claim_t1=claim["t1"],
            modality=claim["modality"],
            evidence=evidence,
        )
        self._materialize(
            claim_id=claim_id,
            agent=claim["speaker"],
            claim_window=(claim["t0"], claim["t1"]),
            decision=decision,
        )

        return AuditResult(
            claim_id=claim_id,
            speaker=claim["speaker"],
            subject=claim["subject"],
            place=claim["place"],
            t0=claim["t0"],
            t1=claim["t1"],
            modality=claim["modality"],
            verdict=decision.verdict,
            coverage=decision.coverage_fraction,
            covered_minutes=decision.covered_minutes,
            uncovered=decision.uncovered_minutes,
            gaps=decision.gaps,
            supporting=decision.supporting,
            conflicting=decision.conflicting,
            hearsay_support=decision.hearsay_support,
            evidence=decision.evidence,
            reason=decision.reason,
        )

    def _materialize(
        self,
        *,
        claim_id: str,
        agent: str,
        claim_window: Span,
        decision: Decision,
    ) -> None:
        """Write the proof back into the case graph.

        Supporting *and* conflicting evidence are both written whatever the
        verdict: a CONTRADICTED claim keeps the memory that supported it, so
        the detective sees the whole picture rather than only the conclusion.

        Hearsay support is written as `SUPPORTED_BY` with `src='hearsay'` on
        the Evidence node. That is what keeps a HEARSAY verdict walkable — the
        shadow carries the transmission's source and tick, so the referee can
        pick the chain up later without the case graph ever holding the fact.
        """
        claim_t0, claim_t1 = claim_window
        for ev in decision.supporting + decision.hearsay_support:
            # The slice of *the claim* this memory accounts for, clipped to the
            # claim window. A fact that overruns the claim covers only the part
            # that overlaps it.
            covers = (max(ev["t0"], claim_t0), min(ev["t1"], claim_t1))
            self._case.materialize_support(
                claim_id=claim_id, evidence=ev, agent=agent, covers=covers
            )
        for ev in decision.conflicting:
            self._case.materialize_conflict(claim_id=claim_id, evidence=ev, agent=agent)
        if decision.materializes_gaps:
            for g0, g1 in decision.gaps:
                self._case.materialize_gap(claim_id=claim_id, g0=g0, g1=g1)
        self._case.set_verdict(
            claim_id=claim_id,
            verdict=decision.verdict,
            coverage=decision.coverage_fraction,
            uncovered=decision.uncovered_minutes,
        )

    def evaluate_in_mind(
        self,
        *,
        agent: str,
        subject: str,
        place: str,
        t0: int,
        t1: int,
        modality: str,
    ) -> Decision:
        """Audit a claim against one agent's memory, writing nothing.

        The referee's chain walk needs the verdict a claim would get in each
        agent's mind along the way, without those intermediate answers
        overwriting the claim's own verdict in the case graph — the claim
        belongs to its speaker, not to whoever they heard it from. So this
        gathers and decides, and deliberately does not materialize.
        """
        evidence = self._mind(agent).gather_evidence(
            subject=subject, place=place, t0=t0, t1=t1
        )
        return decide(claim_t0=t0, claim_t1=t1, modality=modality, evidence=evidence)

    def audit_all(self) -> list[AuditResult]:
        """Audit every claim in the case, in turn order."""
        return [self.audit_claim(c["id"]) for c in self._case.all_claims()]
