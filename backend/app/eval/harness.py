"""One seed, end to end, with no LLM anywhere in the run.

The order is fixed and each step is the real component, not a stand-in:

1. `plan_world` / `generate` build the world, the seven minds and the case.
2. `interview_all` has the scripted suspects testify, by role policy.
3. `AuditEngine.audit_all` produces one verdict per claim, from Cypher plus
   deterministic Python. **A model never classifies a claim** (the project
   rules, rule 1), and there is nothing to disable here: no LLM is in this path.
4. `Referee.trace_all_hearsay` walks every HEARSAY claim's provenance.
5. `PlanTruth` labels each claim from the generator's plan.

**The eval materializes nothing.** `trace_all_hearsay` reads only, and this
harness deliberately does not call `materialize_chain`. In the application only
`polygraph` writes `TRACED_TO`, which is what makes the detective's budget of
two real; an eval run that wrote the referee's conclusions into a case graph
would be putting the answer where nobody asked for it, and would leave spec
8.3's graph-versus-transcript arm measuring who was handed the answer. The
chains are scored from the `Chain` objects in memory instead.

**Nothing here is tuned.** No knob is chosen per seed, every seed runs the same
`WorldSpec`, and the scoreboard weights are not consulted at all.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.app.agents.scripted import interview_all
from backend.app.audit.engine import AuditEngine
from backend.app.case.graph import CaseGraph, case_graph_name
from backend.app.minds.access import mind_graph_name
from backend.app.referee.ground_truth import GroundTruth, PlanTruth
from backend.app.referee.provenance import Referee
from backend.app.world.generator import WorldSpec, generate, plan_world, world_graph_name


@dataclass(frozen=True)
class ClaimRecord:
    """One scored claim: what the engine said, beside what the world was.

    Flat and plain on purpose — `metrics.py` takes nothing but these, so every
    figure in the report can be computed and tested without a graph server.
    """

    seed: int
    claim_id: str
    speaker: str
    subject: str
    place: str
    t0: int
    t1: int
    modality: str

    # the engine's side
    verdict: str
    coverage: float
    uncovered: int
    gap_count: int
    chain_terminal: str | None
    chain_origin: str | None

    # the answer key's side
    label: str
    true_of_world: bool
    witnessed_backing: bool
    witnessed_conflict: bool
    any_overlapping_memory: bool
    truth_origin: str | None
    truth_chain_root: str | None
    truth_hearsay_entries: int


@dataclass(frozen=True)
class GapRecord:
    """One materialized `Gap`, with where the subject really was during it."""

    seed: int
    claim_id: str
    speaker: str
    subject: str
    place: str
    t0: int
    t1: int
    truth: str


@dataclass(frozen=True)
class SeedRun:
    """Everything one seed contributed, including what it failed to contribute."""

    seed: int
    plan_seed: int
    culprit: str
    claims: tuple[ClaimRecord, ...]
    gaps: tuple[GapRecord, ...]
    rejected: int
    fabrications: int
    relayed_fabrications: int
    chains: int
    counts: dict[str, int]

    @property
    def claim_count(self) -> int:
        return len(self.claims)


def graph_names(seed: int, people: list[str]) -> list[str]:
    """Every graph one seed owns. The one place this list is built."""
    return (
        [world_graph_name(seed), case_graph_name(seed)]
        + [mind_graph_name(seed, agent) for agent in people]
    )


def drop_seed(db: Any, seed: int, people: list[str]) -> None:
    """Delete a seed's graphs.

    FalkorDB is shared across checkouts and the graphs are keyed by seed, so a
    24-seed run that left its worlds behind would leave 216 graphs on a server
    other sessions are working against. A graph that was never created has
    nothing to drop, and `delete` raising on that is the only error swallowed
    anywhere in this package — it is teardown, and it reports nothing.
    """
    for name in graph_names(seed, people):
        try:
            db.select_graph(name).delete()
        except Exception:  # noqa: BLE001, S110
            pass


def run_seed(
    db: Any,
    seed: int,
    *,
    spec: WorldSpec | None = None,
    drop: bool = True,
) -> SeedRun:
    """Generate, interview, audit, trace and label one seed.

    `spec` is the same for every seed in a run; passing a different one per
    seed would be tuning the benchmark to its seeds (spec 8.4.5).

    The seed's graphs are dropped before the run as well as after it, so the
    figures cannot be inflated by a world some earlier session left behind.
    """
    spec = spec or WorldSpec()
    plan_seed = spec.plan_seed if spec.plan_seed is not None else seed
    plan = plan_world(plan_seed, spec)
    truth = PlanTruth(plan)
    people = [p.id for p in plan.people]

    # Start from nothing. `CREATE_PRESENCE` and `ingest_claim` append, so
    # generating into a seed whose graphs already exist silently doubles the
    # world: every claim gets ingested and audited twice and every count in the
    # report is wrong by a factor nobody would notice from the figures. These
    # graphs are keyed by seed on a server shared across checkouts, so an
    # inherited `case:{seed}` from an earlier session is a real hazard, not a
    # hypothetical one — it happened on the development seed the first time
    # this harness ran.
    drop_seed(db, seed, people)

    try:
        counts = generate(db, seed, spec=spec)
        interview_all(db, seed, plan=plan)

        case = CaseGraph(db, seed)
        audited = AuditEngine(db, seed).audit_all()
        chains = {c.claim_id: c for c in Referee(db, seed).trace_all_hearsay()}

        # Gaps as the detective would see them: the `Gap` nodes actually in the
        # case graph, not the uncovered spans the decision computed. Spec 5.5
        # grants Gap nodes to the partial-support row only, and the question
        # being scored is "when the audit reports a gap", so what the graph
        # holds is what counts. One query for the whole case, not one per claim.
        gaps_by_claim: dict[str, list[tuple[int, int]]] = {}
        for row in case.gaps():
            gaps_by_claim.setdefault(row["claim_id"], []).append(
                (int(row["t0"]), int(row["t1"]))
            )

        claim_records: list[ClaimRecord] = []
        gap_records: list[GapRecord] = []
        for result in audited:
            claim = {
                "speaker": result.speaker,
                "subject": result.subject,
                "place": result.place,
                "t0": result.t0,
                "t1": result.t1,
                "modality": result.modality,
            }
            labelled = truth.label_claim(claim)
            chain = chains.get(result.claim_id)
            spans = sorted(gaps_by_claim.get(result.claim_id, []))

            claim_records.append(
                ClaimRecord(
                    seed=seed,
                    claim_id=result.claim_id,
                    speaker=result.speaker,
                    subject=result.subject,
                    place=result.place,
                    t0=result.t0,
                    t1=result.t1,
                    modality=result.modality,
                    verdict=result.verdict,
                    coverage=result.coverage,
                    uncovered=result.uncovered,
                    gap_count=len(spans),
                    chain_terminal=chain.terminal if chain else None,
                    chain_origin=chain.origin_agent if chain else None,
                    label=labelled.label,
                    true_of_world=labelled.true_of_world,
                    witnessed_backing=labelled.witnessed_backing,
                    witnessed_conflict=labelled.witnessed_conflict,
                    any_overlapping_memory=labelled.any_overlapping_memory,
                    truth_origin=labelled.origin_agent,
                    truth_chain_root=labelled.chain_root,
                    truth_hearsay_entries=labelled.hearsay_entries,
                )
            )
            for g0, g1 in spans:
                gap_records.append(
                    GapRecord(
                        seed=seed,
                        claim_id=result.claim_id,
                        speaker=result.speaker,
                        subject=result.subject,
                        place=result.place,
                        t0=g0,
                        t1=g1,
                        truth=truth.label_gap(
                            subject=result.subject, place=result.place, t0=g0, t1=g1
                        ).verdict,
                    )
                )

        # The graph-backed answer key must agree with the plan-backed one about
        # the one thing they both hold. A disagreement means the write path
        # changed the world, and every label in this run would be suspect.
        on_graph = GroundTruth(db, seed).culprit()
        if on_graph != truth.culprit():
            raise RuntimeError(
                f"seed {seed}: world:{seed} names culprit {on_graph!r} but the "
                f"plan it was written from names {truth.culprit()!r}"
            )

        return SeedRun(
            seed=seed,
            plan_seed=plan_seed,
            culprit=truth.culprit(),
            claims=tuple(claim_records),
            gaps=tuple(gap_records),
            rejected=plan.rejected,
            fabrications=len(plan.fabrications),
            relayed_fabrications=sum(
                1 for f in plan.fabrications if f.relayed_fact_ids
            ),
            chains=len(chains),
            counts=counts,
        )
    finally:
        if drop:
            drop_seed(db, seed, people)


def run_seeds(
    db: Any,
    seeds: list[int],
    *,
    spec: WorldSpec | None = None,
    drop: bool = True,
    on_seed: Any = None,
) -> list[SeedRun]:
    """Run the frozen seeds in the order given, which is the order in the file."""
    runs = []
    for seed in seeds:
        run = run_seed(db, seed, spec=spec, drop=drop)
        runs.append(run)
        if on_seed is not None:
            on_seed(run)
    return runs


def all_claims(runs: list[SeedRun]) -> list[ClaimRecord]:
    return [c for run in runs for c in run.claims]


def all_gaps(runs: list[SeedRun]) -> list[GapRecord]:
    return [g for run in runs for g in run.gaps]
