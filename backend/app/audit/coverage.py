"""How much of a claimed interval the evidence actually accounts for.

Interval union is awkward in the OpenCypher subset and trivial here, so this
one step is deterministic Python. It is arithmetic, not judgement, and the
result is written back into the graph, so the graph stays the system of record.
"""

from __future__ import annotations

Span = tuple[int, int]


def coverage(claim_t0: int, claim_t1: int, intervals: list[Span]) -> tuple[int, list[Span]]:
    """Return `(covered_minutes, gaps)` for `[claim_t0, claim_t1)`.

    `intervals` are the witnessed, same-place facts overlapping the claim
    window, clipped here to the claim. They may overlap each other, so they
    MUST be merged before summing: two facts covering 21:00-21:10 and
    21:05-21:15 cover 15 minutes, not 20. Summing unmerged spans can push
    coverage above the claim length and silently promote a partially-supported
    claim to SUPPORTED, which is the exact bug class this module exists to
    remove.

    `gaps` are the uncovered half-open spans, ascending and disjoint.
    `covered + sum(gap lengths) == claim_t1 - claim_t0` always holds.
    """
    spans = sorted((max(a, claim_t0), min(b, claim_t1)) for a, b in intervals)
    spans = [(a, b) for a, b in spans if a < b]  # drop empty / out-of-window
    merged: list[Span] = []
    for a, b in spans:
        if merged and a <= merged[-1][1]:  # touching or overlapping
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    gaps: list[Span] = []
    cursor = claim_t0
    for a, b in merged:
        if a > cursor:
            gaps.append((cursor, a))
        cursor = b
    if cursor < claim_t1:
        gaps.append((cursor, claim_t1))
    return sum(b - a for a, b in merged), gaps
