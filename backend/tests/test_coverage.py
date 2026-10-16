"""All eleven coverage cases from the spec 5.4 table, plus the invariant.

`coverage()` is the arithmetic the verdict rests on. Its one dangerous failure
mode is summing witnessed spans without merging them first: two facts covering
[0,10) and [5,15) sum to 20 minutes over a 15-minute claim, which pushes
coverage past the claim length and silently promotes a partially-supported
claim to SUPPORTED. The `overlapping` case and the property test below both
exist to catch exactly that.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from backend.app.audit.coverage import coverage

# (name, claim_t0, claim_t1, spans, expected_covered, expected_gaps)
# Transcribed from the table in spec 5.4. Do not retune these to match code.
CASES = [
    ("full", 0, 15, [(0, 15)], 15, []),
    ("partial tail", 0, 15, [(12, 15)], 3, [(0, 12)]),
    ("union to full", 0, 15, [(0, 8), (8, 15)], 15, []),
    ("middle gap", 0, 15, [(0, 5), (10, 15)], 10, [(5, 10)]),
    ("no evidence", 0, 15, [], 0, [(0, 15)]),
    ("overlapping", 0, 15, [(0, 10), (5, 15)], 15, []),
    ("fact overruns claim", 5, 10, [(0, 20)], 5, []),
    ("two gaps", 0, 20, [(5, 10)], 5, [(0, 5), (10, 20)]),
    ("unsorted input", 0, 15, [(10, 15), (0, 5)], 10, [(5, 10)]),
    ("touching spans", 0, 15, [(0, 7), (7, 15)], 15, []),
    ("entirely outside", 0, 15, [(20, 25)], 0, [(0, 15)]),
]


@pytest.mark.parametrize(
    ("claim_t0", "claim_t1", "spans", "want_covered", "want_gaps"),
    [c[1:] for c in CASES],
    ids=[c[0] for c in CASES],
)
def test_spec_table(claim_t0, claim_t1, spans, want_covered, want_gaps):
    covered, gaps = coverage(claim_t0, claim_t1, spans)
    assert covered == want_covered
    assert gaps == want_gaps


def test_overlapping_spans_do_not_exceed_the_claim():
    """The specific bug this rewrite exists to remove.

    Unmerged, (0,10) + (5,15) sums to 20 over a 15-tick claim. A coverage
    figure above the claim length would satisfy any `covered >= duration`
    test for SUPPORTED while a third of the claim went unexamined.
    """
    covered, gaps = coverage(0, 15, [(0, 10), (5, 15)])
    assert covered == 15
    assert covered <= 15 - 0
    assert gaps == []


def test_gaps_are_half_open_and_disjoint():
    """Gaps are [t0, t1) spans in ascending order and never touch each other."""
    _, gaps = coverage(0, 30, [(5, 10), (20, 25)])
    assert gaps == [(0, 5), (10, 20), (25, 30)]
    for (_, a_t1), (b_t0, _) in zip(gaps, gaps[1:], strict=False):
        assert a_t1 < b_t0


# ---------------------------------------------------------------------------
# The invariant. This is the property that breaks when spans are summed
# without merging: the covered minutes and the gap minutes must exactly
# partition the claim, with nothing double-counted and nothing lost.

ticks = st.integers(min_value=0, max_value=300)


@st.composite
def claim_and_spans(draw):
    t0 = draw(ticks)
    t1 = draw(st.integers(min_value=t0 + 1, max_value=301))
    spans = draw(
        st.lists(
            st.tuples(ticks, ticks).map(lambda ab: (min(ab), max(ab))),
            max_size=12,
        )
    )
    return t0, t1, spans


@given(claim_and_spans())
def test_covered_plus_gaps_equals_claim_duration(case):
    claim_t0, claim_t1, spans = case
    covered, gaps = coverage(claim_t0, claim_t1, spans)
    assert covered + sum(b - a for a, b in gaps) == claim_t1 - claim_t0
    assert 0 <= covered <= claim_t1 - claim_t0
    for a, b in gaps:
        assert claim_t0 <= a < b <= claim_t1
