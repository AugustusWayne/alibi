"""The decision table (spec 5.5), one test per verdict, against a real graph.

Each test hand-builds a mind and a case graph, runs the real audit, and asserts
both the verdict and what was materialized. The two rules v1 got wrong —
conflict beats support, and partial is not full — get their own tests, because
they are the two places where a plausible-looking implementation produces a
confidently wrong answer.

A verdict here describes grounding, not intent. UNSUPPORTED means nothing in
the speaker's own memory accounted for the claim. It does not mean the claim
is false, and nothing in this file should be read as saying so.
"""

from __future__ import annotations

import pytest

from backend.app.audit.engine import AuditEngine
from backend.app.audit.verdicts import (
    CONTRADICTED,
    HEARSAY,
    INDETERMINATE,
    SUPPORTED,
    UNSUPPORTED,
)
from backend.app.case.graph import CaseGraph, case_graph_name
from backend.app.minds.access import MindAccess, mind_graph_name

KITCHEN = "kitchen"
LIBRARY = "library"


@pytest.fixture
def world(db, scratch_seed, graphs):
    """A case with one claim, and the speaker's mind, both empty of facts.

    Returns a small builder so each test writes only the memories its own
    verdict needs.
    """
    seed = scratch_seed
    graphs(case_graph_name(seed))
    graphs(mind_graph_name(seed, "s1"))
    graphs(mind_graph_name(seed, "s2"))

    case = CaseGraph(db, seed)
    case.upsert_place(KITCHEN, "Kitchen")
    case.upsert_place(LIBRARY, "Library")
    case.upsert_suspect("s1", "Avery")
    case.upsert_suspect("s2", "Blake")

    mind = MindAccess(db, seed, "s1")
    mind.upsert_person("s1", "Avery")
    mind.upsert_place(KITCHEN, "Kitchen")
    mind.upsert_place(LIBRARY, "Library")

    class Builder:
        seed = None
        def claim(self, *, claim_id="c1", speaker="s1", subject="s1",
                  place=KITCHEN, t0=0, t1=15, modality="THROUGHOUT", turn=1,
                  relayed_from=None):
            case.ingest_claim(
                claim_id=claim_id, speaker=speaker, subject=subject, place=place,
                t0=t0, t1=t1, turn=turn, modality=modality, relayed_from=relayed_from,
            )
            return claim_id

        def witnessed(self, *, fact_id, subject="s1", place=KITCHEN, t0=0, t1=15):
            mind.write_fact(fact_id=fact_id, kind="saw", src="witnessed",
                            subject=subject, place=place, t0=t0, t1=t1, learned_at=t0)

        def hearsay(self, *, fact_id, subject="s1", place=KITCHEN, t0=0, t1=15,
                    learned_at=20, src_agent="s2", src_fact_id="f-remote"):
            mind.write_fact(fact_id=fact_id, kind="heard", src="hearsay",
                            subject=subject, place=place, t0=t0, t1=t1,
                            learned_at=learned_at)
            mind.write_transmission(fact_id=fact_id, transmission_id=f"tr-{fact_id}",
                                    tick=learned_at, src_agent=src_agent,
                                    src_fact_id=src_fact_id)

        def inferred(self, *, fact_id, subject="s1", place=KITCHEN, t0=0, t1=15):
            mind.write_fact(fact_id=fact_id, kind="did", src="inferred",
                            subject=subject, place=place, t0=t0, t1=t1, learned_at=t0)

        def engine_decide(self, *, claim_t0, claim_t1, evidence, modality="THROUGHOUT"):
            """Call the decision table directly, for degenerate windows that
            cannot be ingested at all."""
            from backend.app.audit.decide import decide

            return decide(
                claim_t0=claim_t0, claim_t1=claim_t1, modality=modality,
                evidence=evidence,
            )

    b = Builder()
    b.seed = seed
    b.case = case
    b.mind = mind
    b.engine = AuditEngine(db, seed)
    return b


# -- one test per verdict ----------------------------------------------------


def test_supported_when_witnessed_memory_covers_the_whole_claim(world):
    """THROUGHOUT [0,15) with a witnessed [0,15) at the same place."""
    world.claim(claim_id="c1", t0=0, t1=15)
    world.witnessed(fact_id="f1", t0=0, t1=15)

    r = world.engine.audit_claim("c1")

    assert r.verdict == SUPPORTED
    assert r.covered_minutes == 15
    assert r.gaps == []
    assert r.coverage == pytest.approx(1.0)
    stored = world.case.claim("c1")
    assert stored["verdict"] == SUPPORTED
    assert stored["uncovered"] == 0
    assert len(world.case.claim_evidence("c1")["supported_by"]) == 1


def test_unsupported_when_no_memory_overlaps_the_claim(world):
    """A memory outside the claim window is not evidence about it.

    UNSUPPORTED means nothing was found in the speaker's own memory. It is a
    statement about grounding, not about the speaker.
    """
    world.claim(claim_id="c1", t0=0, t1=15)
    world.witnessed(fact_id="f1", t0=40, t1=50)

    r = world.engine.audit_claim("c1")

    assert r.verdict == UNSUPPORTED
    assert r.evidence == []
    assert r.covered_minutes == 0
    assert world.case.claim("c1")["uncovered"] == 15


def test_contradicted_when_witnessed_memory_puts_subject_elsewhere(world):
    """The speaker's own memory has them in the library during the claim."""
    world.claim(claim_id="c1", place=KITCHEN, t0=0, t1=15)
    world.witnessed(fact_id="f1", place=LIBRARY, t0=5, t1=20)

    r = world.engine.audit_claim("c1")

    assert r.verdict == CONTRADICTED
    assert [e["fact_id"] for e in r.conflicting] == ["f1"]
    assert len(world.case.claim_evidence("c1")["conflicts_with"]) == 1


def test_indeterminate_when_witnessed_support_is_partial(world):
    """3 of 15 minutes witnessed. A 12-minute Gap, not a SUPPORTED claim."""
    world.claim(claim_id="c1", t0=0, t1=15)
    world.witnessed(fact_id="f1", t0=12, t1=15)

    r = world.engine.audit_claim("c1")

    assert r.verdict == INDETERMINATE
    assert r.covered_minutes == 3
    assert r.gaps == [(0, 12)]
    assert world.case.claim_evidence("c1")["gaps"] == [[0, 12]]
    assert world.case.claim("c1")["uncovered"] == 12


def test_hearsay_when_the_only_support_is_secondhand(world):
    """No witnessed memory, one hearsay memory that fits the claim.

    The transmission metadata survives onto the public Evidence shadow, so the
    referee can walk the chain later without the case graph holding the fact.
    """
    world.claim(claim_id="c1", t0=0, t1=15)
    world.hearsay(fact_id="f1", t0=0, t1=15, learned_at=20, src_agent="s2")

    r = world.engine.audit_claim("c1")

    assert r.verdict == HEARSAY
    assert [e["fact_id"] for e in r.hearsay_support] == ["f1"]
    assert r.hearsay_support[0]["heard_from"] == "s2"
    assert r.hearsay_support[0]["heard_tick"] == 20
    assert len(world.case.claim_evidence("c1")["supported_by"]) == 1


# -- the two rules v1 got wrong ----------------------------------------------


def test_conflict_beats_support_and_both_sets_are_retained(world):
    """Full witnessed support AND a conflicting witnessed memory.

    v1 returned `supported` here and hid the conflict, because it read
    evidence in a precedence order and stopped at the first match. The verdict
    must be CONTRADICTED, and *both* evidence sets must stay on the claim —
    conflict outranks support, it does not erase it.
    """
    world.claim(claim_id="c1", place=KITCHEN, t0=0, t1=15)
    world.witnessed(fact_id="f-support", place=KITCHEN, t0=0, t1=15)
    world.witnessed(fact_id="f-conflict", place=LIBRARY, t0=5, t1=10)

    r = world.engine.audit_claim("c1")

    assert r.verdict == CONTRADICTED
    assert [e["fact_id"] for e in r.supporting] == ["f-support"]
    assert [e["fact_id"] for e in r.conflicting] == ["f-conflict"]

    materialized = world.case.claim_evidence("c1")
    assert len(materialized["supported_by"]) == 1, "support must survive a contradiction"
    assert len(materialized["conflicts_with"]) == 1
    assert world.case.claim("c1")["verdict"] == CONTRADICTED


def test_partial_is_not_full_even_when_several_facts_overlap(world):
    """Two witnessed facts overlapping each other, covering 10 of 15 minutes.

    Unmerged these sum to 15 and would pass a `covered >= duration` check,
    promoting a claim with a 5-minute hole to SUPPORTED. Merged they cover 10.
    """
    world.claim(claim_id="c1", t0=0, t1=15)
    world.witnessed(fact_id="f1", t0=0, t1=8)
    world.witnessed(fact_id="f2", t0=3, t1=10)

    r = world.engine.audit_claim("c1")

    assert r.covered_minutes == 10, "spans must be merged before summing"
    assert r.verdict == INDETERMINATE
    assert r.gaps == [(10, 15)]


def test_at_some_point_is_satisfied_by_any_overlap(world):
    """The weaker modality. The same 3-of-15 evidence that is INDETERMINATE
    for THROUGHOUT is SUPPORTED for AT_SOME_POINT, and gets no Gap nodes."""
    world.claim(claim_id="c1", t0=0, t1=15, modality="AT_SOME_POINT")
    world.witnessed(fact_id="f1", t0=12, t1=15)

    r = world.engine.audit_claim("c1")

    assert r.verdict == SUPPORTED
    assert world.case.claim_evidence("c1")["gaps"] == []


def test_inferred_support_alone_is_indeterminate(world):
    """An inferred memory is neither witnessed nor secondhand.

    It cannot ground a claim and it cannot refute one, so it lands in the
    decision table's last row rather than being silently counted as support.
    """
    world.claim(claim_id="c1", t0=0, t1=15)
    world.inferred(fact_id="f1", t0=0, t1=15)

    r = world.engine.audit_claim("c1")

    assert r.verdict == INDETERMINATE
    assert r.covered_minutes == 0


def test_witnessed_support_outranks_hearsay_support(world):
    """With both, the claim is SUPPORTED on the witnessed memory, not HEARSAY."""
    world.claim(claim_id="c1", t0=0, t1=15)
    world.witnessed(fact_id="f-seen", t0=0, t1=15)
    world.hearsay(fact_id="f-heard", t0=0, t1=15)

    r = world.engine.audit_claim("c1")

    assert r.verdict == SUPPORTED


def test_touching_memory_does_not_support_a_claim(world):
    """A witnessed fact over [15,30) shares no tick with a claim over [0,15).

    The half-open contract means it is not evidence about this claim at all,
    so the verdict is UNSUPPORTED, not partial support.
    """
    world.claim(claim_id="c1", t0=0, t1=15)
    world.witnessed(fact_id="f1", t0=15, t1=30)

    r = world.engine.audit_claim("c1")

    assert r.evidence == []
    assert r.verdict == UNSUPPORTED


def test_audit_never_invents_a_link(world):
    """An UNSUPPORTED claim gets no evidence edges of any kind.

    The audit materializes only what it proved (project rules, rule 5). A claim
    nothing accounts for must end up with an empty path, not a manufactured one.
    """
    world.claim(claim_id="c1", t0=0, t1=15)

    world.engine.audit_claim("c1")

    ev = world.case.claim_evidence("c1")
    assert ev["supported_by"] == []
    assert ev["conflicts_with"] == []
    assert ev["gaps"] == []


def test_every_verdict_is_reachable_in_one_case(world):
    """All five states, one case graph, one audit pass.

    This is the milestone gate in a single test: the engine must produce every
    row of the decision table, not just the easy ones.
    """
    world.claim(claim_id="sup", subject="s1", place=KITCHEN, t0=0, t1=10, turn=1)
    world.witnessed(fact_id="f-sup", subject="s1", place=KITCHEN, t0=0, t1=10)

    world.claim(claim_id="uns", subject="p-uns", place=KITCHEN, t0=20, t1=30, turn=2)

    world.claim(claim_id="con", subject="p-con", place=KITCHEN, t0=40, t1=50, turn=3)
    world.witnessed(fact_id="f-con", subject="p-con", place=LIBRARY, t0=40, t1=50)

    world.claim(claim_id="ind", subject="p-ind", place=KITCHEN, t0=60, t1=75, turn=4)
    world.witnessed(fact_id="f-ind", subject="p-ind", place=KITCHEN, t0=60, t1=63)

    world.claim(claim_id="hea", subject="p-hea", place=KITCHEN, t0=80, t1=90, turn=5)
    world.hearsay(fact_id="f-hea", subject="p-hea", place=KITCHEN, t0=80, t1=90,
                  learned_at=95)

    results = {r.claim_id: r.verdict for r in world.engine.audit_all()}

    assert results == {
        "sup": SUPPORTED,
        "uns": UNSUPPORTED,
        "con": CONTRADICTED,
        "ind": INDETERMINATE,
        "hea": HEARSAY,
    }


# -- degenerate claim windows ------------------------------------------------


def test_a_zero_length_claim_is_refused_rather_than_judged(world):
    """`[t, t)` is the empty interval, so there is nothing to ground.

    Before this test the audit returned SUPPORTED for a zero-length claim
    whenever any witnessed fact straddled the instant, because the modality
    check `covered >= duration` reduces to `0 >= 0`. That is the same
    vacuous-arithmetic bug class as summing unmerged spans: a confident
    verdict over zero examined minutes.

    A claim about no ticks is malformed input, not an epistemic state, so it
    raises rather than being assigned one of the five verdicts.
    """
    with pytest.raises(ValueError, match="zero-length|t0 < t1"):
        world.engine_decide(claim_t0=10, claim_t1=10, evidence=[])


def test_an_inverted_claim_is_refused(world):
    """`[20, 10)` is not an interval at all. Same reasoning."""
    with pytest.raises(ValueError, match="zero-length|t0 < t1"):
        world.engine_decide(claim_t0=20, claim_t1=10, evidence=[])


def test_a_zero_length_claim_cannot_be_ingested(world):
    """The case graph refuses to store one, so the audit never meets it.

    Validating at ingest keeps the graph the system of record for
    well-formed claims only; `decide` raising is the backstop.
    """
    with pytest.raises(ValueError, match="zero-length|t0 < t1"):
        world.claim(claim_id="bad", t0=10, t1=10)


def test_a_one_tick_claim_is_the_smallest_auditable_one(world):
    """`[10, 11)` contains exactly tick 10 and audits normally.

    The boundary next to the refusal: one tick is a real claim, zero is not.
    """
    world.claim(claim_id="c1", t0=10, t1=11)
    world.witnessed(fact_id="f1", t0=10, t1=11)

    r = world.engine.audit_claim("c1")

    assert r.verdict == SUPPORTED
    assert r.covered_minutes == 1
    assert r.coverage == pytest.approx(1.0)
