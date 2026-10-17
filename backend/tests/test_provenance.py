"""The cross-graph provenance trace (spec 5.7), all seven terminal states.

Each test builds the minds by hand so the chain shape under test is exactly
the one named, except the seed-7777 case, which traces a world the generator
produced and checks the answer against ground truth rather than against the
trace's own opinion.

The three states beginning `CHAIN_` are failures of the chain, not findings
about a person. `CHAIN_BROKEN` in particular is ambiguous — the cited agent
may have had nothing to record, or may never have recorded what it was told —
so a test here asserts it is never reported as an origin.
"""

from __future__ import annotations

import pytest

from backend.app.audit.engine import AuditEngine
from backend.app.audit.verdicts import HEARSAY
from backend.app.case.graph import CaseGraph, case_graph_name
from backend.app.minds.access import MindAccess, mind_graph_name
from backend.app.referee.ground_truth import GroundTruth
from backend.app.referee.provenance import Referee
from backend.app.referee.terminals import (
    ALL_TERMINALS,
    CHAIN_BROKEN,
    CHAIN_CYCLE,
    CHAIN_TEMPORAL_VIOLATION,
    CHAIN_TOO_DEEP,
    DEPTH_CAP,
    ORIGIN_CONTRADICTED,
    ORIGIN_TERMINALS,
    ORIGIN_UNSUPPORTED,
    ORIGIN_WITNESSED,
)
from backend.app.world.generator import WorldSpec, generate, plan_world, world_graph_name

KITCHEN = "kitchen"
LIBRARY = "library"
SEED = 7777


@pytest.fixture
def rig(db, scratch_seed, graphs):
    """A case with one claim and a hand-built chain of minds behind it."""
    seed = scratch_seed
    graphs(case_graph_name(seed))

    case = CaseGraph(db, seed)
    case.upsert_place(KITCHEN, "Kitchen")
    case.upsert_place(LIBRARY, "Library")

    class Rig:
        def __init__(self):
            self.minds: dict[str, MindAccess] = {}

        def mind(self, agent: str) -> MindAccess:
            if agent not in self.minds:
                graphs(mind_graph_name(seed, agent))
                m = MindAccess(db, seed, agent)
                m.upsert_place(KITCHEN, "Kitchen")
                m.upsert_place(LIBRARY, "Library")
                self.minds[agent] = m
            return self.minds[agent]

        def claim(self, *, speaker, subject="x", place=KITCHEN, t0=0, t1=15,
                  claim_id="c1"):
            case.upsert_suspect(speaker, speaker)
            case.ingest_claim(
                claim_id=claim_id, speaker=speaker, subject=subject, place=place,
                t0=t0, t1=t1, turn=1, modality="THROUGHOUT",
            )
            return claim_id

        def heard(self, *, agent, fact_id, from_agent, src_fact_id, tick,
                  subject="x", place=KITCHEN, t0=0, t1=15):
            """`agent` holds a secondhand memory, told by `from_agent`."""
            m = self.mind(agent)
            m.write_fact(fact_id=fact_id, kind="heard", src="hearsay", subject=subject,
                         place=place, t0=t0, t1=t1, learned_at=tick)
            m.write_transmission(fact_id=fact_id, transmission_id=f"tr-{fact_id}",
                                 tick=tick, src_agent=from_agent,
                                 src_fact_id=src_fact_id)

        def saw(self, *, agent, fact_id, subject="x", place=KITCHEN, t0=0, t1=15,
                learned_at=None):
            self.mind(agent).write_fact(
                fact_id=fact_id, kind="saw", src="witnessed", subject=subject,
                place=place, t0=t0, t1=t1,
                learned_at=t0 if learned_at is None else learned_at,
            )

        def inferred(self, *, agent, fact_id, subject="x", place=KITCHEN, t0=0, t1=15):
            self.mind(agent).write_fact(
                fact_id=fact_id, kind="did", src="inferred", subject=subject,
                place=place, t0=t0, t1=t1, learned_at=t0,
            )

    r = Rig()
    r.case = case
    r.referee = Referee(db, seed)
    r.engine = AuditEngine(db, seed)
    r.seed = seed
    return r


# -- the three origin states -------------------------------------------------


def test_origin_witnessed_is_an_honest_chain(rig):
    """b told a, and b actually saw it. The chain ends grounded."""
    rig.claim(speaker="a")
    rig.heard(agent="a", fact_id="fa", from_agent="b", src_fact_id="fb", tick=20)
    rig.saw(agent="b", fact_id="fb")

    chain = rig.referee.trace_claim("c1")

    assert chain.terminal == ORIGIN_WITNESSED
    assert chain.origin_agent == "b"
    assert chain.is_origin
    assert not chain.is_ungrounded, "a chain ending in a witness is not ungrounded"
    assert [h.agent for h in chain.hops] == ["a", "b"]
    assert chain.carriers == ("a",)


def test_origin_unsupported_names_where_the_account_began(rig):
    """b told a, but b holds it only as an inference with nothing behind it."""
    rig.claim(speaker="a")
    rig.heard(agent="a", fact_id="fa", from_agent="b", src_fact_id="fb", tick=20)
    rig.inferred(agent="b", fact_id="fb")

    chain = rig.referee.trace_claim("c1")

    assert chain.terminal == ORIGIN_UNSUPPORTED
    assert chain.origin_agent == "b"
    assert chain.is_ungrounded
    assert chain.hops[-1].verdict == "INDETERMINATE"


def test_origin_contradicted_when_the_source_contradicts_itself(rig):
    """b told a that x was in the kitchen; b's own memory has x in the library."""
    rig.claim(speaker="a", place=KITCHEN)
    rig.heard(agent="a", fact_id="fa", from_agent="b", src_fact_id="fb", tick=20)
    rig.inferred(agent="b", fact_id="fb", place=KITCHEN)
    rig.saw(agent="b", fact_id="fb-real", place=LIBRARY, t0=5, t1=12)

    chain = rig.referee.trace_claim("c1")

    assert chain.terminal == ORIGIN_CONTRADICTED
    assert chain.origin_agent == "b"
    assert chain.is_ungrounded


def test_a_multi_hop_chain_walks_to_the_far_end(rig):
    """a heard from b, who heard from c, who saw it. Three hops, one origin."""
    rig.claim(speaker="a")
    rig.heard(agent="a", fact_id="fa", from_agent="b", src_fact_id="fb", tick=30)
    rig.heard(agent="b", fact_id="fb", from_agent="c", src_fact_id="fc", tick=20)
    rig.saw(agent="c", fact_id="fc")

    chain = rig.referee.trace_claim("c1")

    assert chain.terminal == ORIGIN_WITNESSED
    assert chain.origin_agent == "c"
    assert [h.agent for h in chain.hops] == ["a", "b", "c"]
    assert sorted(chain.carriers) == ["a", "b"]


# -- the four chain-failure states -------------------------------------------


def test_chain_broken_is_reported_and_is_not_an_origin(rig):
    """b told a, citing a record that exists in no mind.

    Spec 5.7 calls this ambiguous: b may have had nothing to record, or may
    never have recorded what it was told. So it is named as its own state and
    must not be reported as an origin — doing so would convert "we cannot
    tell" into "this is where it started".
    """
    rig.claim(speaker="a")
    rig.heard(agent="a", fact_id="fa", from_agent="b", src_fact_id="f-nonexistent",
              tick=20)
    rig.mind("b")  # b exists and has memories, just not this one
    rig.saw(agent="b", fact_id="fb-unrelated", place=LIBRARY, t0=100, t1=110)
    # b is a suspect in the case, so the scoreboard has a row to show zero in.
    rig.case.upsert_suspect("b", "b")

    chain = rig.referee.trace_claim("c1")

    assert chain.terminal == CHAIN_BROKEN
    assert chain.origin_agent is None, "CHAIN_BROKEN names no origin"
    assert not chain.is_origin
    assert chain.is_ungrounded
    assert "f-nonexistent" in chain.detail

    # And it must not become an origin on the scoreboard either.
    rig.referee.materialize_chain(chain)
    traces = rig.case.traces()
    assert all(t["role"] != "origin" for t in traces), (
        f"CHAIN_BROKEN materialized an origin edge: {traces}"
    )
    rows = {r["suspect"]: r for r in rig.case.scoreboard_rows()}
    assert rows["b"]["originated_ungrounded"] == 0
    assert rows["a"]["carried_ungrounded"] == 1, "a carried it, which is all we know"


def test_chain_temporal_violation_when_the_telling_precedes_the_knowing(rig):
    """b told a at tick 10 something b did not learn until tick 50.

    The transmission could not have happened as described. This is checkable
    only because `learned_at` is distinct from `t0` — a fact *about* 21:00 may
    have been *learned* at 21:30.
    """
    rig.claim(speaker="a")
    rig.heard(agent="a", fact_id="fa", from_agent="b", src_fact_id="fb", tick=10)
    rig.saw(agent="b", fact_id="fb", t0=0, t1=15, learned_at=50)

    chain = rig.referee.trace_claim("c1")

    assert chain.terminal == CHAIN_TEMPORAL_VIOLATION
    assert chain.origin_agent is None
    assert chain.is_ungrounded
    assert "10" in chain.detail and "50" in chain.detail


def test_a_telling_at_exactly_the_moment_learned_is_allowed(rig):
    """`learned_at <= tick`, so equality is fine. The boundary of the check."""
    rig.claim(speaker="a")
    rig.heard(agent="a", fact_id="fa", from_agent="b", src_fact_id="fb", tick=50)
    rig.saw(agent="b", fact_id="fb", t0=0, t1=15, learned_at=50)

    chain = rig.referee.trace_claim("c1")

    assert chain.terminal == ORIGIN_WITNESSED


def test_chain_cycle_when_the_walk_returns_to_someone_it_has_seen(rig):
    """a heard from b, and b's record cites a. The walk must stop, not loop."""
    rig.claim(speaker="a")
    rig.heard(agent="a", fact_id="fa", from_agent="b", src_fact_id="fb", tick=30)
    rig.heard(agent="b", fact_id="fb", from_agent="a", src_fact_id="fa", tick=20)

    chain = rig.referee.trace_claim("c1")

    assert chain.terminal == CHAIN_CYCLE
    assert chain.origin_agent is None


def test_chain_too_deep_stops_at_the_cap(rig):
    """A chain longer than the depth cap is reported, not followed further."""
    rig.claim(speaker="a0")
    agents = [f"a{i}" for i in range(DEPTH_CAP + 3)]
    for i, agent in enumerate(agents[:-1]):
        rig.heard(agent=agent, fact_id=f"f{i}", from_agent=agents[i + 1],
                  src_fact_id=f"f{i + 1}", tick=100 - i)
    rig.saw(agent=agents[-1], fact_id=f"f{len(agents) - 1}")

    chain = rig.referee.trace_claim("c1")

    assert chain.terminal == CHAIN_TOO_DEEP
    assert chain.origin_agent is None
    assert len(chain.hops) - 1 <= DEPTH_CAP + 1


def test_every_terminal_state_is_reachable():
    """All seven states exist and the tests above cover each one.

    A state nobody can produce is a state nobody has tested, so this pins the
    list to the seven in spec 5.7.
    """
    assert len(ALL_TERMINALS) == 7
    covered = {
        ORIGIN_WITNESSED, ORIGIN_UNSUPPORTED, ORIGIN_CONTRADICTED,
        CHAIN_BROKEN, CHAIN_TEMPORAL_VIOLATION, CHAIN_TOO_DEEP, CHAIN_CYCLE,
    }
    assert covered == set(ALL_TERMINALS)


def test_a_claim_with_no_secondhand_memory_has_no_chain(rig):
    """Only HEARSAY verdicts get a chain. A witnessed claim has nothing to walk."""
    rig.claim(speaker="a")
    rig.saw(agent="a", fact_id="fa")

    assert rig.referee.trace_claim("c1") is None


# -- against a generated world and its ground truth --------------------------


@pytest.fixture
def world(db, scratch_seed, graphs):
    """Seed 7777, with both pathological chains planted."""
    seed = scratch_seed
    plan = plan_world(SEED, WorldSpec(plant_broken_chain=True,
                                      plant_temporal_violation=True))
    graphs(world_graph_name(seed))
    graphs(case_graph_name(seed))
    for person in plan.people:
        graphs(mind_graph_name(seed, person.id))
    generate(db, seed, spec=WorldSpec(plan_seed=SEED, plant_broken_chain=True,
                                      plant_temporal_violation=True))
    return plan, seed


def test_the_seed_7777_repeater_traces_to_the_culprit_as_origin(db, world):
    """The innocent repeater's claim traces back to the agent who started it.

    Checked against ground truth, not against the trace's own opinion: the
    origin the referee names must be the person the generator recorded as the
    fabricator, and that person must be the culprit.

    The repeater is not deceiving anyone. Their memory genuinely holds what
    they were told, which is why their own claim is HEARSAY rather than
    anything worse, and why they appear here as a carrier.
    """
    plan, seed = world
    truth = GroundTruth(db, seed)
    referee = Referee(db, seed)
    case = CaseGraph(db, seed)

    fab = next(f for f in plan.fabrications if f.pathology == "none")
    by_id = {f.id: f for f in plan.facts}
    repeater = by_id[fab.relayed_fact_ids[0]].owner

    # The repeater says what it was told, and the audit calls it HEARSAY.
    case.ingest_claim(
        claim_id="rep", speaker=repeater, subject=fab.by_person, place=fab.place,
        t0=fab.t0, t1=fab.t1, turn=1, modality="THROUGHOUT", relayed_from=fab.by_person,
    )
    audited = AuditEngine(db, seed).audit_claim("rep")
    assert audited.verdict == HEARSAY

    chain = referee.trace_claim("rep")
    assert chain is not None

    # Ground truth: the origin is the recorded fabricator, who is the culprit.
    assert chain.terminal in ORIGIN_TERMINALS, (
        f"the traceable fabrication must resolve to an origin, got {chain.terminal}"
    )
    assert chain.origin_agent == fab.by_person
    assert chain.origin_agent == truth.culprit()
    assert truth.people()[chain.origin_agent] == "culprit"
    assert chain.is_ungrounded

    # The repeater is a link, not the source.
    assert repeater in chain.carriers
    assert chain.origin_agent not in chain.carriers

    # And that distinction survives into the scoreboard.
    referee.materialize_chain(chain)
    rows = {r["suspect"]: r for r in case.scoreboard_rows()}
    assert rows[chain.origin_agent]["originated_ungrounded"] == 1
    assert rows[chain.origin_agent]["carried_ungrounded"] == 0
    assert rows[repeater]["originated_ungrounded"] == 0
    assert rows[repeater]["carried_ungrounded"] == 1


def test_the_planted_broken_chain_is_detected_and_not_an_origin(db, world):
    """The generator's broken chain reports CHAIN_BROKEN, and names no origin."""
    plan, seed = world
    referee = Referee(db, seed)
    case = CaseGraph(db, seed)

    fab = next(f for f in plan.fabrications if f.pathology == "broken_chain")
    assert fab.relayed_fact_ids, "the broken chain was never relayed to anyone"
    by_id = {f.id: f for f in plan.facts}
    repeater = by_id[fab.relayed_fact_ids[0]].owner

    case.ingest_claim(
        claim_id="broken", speaker=repeater, subject=fab.by_person, place=fab.place,
        t0=fab.t0, t1=fab.t1, turn=1, modality="THROUGHOUT",
    )
    chain = referee.trace_claim("broken")

    assert chain.terminal == CHAIN_BROKEN
    assert chain.origin_agent is None
    assert not chain.is_origin

    referee.materialize_chain(chain)
    rows = {r["suspect"]: r for r in case.scoreboard_rows()}
    assert rows[fab.by_person]["originated_ungrounded"] == 0, (
        "an ambiguous broken chain must not be scored as an origin"
    )


def test_the_planted_temporal_violation_is_detected(db, world):
    """The generator's early telling reports CHAIN_TEMPORAL_VIOLATION."""
    plan, seed = world
    referee = Referee(db, seed)
    case = CaseGraph(db, seed)

    fab = next(f for f in plan.fabrications if f.pathology == "temporal_violation")
    assert fab.relayed_fact_ids, "the early telling was never relayed to anyone"
    by_id = {f.id: f for f in plan.facts}
    heard = by_id[fab.relayed_fact_ids[0]]

    case.ingest_claim(
        claim_id="early", speaker=heard.owner, subject=fab.by_person, place=fab.place,
        t0=fab.t0, t1=fab.t1, turn=1, modality="THROUGHOUT",
    )
    chain = referee.trace_claim("early")

    assert chain.terminal == CHAIN_TEMPORAL_VIOLATION
    assert chain.origin_agent is None


def test_tracing_a_whole_case_writes_nothing_into_it(db, world):
    """`trace_all_hearsay` traces every HEARSAY claim and materializes none.

    The chains are the referee's own view. Writing a conclusion into the case
    graph is a separate act, and in the application only the detective's
    budgeted `polygraph` performs it (spec 7, and `test_detective.py`): a case
    graph pre-loaded with every origin would make that budget decorative and
    leave the graph-versus-transcript arm of the benchmark measuring who was
    handed the answer.

    This replaces the eager assertion this test carried while the walk
    materialized as it went — the behaviour that was ruled wrong on
    2026-10-17, not the test's own misunderstanding.
    """
    from backend.app.agents.scripted import interview_all

    plan, seed = world
    interview_all(db, seed, plan=plan)
    results = AuditEngine(db, seed).audit_all()
    hearsay_claims = [r for r in results if r.verdict == HEARSAY]
    assert hearsay_claims, "the world produced no secondhand claims to trace"

    referee = Referee(db, seed)
    chains = referee.trace_all_hearsay()
    assert len(chains) == len(hearsay_claims)
    assert all(c.terminal in ALL_TERMINALS for c in chains)
    assert CaseGraph(db, seed).traces() == [], (
        "the walk wrote its conclusions into the case graph without being asked"
    )

    # Materialized only on request, one chain at a time — which is exactly
    # what spending a polygraph on one claim does.
    referee.materialize_chain(chains[0])
    traced = {t["claim_id"] for t in CaseGraph(db, seed).traces()}
    assert traced == {chains[0].claim_id}
