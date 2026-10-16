"""The four boundary cases of the time contract (spec 4.0).

All intervals are half-open [t0, t1).

  overlap:    a and b overlap iff  a.t0 < b.t1 AND b.t0 < a.t1   (strict)
  travel:     A over [a.t0, a.t1) then B over [b.t0, b.t1) is feasible
              iff  a.t1 + travel(A, B) <= b.t0

Implemented in M1 by `backend/app/audit/time_contract.py`. These were four
`xfail(strict=True)` cases scaffolded in M0; the markers came off the moment
the module landed, which is what strict was for — the suite went red on XPASS
rather than letting a passing test hide behind an "expected to fail" label.
The assertions below are unchanged from M0.
"""

from __future__ import annotations


def _overlaps():
    from backend.app.audit.time_contract import overlaps

    return overlaps


def _travel_feasible():
    from backend.app.audit.time_contract import travel_feasible

    return travel_feasible


def test_journey_with_exactly_enough_time_is_feasible():
    """Leaves A at tick 10, walk is 5, arrives B at 15. 10 + 5 <= 15."""
    travel_feasible = _travel_feasible()
    assert travel_feasible(a_t1=10, b_t0=15, travel_minutes=5) is True


def test_journey_one_tick_short_is_impossible():
    """Same journey, walk is 6. 10 + 6 = 16 > 15, so the claim does not fit."""
    travel_feasible = _travel_feasible()
    assert travel_feasible(a_t1=10, b_t0=15, travel_minutes=6) is False


def test_intervals_touching_at_a_point_do_not_overlap():
    """[0,10) and [10,20) share no tick. v1's inclusive compare said they did."""
    overlaps = _overlaps()
    assert overlaps(0, 10, 10, 20) is False


def test_intervals_overlapping_by_one_tick_do_overlap():
    """[0,10) and [9,20) share exactly tick 9."""
    overlaps = _overlaps()
    assert overlaps(0, 10, 9, 20) is True
