"""Scoring, as pure arithmetic over records. No database, no Cypher, no LLM.

Everything the report prints is computed here from the plain records the
harness returns, so each figure can be tested against a handful of rows
without a graph server. That separation is not tidiness: a metric that can
only be checked by running the whole pipeline is a metric nobody checks.

**Two different questions, deliberately not merged.** The engine's only
ungrounded signal is `UNSUPPORTED ∪ CONTRADICTED` (spec 8.2). Scoring that
signal against *whether the speaker's own memory backed the claim* measures
grounding detection — what the engine claims to do. Scoring the same signal
against *whether the claim was true* measures falsehood detection — what the
engine explicitly does not claim to do. The gap between the two numbers is the
"grounded ≠ true" result the project exists to report, so they are computed
separately and reported separately, never averaged.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from backend.app.audit.verdicts import ALL_VERDICTS, CONTRADICTED, UNSUPPORTED
from backend.app.referee.ground_truth import ALL_LABELS, GAP_TRUTHS, TRUE_CLAIM, GapTruth
from backend.app.referee.terminals import (
    CHAIN_BROKEN,
    CHAIN_TEMPORAL_VIOLATION,
    ORIGIN_TERMINALS,
)

UNGROUNDED_VERDICTS = (UNSUPPORTED, CONTRADICTED)
"""The engine's ungrounded signal, named by spec 8.2. Not a falsehood signal."""


@dataclass(frozen=True)
class Confusion:
    """The raw matrix. Counts only — no normalisation, no rounding, no colour.

    Rows are the five verdicts, columns the four labels, both in their declared
    order and both complete: a verdict that never arose keeps its row at zero
    rather than vanishing, because an absent row and a zero row mean different
    things and the reader must be able to tell which they are looking at.
    """

    cells: dict[tuple[str, str], int]
    verdicts: tuple[str, ...] = ALL_VERDICTS
    labels: tuple[str, ...] = ALL_LABELS

    @property
    def total(self) -> int:
        return sum(self.cells.values())

    def row_total(self, verdict: str) -> int:
        return sum(self.cells[(verdict, lab)] for lab in self.labels)

    def column_total(self, label: str) -> int:
        return sum(self.cells[(v, label)] for v in self.verdicts)


def confusion(records: list) -> Confusion:
    """Engine verdict x ground-truth label, over every scored claim."""
    counted = Counter((r.verdict, r.label) for r in records)
    cells = {(v, lab): counted.get((v, lab), 0) for v in ALL_VERDICTS for lab in ALL_LABELS}
    unknown = set(counted) - set(cells)
    if unknown:
        # A verdict or label outside the declared enums is a contract break, not
        # a row to add quietly: the matrix dimensions come from the spec.
        raise ValueError(f"verdict/label pairs outside the declared enums: {sorted(unknown)}")
    return Confusion(cells=cells)


@dataclass(frozen=True)
class PR:
    """Precision, recall and their counts for one binary question."""

    question: str
    predicted_positive: str
    actual_positive: str
    tp: int
    fp: int
    fn: int
    tn: int

    @property
    def precision(self) -> float | None:
        """None when nothing was predicted positive — undefined, not zero."""
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else None

    @property
    def recall(self) -> float | None:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else None

    @property
    def f1(self) -> float | None:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p and r else None


def _pr(records: list, *, question: str, predicted_positive: str, actual_positive: str,
        predict, actual) -> PR:
    tallies = Counter((bool(predict(r)), bool(actual(r))) for r in records)
    return PR(
        question=question,
        predicted_positive=predicted_positive,
        actual_positive=actual_positive,
        tp=tallies[(True, True)],
        fp=tallies[(True, False)],
        fn=tallies[(False, True)],
        tn=tallies[(False, False)],
    )


def grounding_pr(records: list) -> PR:
    """Full-coverage detection: does the signal fire whenever memory falls short?

    The strict reading of grounding, and the pessimistic one. Its denominator is
    every claim the speaker's own witnessed memory does not *fully* account for,
    which includes every partially-covered claim. The engine sends those to
    INDETERMINATE with their gaps attached rather than calling them ungrounded,
    so recall here is low by construction and `backing_by_verdict` shows exactly
    where it goes. A high number here would mean the engine was reporting
    partial support as ungrounded, which is the v1 behaviour spec 5.5 exists to
    remove — so this figure being low is the decision table working.

    `strict_grounding_pr` below asks the apples-to-apples question instead.
    """
    return _pr(
        records,
        question="full-coverage detection (memory does not fully cover the claim)",
        predicted_positive="verdict in (UNSUPPORTED, CONTRADICTED)",
        actual_positive="the speaker's own witnessed memory does not fully account "
        "for the claim",
        predict=lambda r: r.verdict in UNGROUNDED_VERDICTS,
        actual=lambda r: not r.witnessed_backing,
    )


def strict_grounding_pr(records: list) -> PR:
    """Grounding detection, scored against what the two verdicts actually mean.

    The engine measured against what it measures. `UNSUPPORTED` is spec 5.5's
    "no overlapping facts at all" — any source, any place — and `CONTRADICTED`
    is witnessed memory placing the subject elsewhere. Those two conditions,
    and not a looser one, are this metric's denominator.

    The truth side is read from the generator's plan rather than from the audit,
    so agreement here says the graph writes, the gather query, the interval
    merge and the decision table all agree with the world that was built. This
    is the grounding number to compare against `falsehood_pr`: both score the
    same engine signal, against two different truths, and the distance between
    them is the "grounded is not true" result.
    """
    return _pr(
        records,
        question="grounding detection (what UNSUPPORTED and CONTRADICTED mean)",
        predicted_positive="verdict in (UNSUPPORTED, CONTRADICTED)",
        actual_positive="the speaker holds nothing overlapping about the subject, "
        "or witnessed memory places them elsewhere",
        predict=lambda r: r.verdict in UNGROUNDED_VERDICTS,
        actual=lambda r: r.witnessed_conflict or not r.any_overlapping_memory,
    )


def falsehood_pr(records: list) -> PR:
    """Does an ungrounded verdict mean the claim was false?

    The engine has no falsehood detector and does not claim one, so this number
    is expected to be worse than the one above. The distance between them is
    the result, not a defect to close.
    """
    return _pr(
        records,
        question="falsehood detection",
        predicted_positive="verdict in (UNSUPPORTED, CONTRADICTED)",
        actual_positive="the claim did not match the world",
        predict=lambda r: r.verdict in UNGROUNDED_VERDICTS,
        actual=lambda r: r.label != TRUE_CLAIM,
    )


@dataclass(frozen=True)
class OriginAccuracy:
    """How often the chain named the agent the plan says an account began with.

    `resolved` counts chains that reached one of the three origin states.
    `chain_broken` and `chain_temporal_violation` are reported beside the
    accuracy and never folded into it: spec 5.7 says `CHAIN_BROKEN` is
    ambiguous and is not an origin, so counting it as a miss would assert the
    chain was wrong when what happened is that it could not tell.
    """

    subset: int
    resolved: int
    correct: int
    misnamed: int
    unresolved: int
    chains_total: int
    chain_broken: int
    chain_temporal_violation: int
    terminals: dict[str, int]

    @property
    def accuracy_over_resolved(self) -> float | None:
        return self.correct / self.resolved if self.resolved else None

    @property
    def accuracy_over_subset(self) -> float | None:
        """Credit only for chains that both resolved and named the right agent."""
        return self.correct / self.subset if self.subset else None

    @property
    def chain_broken_rate(self) -> float | None:
        return self.chain_broken / self.chains_total if self.chains_total else None

    @property
    def temporal_violation_rate(self) -> float | None:
        return (
            self.chain_temporal_violation / self.chains_total if self.chains_total else None
        )


def origin_accuracy(records: list) -> OriginAccuracy:
    """Origin identification over the claims where ground truth names an origin.

    The subset is the claims the plan says began as a planted account somewhere
    other than the speaker, and which the engine actually traced. A claim the
    engine never traced is not a wrong answer and is excluded from the subset
    rather than scored as a miss; `chains_total` below counts every chain the
    run produced, so the rates are over all of them.
    """
    traced = [r for r in records if r.chain_terminal is not None]
    subset = [r for r in traced if r.truth_origin is not None]
    resolved = [r for r in subset if r.chain_terminal in ORIGIN_TERMINALS]
    correct = [r for r in resolved if r.chain_origin == r.truth_origin]
    return OriginAccuracy(
        subset=len(subset),
        resolved=len(resolved),
        correct=len(correct),
        misnamed=len(resolved) - len(correct),
        unresolved=len(subset) - len(resolved),
        chains_total=len(traced),
        chain_broken=sum(1 for r in traced if r.chain_terminal == CHAIN_BROKEN),
        chain_temporal_violation=sum(
            1 for r in traced if r.chain_terminal == CHAIN_TEMPORAL_VIOLATION
        ),
        terminals=dict(Counter(r.chain_terminal for r in traced)),
    )


def multi_chain_claims(records: list) -> int:
    """Claims resting on more than one secondhand memory, so having more than
    one chain.

    `trace_claim` walks the first and the eval scores that one, so this is the
    size of the choice being made. Reported rather than left implicit.
    """
    return sum(1 for r in records if r.truth_hearsay_entries > 1)


def chain_root_accuracy(records: list) -> PR:
    """Did the chain reach whoever first held the memory, over every chain?

    Wider than `origin_accuracy`: that one asks about planted accounts, this
    one asks about honest ones too, where the right answer is the first-hand
    witness. Reported as a hit rate in PR's shape so the counts stay visible.

    Scored against the root of the same secondhand memory the referee walked:
    a claim with several of them has several chains, each with its own correct
    root, and comparing one chain against another's root would manufacture a
    disagreement out of two right answers.
    """
    traced = [
        r for r in records if r.chain_terminal in ORIGIN_TERMINALS and r.truth_chain_root
    ]
    return _pr(
        traced,
        question="chain root identification",
        predicted_positive="the chain named an agent",
        actual_positive="that agent is who first held the memory, per the plan",
        predict=lambda r: r.chain_origin is not None,
        actual=lambda r: r.chain_origin == r.truth_chain_root,
    )


@dataclass(frozen=True)
class GapPrecision:
    """What was really happening during the spans the audit left unaccounted.

    Three outcomes, counted separately because which of them is a "hit" depends
    on the question. A gap is a statement about the *speaker's memory*, not
    about the subject's route, so a gap the subject spent at the claimed place
    is not an engine error — nobody accounted for it and it is still the right
    thing to ask about. `strict` answers spec 8.2's question as written; `loose`
    answers the weaker one, which is whether the subject was verifiably not
    where the claim put them.
    """

    total: int
    elsewhere: int
    in_transit: int
    at_claimed_place: int

    @property
    def strict(self) -> float | None:
        """Share of gaps where the true route places the subject somewhere else."""
        return self.elsewhere / self.total if self.total else None

    @property
    def loose(self) -> float | None:
        """Share where the subject was demonstrably not at the claimed place."""
        return (self.elsewhere + self.in_transit) / self.total if self.total else None


def gap_precision(gaps: list) -> GapPrecision:
    """Score every materialized `Gap` against the subject's true route."""
    counted = Counter(g.truth for g in gaps)
    unknown = set(counted) - set(GAP_TRUTHS)
    if unknown:
        raise ValueError(f"gap outcomes outside the declared set: {sorted(unknown)}")
    return GapPrecision(
        total=len(gaps),
        elsewhere=counted[GapTruth.ELSEWHERE],
        in_transit=counted[GapTruth.IN_TRANSIT],
        at_claimed_place=counted[GapTruth.AT_CLAIMED_PLACE],
    )


@dataclass(frozen=True)
class GeneratorYield:
    """What the generator threw out, and what it produced that cannot be scored.

    Spec 8.4.2 asks for the rejection rate. The generator rejects nothing: the
    floor plan is connected by a spanning chain and every route pays its travel
    in full at construction, so there is no retry loop and no discarded world
    to count — `rejected` is structurally zero and is reported anyway, because a
    zero that is explained is data and a missing row is not.

    What does vary is `without_relayed_fabrication`: a seed where the culprit
    never shared a room with an honest suspect after the incident has nobody to
    tell, so the planted account is never relayed and that seed contributes no
    chain to trace. Those seeds are reported, kept in the denominators, and
    never redrawn.
    """

    seeds: int
    rejected: int
    fabrications: int
    relayed_fabrications: int
    without_relayed_fabrication: int
    seeds_without_relay: tuple[int, ...]

    @property
    def rejection_rate(self) -> float | None:
        return self.rejected / (self.seeds + self.rejected) if self.seeds else None

    @property
    def unrelayed_rate(self) -> float | None:
        return self.without_relayed_fabrication / self.seeds if self.seeds else None


def generator_yield(runs: list) -> GeneratorYield:
    """Aggregate what the generator produced across the frozen seeds."""
    unrelayed = tuple(sorted(r.seed for r in runs if r.relayed_fabrications == 0))
    return GeneratorYield(
        seeds=len(runs),
        rejected=sum(r.rejected for r in runs),
        fabrications=sum(r.fabrications for r in runs),
        relayed_fabrications=sum(r.relayed_fabrications for r in runs),
        without_relayed_fabrication=len(unrelayed),
        seeds_without_relay=unrelayed,
    )


def verdict_tally(records: list) -> dict[str, int]:
    """Every verdict, with the ones that never arose kept at zero."""
    counted = Counter(r.verdict for r in records)
    return {v: counted.get(v, 0) for v in ALL_VERDICTS}


def label_tally(records: list) -> dict[str, int]:
    counted = Counter(r.label for r in records)
    return {lab: counted.get(lab, 0) for lab in ALL_LABELS}


def backing_by_verdict(records: list) -> dict[str, tuple[int, int]]:
    """Per verdict, `(backed, unbacked)` by the speaker's own witnessed memory.

    The breakdown behind `grounding_pr`'s recall. Without it, HEARSAY and
    INDETERMINATE claims — unbacked by witnessed memory but not reported as
    ungrounded — would sit inside one recall number with no way to see them.
    """
    out = {}
    for verdict in ALL_VERDICTS:
        rows = [r for r in records if r.verdict == verdict]
        out[verdict] = (
            sum(1 for r in rows if r.witnessed_backing),
            sum(1 for r in rows if not r.witnessed_backing),
        )
    return out
