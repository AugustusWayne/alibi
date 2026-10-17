"""The detective's typed tool surface (spec 7), and what it is rationed to.

Two properties here are the point of the file, and both are about *when*
information exists rather than where it lives:

1. **The polygraph budget is real.** Spec 7 gives `polygraph` a budget of two
   per case. The boundary is tested exactly: the second call is allowed, the
   third is refused.
2. **An unpolygraphed claim has no `TRACED_TO` edge.** The referee's chain
   conclusions are materialized only for claims the detective actually spent a
   polygraph on. If they were written eagerly the budget would be decorative —
   the case graph would already say "this began with p4, and p4 has nothing
   behind it" — and the graph-versus-transcript arm of the benchmark would be
   measuring who was handed the answer.

Nothing in this file asks whether a claim is *true*. The tools report
grounding, and the reports they return carry no ground-truth label.
"""

from __future__ import annotations

import pytest

from backend.app.agents.detective import BudgetExhausted, DetectiveTools, Question
from backend.app.agents.scripted import build_suspects, interview_all
from backend.app.audit.engine import AuditEngine
from backend.app.audit.verdicts import ALL_VERDICTS, HEARSAY
from backend.app.case.graph import CaseGraph, case_graph_name
from backend.app.case.scoreboard import SCORED_TERMS
from backend.app.minds.access import mind_graph_name
from backend.app.referee.provenance import Referee
from backend.app.referee.terminals import UNGROUNDED_ORIGINS
from backend.app.world.generator import WorldSpec, generate, plan_world, world_graph_name

SEED = 7777
SPEC = WorldSpec(plant_broken_chain=True, plant_temporal_violation=True)


@pytest.fixture
def case(db, scratch_seed, graphs):
    """A fully audited seed-7777 case, with no trace materialized yet.

    This is the state the detective is handed: claims with verdicts, evidence
    shadows, gaps and contradictions — the audit's own findings — and nothing
    from the referee's chain walk.
    """
    seed = scratch_seed
    plan = plan_world(SEED, SPEC)
    graphs(world_graph_name(seed))
    graphs(case_graph_name(seed))
    for person in plan.people:
        graphs(mind_graph_name(seed, person.id))
    generate(db, seed, spec=WorldSpec(plan_seed=SEED, plant_broken_chain=True,
                                      plant_temporal_violation=True))
    interview_all(db, seed, plan=plan)
    AuditEngine(db, seed).audit_all()

    class Rig:
        pass

    rig = Rig()
    rig.seed = seed
    rig.plan = plan
    rig.case = CaseGraph(db, seed)
    rig.referee = Referee(db, seed)
    rig.tools = DetectiveTools(
        db, seed, suspects=build_suspects(db, seed, plan=plan)
    )
    return rig


def _hearsay_claims(case_graph: CaseGraph) -> list[dict]:
    return [c for c in case_graph.all_claims() if c["verdict"] == HEARSAY]


# -- the budget --------------------------------------------------------------


def test_the_polygraph_budget_is_two_and_the_third_call_is_refused(case):
    """The boundary exactly: two claims allowed, the third refused.

    Refused loudly, by raising. A tool that silently returned an empty report
    on an exhausted budget would be indistinguishable from a claim with
    nothing behind it, which is the one confusion this system cannot afford.
    """
    claims = case.case.all_claims()
    assert len(claims) >= 3, "the world must offer more claims than the budget allows"
    first, second, third = claims[0], claims[1], claims[2]

    assert case.tools.polygraphs_left == 2

    case.tools.polygraph(first["speaker"], first["id"])
    assert case.tools.polygraphs_left == 1

    case.tools.polygraph(second["speaker"], second["id"])
    assert case.tools.polygraphs_left == 0

    with pytest.raises(BudgetExhausted):
        case.tools.polygraph(third["speaker"], third["id"])


def test_a_refused_polygraph_writes_nothing(case):
    """An exhausted budget leaves the case graph exactly as it was."""
    claims = case.case.all_claims()
    for claim in claims[:2]:
        case.tools.polygraph(claim["speaker"], claim["id"])
    before = case.case.traces()

    third = claims[2]
    with pytest.raises(BudgetExhausted):
        case.tools.polygraph(third["speaker"], third["id"])

    assert case.case.traces() == before
    assert all(t["claim_id"] != third["id"] for t in case.case.traces())


def test_re_polygraphing_one_claim_spends_the_budget_once(case):
    """Asking twice about the same claim costs one.

    The budget rations which minds the referee opens on the detective's
    behalf. A second look at a claim already polygraphed opens nothing: its
    conclusion is already in the case graph and the detective can read it
    there. Charging for it would make the budget a measure of call discipline
    rather than of information.
    """
    target = _hearsay_claims(case.case)[0]

    first = case.tools.polygraph(target["speaker"], target["id"])
    assert case.tools.polygraphs_left == 1

    again = case.tools.polygraph(target["speaker"], target["id"])
    assert case.tools.polygraphs_left == 1, "a repeat opened no new mind"
    assert again.verdict == first.verdict
    assert again.chain == first.chain


# -- the gating of TRACED_TO -------------------------------------------------


def test_an_unpolygraphed_claim_has_no_traced_to_edge(case):
    """The audit alone materializes no chain conclusion, for any claim."""
    assert _hearsay_claims(case.case), "the world produced no secondhand claims"
    assert case.case.traces() == [], (
        "the case graph carried the referee's chain conclusions before the "
        "detective spent a single polygraph"
    )


def test_polygraphing_one_claim_traces_that_claim_and_no_other(case):
    """Exactly one claim's chain is materialized, and it is the one asked about."""
    hearsay = _hearsay_claims(case.case)
    assert len(hearsay) >= 2, "the test needs a second secondhand claim to leave alone"
    target, untouched = hearsay[0], hearsay[1]

    case.tools.polygraph(target["speaker"], target["id"])

    traced = {t["claim_id"] for t in case.case.traces()}
    assert traced == {target["id"]}
    assert untouched["id"] not in traced


def test_the_scoreboard_counts_only_polygraphed_chains(case):
    """Q8's origin and carrier columns are zero until a polygraph is spent.

    This is the causal demo stated as a test: the board ranks on what the
    audit found, and the chain's conclusion enters the ranking only when the
    detective pays for it.
    """
    before = {r["suspect"]: r for r in case.case.scoreboard_rows()}
    assert all(r["originated_ungrounded"] == 0 for r in before.values())
    assert all(r["carried_ungrounded"] == 0 for r in before.values())

    chains = {c["id"]: case.referee.trace_claim(c["id"]) for c in _hearsay_claims(case.case)}
    ungrounded = [
        (claim_id, chain)
        for claim_id, chain in chains.items()
        if chain is not None and chain.terminal in UNGROUNDED_ORIGINS
    ]
    assert ungrounded, "seed 7777 must produce a chain that ends at an ungrounded origin"
    claim_id, chain = ungrounded[0]

    claim = case.case.claim(claim_id)
    case.tools.polygraph(claim["speaker"], claim_id)

    after = {r["suspect"]: r for r in case.case.scoreboard_rows()}
    assert after[chain.origin_agent]["originated_ungrounded"] == 1
    assert after[chain.origin_agent]["carried_ungrounded"] == 0
    for carrier in chain.carriers:
        assert after[carrier]["carried_ungrounded"] == 1
        assert after[carrier]["originated_ungrounded"] == 0


# -- what the polygraph is allowed to return ---------------------------------


def test_the_polygraph_returns_a_verdict_with_its_shadows_and_gaps(case):
    """Spec 7: a verdict plus evidence shadows and gaps. Never raw memory."""
    target = _hearsay_claims(case.case)[0]

    report = case.tools.polygraph(target["speaker"], target["id"])

    assert report.claim_id == target["id"]
    assert report.verdict in ALL_VERDICTS
    assert report.support, "a HEARSAY claim rests on a secondhand shadow"
    shadow_fields = {"claim_id", "id", "fact_id", "src", "place", "agent", "t0", "t1",
                     "covers_t0", "covers_t1"}
    for shadow in report.support:
        assert set(shadow) <= shadow_fields, (
            f"the shadow carried a field the case graph has no business holding: "
            f"{set(shadow) - shadow_fields}"
        )


def test_the_polygraph_refuses_a_suspect_who_did_not_make_the_claim(case):
    """The suspect argument cannot select whose memory is read.

    The claim's own public `BY` edge decides that. Passing someone else's name
    is refused rather than quietly honoured, so there is no reading of this
    tool in which the detective chooses a mind (PROJECT_RULES.md rule 6).
    """
    target = _hearsay_claims(case.case)[0]
    other = next(s["id"] for s in case.case.suspects() if s["id"] != target["speaker"])

    with pytest.raises(ValueError, match="made by"):
        case.tools.polygraph(other, target["id"])

    assert case.tools.polygraphs_left == 2, "a refused call spends nothing"
    assert case.case.traces() == []


def test_the_polygraph_refuses_a_claim_that_is_not_in_the_case(case):
    """An unknown claim id raises; it does not come back empty."""
    suspect = case.case.suspects()[0]["id"]
    with pytest.raises(KeyError):
        case.tools.polygraph(suspect, "no-such-claim")
    assert case.tools.polygraphs_left == 2


def test_no_detective_tool_takes_a_graph_name_or_a_seed(case):
    """PROJECT_RULES.md rule 6, asserted against the actual signatures.

    A suspect id is a party in the public case file, not a memory store: the
    tools resolve it against a roster bound at construction, and no parameter
    anywhere names a graph, a seed or an agent's mind.
    """
    import inspect

    forbidden = {"graph", "graph_name", "seed", "mind", "agent", "agent_id", "db"}
    for name in DetectiveTools.TOOLS:
        params = set(inspect.signature(getattr(DetectiveTools, name)).parameters)
        assert not (params & forbidden), f"{name} exposes {params & forbidden}"


# -- the rest of the surface -------------------------------------------------


def test_list_gaps_narrows_to_one_suspect(case):
    """The sleeper tool: the exact spans to interrogate, per suspect."""
    everyone = case.tools.list_gaps()
    assert everyone, "the audit found no unaccounted-for span in the whole case"
    subject = everyone[0]["speaker"]

    only_theirs = case.tools.list_gaps(subject)

    assert only_theirs
    assert {g["speaker"] for g in only_theirs} == {subject}
    assert only_theirs == [g for g in everyone if g["speaker"] == subject]


def test_check_travel_reports_the_walk_and_its_route(case):
    """Public floor plan arithmetic, with the corridors it went through."""
    places = [p["id"] for p in case.case.places()]
    a, b = places[0], places[-1]

    answer = case.tools.check_travel(a, b)

    assert answer["minutes"] >= 1
    assert answer["route"][0] == a and answer["route"][-1] == b


def test_list_contradictions_materializes_and_reads_them_back(case):
    """The detective's view of Q5 and Q6, computed in Cypher."""
    found = case.tools.list_contradictions()
    assert found, "seed 7777 must contain at least one contradiction"
    assert {c["kind"] for c in found} <= {"exclusive_presence", "impossible_travel"}
    assert all(c["speaker_a"] and c["speaker_b"] for c in found)


def test_rank_suspects_returns_the_scoreboard_with_its_breakdown(case):
    """Q8 plus the one ranking function, never a total on its own."""
    board = case.tools.rank_suspects()
    assert board
    assert all(set(row["breakdown"]) == set(SCORED_TERMS) for row in board)
    keys = [(-row["score"], row["suspect"]) for row in board]
    assert keys == sorted(keys), "the board must be ordered by score, ties on suspect id"


def test_an_interview_ingests_what_was_said_and_audits_it(case):
    """A question about a person and a span, answered and then audited."""
    before = len(case.case.all_claims())
    suspect = case.case.suspects()[0]["id"]

    said = case.tools.interview(suspect, Question(window=(0, 30)))

    assert said, "the suspect answered nothing about a window they lived through"
    assert all(c["verdict"] in ALL_VERDICTS for c in said)
    assert len(case.case.all_claims()) >= before


def test_an_interview_repeating_known_testimony_adds_no_claim(case):
    """Asking twice does not double a suspect's account."""
    suspect = case.case.suspects()[0]["id"]
    question = Question(window=(0, 30))

    case.tools.interview(suspect, question)
    after_first = len(case.case.all_claims())
    second = case.tools.interview(suspect, question)

    assert len(case.case.all_claims()) == after_first
    assert all(not c["new"] for c in second)


def test_interview_refuses_a_suspect_who_is_not_in_the_case(case):
    with pytest.raises(KeyError):
        case.tools.interview("nobody", Question())


def test_accuse_records_the_accusation_and_closes_the_case(case):
    """The terminal tool. It records a conclusion; it does not score it."""
    suspect = case.case.suspects()[0]["id"]

    accusation = case.tools.accuse(suspect, "the 20:10 gap is unaccounted for")

    assert accusation.suspect == suspect
    assert accusation.polygraphs_spent == 0
    assert case.tools.accusation == accusation
    with pytest.raises(ValueError, match="closed"):
        case.tools.accuse(suspect, "again")
