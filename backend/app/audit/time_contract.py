"""The time contract (spec 4.0), written down exactly once.

Tick = integer minutes since 18:00, range 0 to 300.

**All intervals are half-open `[t0, t1)`.** Present over `[t0, t1)` means
present from `t0` up to but not including `t1`. Every temporal comparison in
the audit path goes through this module so the half-open convention cannot
drift between Python and Cypher. The Cypher predicates in `queries.py` are the
same two inequalities, written out inline because a Cypher string cannot call a
Python function; if you change one, change both.

v1 used inclusive comparisons and reported adjacent intervals as overlapping.
The boundary tests in `test_time_contract.py` are what stop that returning.
"""

from __future__ import annotations


def overlaps(a0: int, a1: int, b0: int, b1: int) -> bool:
    """Do `[a0, a1)` and `[b0, b1)` share at least one tick?

    Strict inequalities both sides. `[0,10)` and `[10,20)` touch at a point and
    share no tick, so they do not overlap. `[0,10)` and `[9,20)` share tick 9
    and do.
    """
    return a0 < b1 and b0 < a1


def travel_feasible(a_t1: int, b_t0: int, travel_minutes: int) -> bool:
    """Could someone leave A at `a_t1` and be at B by `b_t0`?

    Feasible iff `a_t1 + travel(A, B) <= b_t0`; impossible iff the slack
    `b_t0 - a_t1` is strictly less than the walk. Equality is feasible — a
    journey with exactly enough time fits.
    """
    return a_t1 + travel_minutes <= b_t0
