"""The decision table (spec 5.5) — the only place a verdict is produced.

Two structural rules, which are what this module is shaped around:

**Gather all evidence, then decide.** `decide()` receives the complete evidence
set and computes every condition in the table before selecting any verdict.
There is no first-match scan: `_CONDITIONS` below is evaluated in full, and
only then is the highest-precedence true row taken. This matters because v1
read evidence in a precedence order and returned on the first match, which let
a single supporting memory mask a conflicting one that was never reached.

**Conflict beats support.** A claim with both supporting and conflicting
witnessed memory is CONTRADICTED, and both evidence sets are kept on the
claim. Outranking is not erasure.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.app.audit.coverage import Span, coverage
from backend.app.audit.verdicts import (
    AT_SOME_POINT,
    CONTRADICTED,
    HEARSAY,
    HEARSAY_SRC,
    INDETERMINATE,
    SUPPORTED,
    THROUGHOUT,
    UNSUPPORTED,
    WITNESSED,
)


@dataclass(frozen=True)
class Decision:
    """Everything the audit proved about one claim, before anything is written.

    `supporting` and `conflicting` are both populated regardless of the
    verdict, so the materializer can keep both sets on a CONTRADICTED claim.
    """

    verdict: str
    covered_minutes: int
    gaps: list[Span]
    supporting: list[dict] = field(default_factory=list)
    conflicting: list[dict] = field(default_factory=list)
    hearsay_support: list[dict] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)
    reason: str = ""

    @property
    def duration(self) -> int:
        return self.covered_minutes + sum(b - a for a, b in self.gaps)

    @property
    def coverage_fraction(self) -> float:
        """Covered share of the claim, 0.0 to 1.0. Zero-length claims are 0.0."""
        return self.covered_minutes / self.duration if self.duration else 0.0

    @property
    def uncovered_minutes(self) -> int:
        return sum(b - a for a, b in self.gaps)

    @property
    def materializes_gaps(self) -> bool:
        """Whether the uncovered spans become `Gap` nodes in the case graph.

        Spec 5.5 grants `Gap` nodes to the partial-support row: a claim with
        *some* witnessed backing and a hole in it is the detective's best
        question, and Q8 counts those holes. A wholly UNSUPPORTED claim is
        already its own signal and gets no Gap nodes — but its `uncovered`
        property still records the full span, so nothing is lost.
        """
        return self.verdict == INDETERMINATE and bool(self.supporting)


def decide(
    *,
    claim_t0: int,
    claim_t1: int,
    modality: str,
    evidence: list[dict],
) -> Decision:
    """Apply the decision table to the complete evidence set for one claim.

    `evidence` is every row Q2 returned — overlapping facts about the subject,
    same-place and different-place together. It must be the whole set; passing
    a filtered or truncated set is the one way to make this function return a
    verdict the evidence did not earn.

    Raises `ValueError` unless `claim_t0 < claim_t1`. Under the half-open
    contract `[t, t)` is the empty interval, so a zero-length claim is about
    no ticks at all and there is nothing for evidence to ground. Judging one
    anyway is not harmless: the THROUGHOUT check `covered >= duration`
    collapses to `0 >= 0`, so any straddling memory would return SUPPORTED
    over zero examined minutes. That is the same vacuous arithmetic as
    summing unmerged spans. A malformed window is a data error, not an
    epistemic state, so it is raised loudly rather than given one of the five
    verdicts (project rules, rule 8).
    """
    if claim_t0 >= claim_t1:
        raise ValueError(
            f"claim window [{claim_t0}, {claim_t1}) is zero-length or inverted; "
            f"a claim must satisfy t0 < t1 to be about any tick at all"
        )
    witnessed = [e for e in evidence if e["src"] == WITNESSED]
    supporting = [e for e in witnessed if e["same_place"]]
    conflicting = [e for e in witnessed if not e["same_place"]]
    hearsay_support = [e for e in evidence if e["src"] == HEARSAY_SRC and e["same_place"]]

    covered, gaps = coverage(claim_t0, claim_t1, [(e["t0"], e["t1"]) for e in supporting])
    duration = claim_t1 - claim_t0

    # Every condition is computed here, before any of them is consulted.
    has_conflict = bool(conflicting)
    no_evidence = not evidence
    modality_satisfied = bool(supporting) and (
        covered >= duration if modality == THROUGHOUT else True
    )
    partial_support = (
        bool(supporting) and not modality_satisfied and modality in (THROUGHOUT, AT_SOME_POINT)
    )
    only_hearsay = not supporting and bool(hearsay_support)

    # The table, in precedence order. Conditions are already evaluated; this
    # selects among known booleans rather than short-circuiting a scan.
    rows: list[tuple[bool, str, str]] = [
        (has_conflict, CONTRADICTED, "witnessed memory places the subject elsewhere"),
        (no_evidence, UNSUPPORTED, "no memory overlapping the claim was found"),
        (modality_satisfied, SUPPORTED, "witnessed memory satisfies the claim's modality"),
        (partial_support, INDETERMINATE, "witnessed support covers only part of the claim"),
        (only_hearsay, HEARSAY, "the only support for the claim is secondhand"),
        (True, INDETERMINATE, "the evidence found neither grounds nor refutes the claim"),
    ]
    verdict, reason = next((v, why) for cond, v, why in rows if cond)

    return Decision(
        verdict=verdict,
        covered_minutes=covered,
        gaps=gaps,
        supporting=supporting,
        conflicting=conflicting,
        hearsay_support=hearsay_support,
        evidence=evidence,
        reason=reason,
    )
