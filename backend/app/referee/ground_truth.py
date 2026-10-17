"""Reads `world:{seed}` — what actually happened. Referee only, scoring only.

This is the only module that opens the ground-truth graph. It exists so
origin-identification accuracy can be *measured* rather than asserted (spec
5.7 and section 8): the trace says where it thinks an account began, and this
says where the generator actually planted it.

It is also the only place a claim may be *labelled* (spec 8.1). `GroundTruth`
reads the world graph; `PlanTruth` further down reads the generator's plan,
which is the same answer key in the form that still holds the facts and
transmissions the world graph does not. Both are scoring-only.

Nothing here is reachable from the audit path. The audit engine imports
nothing from this module, and must not — an audit that could consult the
answer key would not be auditing anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.app.audit.coverage import coverage
from backend.app.audit.time_contract import overlaps
from backend.app.audit.verdicts import HEARSAY_SRC, THROUGHOUT, WITNESSED
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


# -- claim labels (spec 8.1) --------------------------------------------------
#
# These four are the answer key for scoring, and the project rules (rule 2)
# confine them to this package: they are the only vocabulary in the repo that speaks about
# intent, and they exist so the eval can *measure* how often an ungrounded
# verdict corresponds to a world where the claim was in fact false. They must
# never reach the case graph, the API, a UI fixture or a verdict. The five
# verdicts in `audit/verdicts.py` are what the system says about a claim; these
# are what the generator knows about the world, and the gap between the two is
# the result the whole project is trying to report honestly.

TRUE_CLAIM = "TRUE_CLAIM"
"""The claim matches what the generator made happen."""

DELIBERATE_FABRICATION = "DELIBERATE_FABRICATION"
"""The generator instructed this agent to assert this falsehood."""

RELAYED_FALSEHOOD = "RELAYED_FALSEHOOD"
"""False, and the speaker's support traces back to a planted origin.

The speaker is not thereby at fault: their memory genuinely holds what they
were told. This label names the provenance of the falsehood, not a culpability.
"""

HONEST_ERROR = "HONEST_ERROR"
"""False, and nothing instructed it — the speaker's own account simply drifts.

With scripted suspects this is almost entirely the `merge_adjacent` case: a
witness who was in a room twice says they were there the whole time, and the
span they assert overruns the span they lived. A real witness does this
constantly, which is why it is in the taxonomy at all.
"""

ALL_LABELS = (TRUE_CLAIM, DELIBERATE_FABRICATION, RELAYED_FALSEHOOD, HONEST_ERROR)

FALSE_LABELS = (DELIBERATE_FABRICATION, RELAYED_FALSEHOOD, HONEST_ERROR)
"""The three labels that mean the claim did not match the world."""

_ROOT_DEPTH_CAP = 8
"""How far the ground-truth provenance walk follows a chain before giving up.

Independent of the referee's own DEPTH_CAP on purpose: this walk reads the
generator's plan, so a cap hit here would be a generator bug rather than an
epistemic state, and it must not be silently confused with `CHAIN_TOO_DEEP`.
"""


@dataclass(frozen=True)
class ClaimTruth:
    """What the generator's own records say about one claim.

    Computed from the plan, never from the audit's output. Deriving any part of
    the answer key from the thing being scored would make the metric a
    restatement of the engine's own opinion.
    """

    label: str
    true_of_world: bool
    witnessed_backing: bool
    """Whether the speaker's own witnessed memory accounts for the claim.

    The ground-truth counterpart of a SUPPORTED verdict, computed from the plan
    rather than through the graph. Scoring the engine against this measures
    grounding detection; scoring it against `label` measures falsehood
    detection, and the two are deliberately different questions.
    """

    witnessed_conflict: bool
    """Whether the speaker's own witnessed memory places the subject elsewhere.

    The ground-truth counterpart of CONTRADICTED.
    """

    any_overlapping_memory: bool
    """Whether the speaker holds *any* memory about the subject overlapping it.

    The ground-truth counterpart of UNSUPPORTED, which spec 5.5 defines as "no
    overlapping facts at all" — any source and any place, not only witnessed
    same-place ones. Scoring the engine's ungrounded signal against this and
    `witnessed_conflict` together is the apples-to-apples grounding question;
    scoring it against `witnessed_backing` asks the different and stricter
    question of whether memory *fully* covered the claim.
    """

    origin_agent: str | None
    """The agent a planted falsehood began with, where the plan names one."""

    chain_root: str | None
    """Who first held the memory this claim rests on, if it rests on hearsay.

    The root of the *first* secondhand memory bearing on the claim, in the same
    order the referee takes them, because `trace_claim` walks that one. None
    when the claim is firsthand, or when the cited record exists in no mind — a
    dangling citation has no root to name.
    """

    hearsay_entries: int = 0
    """How many secondhand memories in the speaker's mind bear on the claim.

    More than one means the claim has more than one chain and the engine
    reports the first. Counted so the report can say how often that happens
    rather than leaving it as an unstated choice.
    """


@dataclass(frozen=True)
class GapTruth:
    """Where the subject really was during one span the audit left unaccounted."""

    ELSEWHERE = "ELSEWHERE"
    IN_TRANSIT = "IN_TRANSIT"
    AT_CLAIMED_PLACE = "AT_CLAIMED_PLACE"

    verdict: str
    t0: int
    t1: int


GAP_TRUTHS = (GapTruth.ELSEWHERE, GapTruth.IN_TRANSIT, GapTruth.AT_CLAIMED_PLACE)


class PlanTruth:
    """The answer key for one world, read out of the generator's own plan.

    `GroundTruth` above reads `world:{seed}` and is what the M2 trace is scored
    against. This reads the `WorldPlan` instead, for two reasons. The plan holds
    the facts and transmissions that the world graph does not — those live in the
    minds — so a falsehood's provenance can be followed in ground truth without
    consulting the referee's own walk, which is the walk being measured. And
    being pure data, it is reproducible from the seed alone with no graph
    involved, so a labelling disagreement shows up as a diff rather than as a
    mismatch against whatever happened to get written.

    The two agree on what they both know; `test_eval` asserts that on a real seed.
    """

    def __init__(self, plan: Any) -> None:
        self._plan = plan
        self._presences: dict[str, list] = {}
        for pr in plan.presences:
            self._presences.setdefault(pr.person, []).append(pr)
        self._facts_by_id = {f.id: f for f in plan.facts}
        self._facts_by_owner: dict[str, list] = {}
        for fact in plan.facts:
            self._facts_by_owner.setdefault(fact.owner, []).append(fact)
        self._transmission_by_fact = {tr.fact_id: tr for tr in plan.transmissions}
        # A fabrication is identified by the record it tells people to cite, so a
        # chain that bottoms out at that record came from that fabrication —
        # whether the record exists (pathology `none`) or does not (`broken_chain`).
        self._fab_by_src_fact = {f.src_fact_id: f for f in plan.fabrications}

    def culprit(self) -> str:
        return next(p.id for p in sorted(self._plan.people, key=lambda p: p.id)
                    if p.role == "culprit")

    def people(self) -> dict[str, str]:
        return {p.id: p.role for p in sorted(self._plan.people, key=lambda p: p.id)}

    # -- the world ----------------------------------------------------------

    def _route_coverage(self, person: str, place: str, t0: int, t1: int) -> int:
        """Minutes of `[t0, t1)` the person's true route spent at `place`."""
        segments = [
            (pr.t0, pr.t1) for pr in self._presences.get(person, []) if pr.place == place
        ]
        covered, _ = coverage(t0, t1, segments)
        return covered

    def true_of_world(self, *, subject: str, place: str, t0: int, t1: int,
                      modality: str) -> bool:
        """Did it actually happen, at the strength it was asserted with?"""
        covered = self._route_coverage(subject, place, t0, t1)
        if modality == THROUGHOUT:
            return covered >= t1 - t0
        return covered > 0

    # -- the speaker's own memory -------------------------------------------

    def witnessed_backing(self, *, speaker: str, subject: str, place: str,
                          t0: int, t1: int, modality: str) -> bool:
        """Does the speaker hold witnessed memory accounting for the claim?

        The same arithmetic the audit performs, over the plan instead of over
        the graph. Scoring the engine against this is what separates "did the
        audit read the memory correctly" from "was the claim true".
        """
        segments = [
            (f.t0, f.t1)
            for f in self._facts_by_owner.get(speaker, [])
            if f.src == WITNESSED and f.subject == subject and f.place == place
        ]
        covered, _ = coverage(t0, t1, segments)
        if modality == THROUGHOUT:
            return covered >= t1 - t0
        return covered > 0

    def witnessed_conflict(self, *, speaker: str, subject: str, place: str,
                           t0: int, t1: int) -> bool:
        """Does the speaker's witnessed memory put the subject somewhere else?"""
        return any(
            f.src == WITNESSED
            and f.subject == subject
            and f.place != place
            and overlaps(f.t0, f.t1, t0, t1)
            for f in self._facts_by_owner.get(speaker, [])
        )

    def any_overlapping_memory(self, *, speaker: str, subject: str,
                               t0: int, t1: int) -> bool:
        """Does the speaker hold anything at all overlapping, about the subject?

        Any source, any place — the gather step's whole result set. This is what
        spec 5.5's UNSUPPORTED row is about: "no overlapping facts at all".
        """
        return any(
            f.subject == subject and overlaps(f.t0, f.t1, t0, t1)
            for f in self._facts_by_owner.get(speaker, [])
        )

    # -- provenance, in ground truth ----------------------------------------

    def _chain_root(self, fact_id: str) -> tuple[str | None, str]:
        """Follow the plan's transmissions to the record a memory came from.

        Returns `(owner, fact_id)` of the earliest record the chain reaches.
        `owner` is None when the chain ends at a citation no mind holds, which
        is the generator's `broken_chain` plant: there is no agent to name, and
        the id is still returned so the caller can see which citation dangled.
        """
        seen: set[str] = set()
        current = fact_id
        for _ in range(_ROOT_DEPTH_CAP):
            fact = self._facts_by_id.get(current)
            if fact is None:
                return None, current
            transmission = self._transmission_by_fact.get(current)
            if transmission is None or transmission.src_fact_id in seen:
                return fact.owner, current
            seen.add(current)
            current = transmission.src_fact_id
        fact = self._facts_by_id.get(current)
        return (fact.owner if fact else None), current

    def _hearsay_support(self, *, speaker: str, subject: str, place: str,
                         t0: int, t1: int) -> list:
        """The speaker's secondhand memories bearing on the claim.

        Ordered `(t0, id)`, which is deliberately the order
        `referee/queries.py::HEARSAY_SUPPORT_FOR_CLAIM` returns them in. A
        claim can rest on several secondhand memories with *different* true
        origins, and `trace_claim` walks the first of them. If this key sorted
        them any other way it would name the root of a chain the referee did
        not follow, and the origin metric would count a disagreement where both
        sides were right about different chains — which is exactly what it did
        on seed 10074 before these two orderings were tied together.
        """
        return sorted(
            (
                f
                for f in self._facts_by_owner.get(speaker, [])
                if f.src == HEARSAY_SRC
                and f.subject == subject
                and f.place == place
                and overlaps(f.t0, f.t1, t0, t1)
            ),
            key=lambda f: (f.t0, f.id),
        )

    def _planted_by(self, *, speaker: str, subject: str, place: str,
                    t0: int, t1: int) -> Any | None:
        """The fabrication this exact claim voices, if the plan recorded one."""
        return next(
            (
                fab
                for fab in self._plan.fabrications
                if fab.by_person == speaker
                and subject == fab.by_person
                and fab.place == place
                and fab.t0 == t0
                and fab.t1 == t1
            ),
            None,
        )

    # -- the label ----------------------------------------------------------

    def label_claim(self, claim: dict) -> ClaimTruth:
        """Label one claim against the plan.

        Every condition is computed before any is consulted, then one ordered
        table selects the label — the same shape as the verdict decision table
        and the chain walk, and for the same reason (project rules, rule 3). A
        first-match scan here would let "it was planted" hide the fact that the
        planted span happens to be true, or the reverse.
        """
        speaker, subject = claim["speaker"], claim["subject"]
        place, t0, t1 = claim["place"], int(claim["t0"]), int(claim["t1"])
        modality = claim["modality"]

        happened = self.true_of_world(
            subject=subject, place=place, t0=t0, t1=t1, modality=modality
        )
        backed = self.witnessed_backing(
            speaker=speaker, subject=subject, place=place, t0=t0, t1=t1, modality=modality
        )
        planted = self._planted_by(
            speaker=speaker, subject=subject, place=place, t0=t0, t1=t1
        )
        conflicted = self.witnessed_conflict(
            speaker=speaker, subject=subject, place=place, t0=t0, t1=t1
        )
        anything = self.any_overlapping_memory(
            speaker=speaker, subject=subject, t0=t0, t1=t1
        )

        roots = [
            self._chain_root(f.id)
            for f in self._hearsay_support(
                speaker=speaker, subject=subject, place=place, t0=t0, t1=t1
            )
        ]
        chain_root = next((owner for owner, _ in roots if owner is not None), None)
        relayed_from_plant = next(
            (self._fab_by_src_fact[fid] for _, fid in roots if fid in self._fab_by_src_fact),
            None,
        )

        rows: list[tuple[bool, str, str | None]] = [
            (happened, TRUE_CLAIM, None),
            (planted is not None, DELIBERATE_FABRICATION, speaker),
            (
                relayed_from_plant is not None,
                RELAYED_FALSEHOOD,
                relayed_from_plant.by_person if relayed_from_plant else None,
            ),
            (True, HONEST_ERROR, None),
        ]
        label, origin = next((lab, org) for cond, lab, org in rows if cond)

        return ClaimTruth(
            label=label,
            true_of_world=happened,
            witnessed_backing=backed,
            witnessed_conflict=conflicted,
            any_overlapping_memory=anything,
            origin_agent=origin,
            chain_root=chain_root,
            hearsay_entries=len(roots),
        )

    # -- gaps ---------------------------------------------------------------

    def label_gap(self, *, subject: str, place: str, t0: int, t1: int) -> GapTruth:
        """Where the subject really was during a span nothing accounted for.

        A gap is a statement about the speaker's memory, not about the subject's
        route, so `AT_CLAIMED_PLACE` is not a false positive in the engine — it
        is a span the speaker could not account for and the subject spent there
        anyway. The three outcomes are reported separately rather than collapsed
        into one precision figure, because which of them counts as a hit depends
        on the question being asked.
        """
        at_place = self._route_coverage(subject, place, t0, t1)
        elsewhere = sum(
            1
            for pr in self._presences.get(subject, [])
            if pr.place != place and overlaps(pr.t0, pr.t1, t0, t1)
        )
        duration = t1 - t0

        rows = [
            (elsewhere > 0, GapTruth.ELSEWHERE),
            (at_place >= duration, GapTruth.AT_CLAIMED_PLACE),
            (True, GapTruth.IN_TRANSIT),
        ]
        verdict = next(v for cond, v in rows if cond)
        return GapTruth(verdict=verdict, t0=t0, t1=t1)
