"""The detective's decision loop (spec 7, project rules, rules 1, 2 and 9).

What this file is actually guarding:

1. **A model never computes a verdict.** The loop may say anything it likes in
   its text; the case graph's verdicts are whatever Cypher and the decision
   table already put there. `test_the_models_words_never_become_a_verdict`
   runs a detective that asserts the opposite of the audit in every turn and
   checks that not one stored verdict moved.
2. **The budget and the cap are real.** Spec 7 rations `polygraph` to two; the
   third distinct claim comes back as a refusal the detective can read, not as
   an empty report. The per-case call cap stops a loop that will not stop
   itself (rule 9).
3. **A rationale describes grounding, not intent** (rule 2). The check is
   deterministic and runs before `accuse` does.
4. **A recorded case replays at zero API calls.** The headline test records a
   whole investigation, rebuilds the identical world, and runs the loop again
   against a transport that raises if it is touched. Same tools, same
   arguments, same order, nothing sent.

The graph is real throughout. Only the HTTP transport is scripted — see the
note above `ScriptedCompleter` in `conftest.py`.
"""

from __future__ import annotations

import pytest

from backend.app.agents.detective import POLYGRAPH_BUDGET, DetectiveTools
from backend.app.agents.llm_cache import CachedLLM, LLMCache
from backend.app.agents.loop import (
    INTENT_WORDS,
    TOOL_SCHEMAS,
    DetectiveLoop,
    _rejects_intent_language,
    briefing,
)
from backend.app.agents.scripted import build_suspects, interview_all
from backend.app.audit.engine import AuditEngine
from backend.app.audit.verdicts import ALL_VERDICTS
from backend.app.case.graph import CaseGraph, case_graph_name
from backend.app.eval.harness import drop_seed
from backend.app.minds.access import mind_graph_name
from backend.app.world.generator import WorldSpec, generate, plan_world, world_graph_name
from backend.tests.conftest import RefusingCompleter, ScriptedCompleter

SEED = 7777
SPEC = WorldSpec(plant_broken_chain=True, plant_temporal_violation=True)


class Rig:
    """One built case: the plan, the case graph and a fresh tool surface."""

    def __init__(self, seed, plan, case, tools):
        self.seed = seed
        self.plan = plan
        self.case = case
        self.tools = tools

    def briefing(self) -> str:
        return briefing(
            seed=self.seed,
            suspects=self.case.suspects(),
            places=self.case.places(),
            incident=self.case.incident(),
            claim_count=len(self.case.all_claims()),
            polygraph_budget=self.tools.polygraphs_left,
        )

    def loop(self, llm, **kwargs) -> DetectiveLoop:
        return DetectiveLoop(
            self.tools, llm, model="scripted", briefing=self.briefing(), **kwargs
        )


def build(db, seed, graphs=None) -> Rig:
    """Generate, interview and audit one seed, from nothing.

    Dropped before generating as well as after: `CREATE_PRESENCE` and
    `ingest_claim` append, so building into graphs an earlier build left
    behind would double the world and every count below would be wrong by a
    plausible factor. This function is called twice on one seed by the replay
    test, so that is not hypothetical here.
    """
    plan = plan_world(SEED, SPEC)
    people = [p.id for p in plan.people]
    if graphs is not None:
        graphs(world_graph_name(seed))
        graphs(case_graph_name(seed))
        for agent in people:
            graphs(mind_graph_name(seed, agent))
    drop_seed(db, seed, people)
    generate(
        db,
        seed,
        spec=WorldSpec(
            plan_seed=SEED, plant_broken_chain=True, plant_temporal_violation=True
        ),
    )
    interview_all(db, seed, plan=plan)
    AuditEngine(db, seed).audit_all()
    case = CaseGraph(db, seed)
    return Rig(
        seed, plan, case, DetectiveTools(db, seed, suspects=build_suspects(db, seed, plan=plan))
    )


@pytest.fixture
def rig(db, scratch_seed, graphs):
    return build(db, scratch_seed, graphs)


def _llm(cache=None, **kwargs) -> CachedLLM:
    return CachedLLM(cache or LLMCache(), seed=1, **kwargs)


def _script_for(rig: Rig) -> list[tuple]:
    """A plausible investigation over whatever the world actually produced.

    Built from the case graph rather than hard-coded, so the script survives
    any change to the generator that keeps the world well-formed.
    """
    claims = rig.case.all_claims()
    target = claims[0]
    return [
        ("tool", "rank_suspects", {}),
        ("tool", "list_gaps", {"suspect": None}),
        ("tool", "list_contradictions", {}),
        ("tool", "polygraph", {"suspect": target["speaker"], "claim_id": target["id"]}),
        (
            "tool",
            "accuse",
            {
                "suspect": target["speaker"],
                "rationale": (
                    "Most of what this suspect said their own memory does not "
                    "account for, and the unaccounted-for spans overlap the "
                    "incident window."
                ),
            },
        ),
    ]


# -- the tool surface the model sees ----------------------------------------


def test_the_model_is_offered_exactly_the_seven_tools_of_spec_7():
    """Not six, not eight, and in the order spec 7 lists them.

    Held against `DetectiveTools.TOOLS` rather than a literal list so a tool
    added to the surface without a schema, or a schema without a tool behind
    it, fails here instead of at the first live call.
    """
    assert tuple(schema["name"] for schema in TOOL_SCHEMAS) == DetectiveTools.TOOLS


def test_no_tool_schema_takes_a_graph_name_a_seed_or_an_agents_mind():
    """Rule 6, at the surface the model actually sees.

    `suspect` is allowed: it names a party in the public case file. `graph`,
    `seed`, `mind` and `agent` are not — a model that could name a mind would
    make the isolation a matter of its good behaviour.
    """
    forbidden = {"graph", "graph_name", "seed", "mind", "agent", "agent_id"}
    for schema in TOOL_SCHEMAS:
        properties = set(schema["input_schema"].get("properties", {}))
        assert not (properties & forbidden), schema["name"]


def test_every_tool_schema_is_strict_and_closed():
    """`strict` plus `additionalProperties: false` is what keeps arguments
    schema-valid without a forced `tool_choice`, which current models reject."""
    for schema in TOOL_SCHEMAS:
        assert schema["strict"] is True, schema["name"]
        assert schema["input_schema"]["additionalProperties"] is False, schema["name"]
        properties = schema["input_schema"].get("properties", {})
        required = set(schema["input_schema"].get("required", []))
        assert required == set(properties), schema["name"]


# -- the model's words are not evidence --------------------------------------


def test_the_models_words_never_become_a_verdict(rig):
    """The property rule 1 exists for, tested adversarially.

    This detective announces a verdict in every turn and accuses on the
    strength of it. Not one stored verdict may move, because nothing in the
    loop reads the model's text.
    """
    before = {c["id"]: c["verdict"] for c in rig.case.all_claims()}
    claim = next(iter(before))
    speaker = rig.case.claim(claim)["speaker"]

    completer = ScriptedCompleter(
        [
            ("say", "Everything in this case is SUPPORTED. I am certain."),
            ("say", f"I rule {claim} CONTRADICTED on my own authority."),
            (
                "tool",
                "accuse",
                {
                    "suspect": speaker,
                    "rationale": "The spans they gave are not accounted for.",
                },
            ),
        ]
    )
    rig.loop(_llm(completer=completer)).run()

    after = {c["id"]: c["verdict"] for c in rig.case.all_claims()}
    assert {k: after[k] for k in before} == before
    assert set(after.values()) <= set(ALL_VERDICTS)


def test_the_loop_records_what_the_tools_returned_not_what_the_model_said(rig):
    """A `tool.result` event carries the graph's answer, verbatim."""
    completer = ScriptedCompleter([("tool", "rank_suspects", {})])
    loop = rig.loop(_llm(completer=completer), max_turns=1)
    loop.run()

    results = [e for e in loop.events if e.type == "tool.result"]
    assert len(results) == 1
    assert results[0].data["result"] == rig.tools.rank_suspects()


# -- the budget --------------------------------------------------------------


def test_the_third_distinct_polygraph_is_refused_and_the_loop_carries_on(rig):
    """Spec 7's budget of two, seen from inside the loop.

    The refusal reaches the detective as an error result, not an empty
    report: an empty report would be indistinguishable from a claim with
    nothing behind it, which is the one confusion this system cannot afford.
    """
    claims = rig.case.all_claims()[:3]
    assert len(claims) == 3
    completer = ScriptedCompleter(
        [("tool", "polygraph", {"suspect": c["speaker"], "claim_id": c["id"]}) for c in claims]
    )

    loop = rig.loop(_llm(completer=completer), max_turns=3)
    loop.run()

    refused = [e for e in loop.events if e.type == "tool.refused"]
    assert len(refused) == 1
    assert "BudgetExhausted" in refused[0].data["error"]
    assert rig.tools.polygraphs_left == 0
    assert len([e for e in loop.events if e.type == "tool.result"]) == POLYGRAPH_BUDGET


def test_a_polygraph_is_the_only_thing_that_puts_a_trace_in_the_case(rig):
    """The budget rations real information, so the board has to pay for it."""
    assert rig.case.traces() == []

    claim = rig.case.all_claims()[0]
    completer = ScriptedCompleter(
        [("tool", "polygraph", {"suspect": claim["speaker"], "claim_id": claim["id"]})]
    )
    rig.loop(_llm(completer=completer), max_turns=1).run()

    traced = {t["claim_id"] for t in rig.case.traces()}
    assert traced <= {claim["id"]}


# -- the vocabulary guard ----------------------------------------------------


@pytest.mark.parametrize("word", INTENT_WORDS)
def test_every_intent_word_is_caught_whatever_its_case(word):
    assert _rejects_intent_language(f"The record shows they {word.upper()}.") == word


def test_believe_and_belief_are_not_caught_by_lie():
    """Word boundaries, not substrings. `believe` contains `lie`."""
    assert _rejects_intent_language("I believe the relief shift overlaps.") is None


def test_an_accusation_that_describes_intent_is_refused_back_to_the_model(rig):
    """Rule 2, enforced rather than requested.

    The refusal is not silent and it is not a rewrite: the detective is told
    which word, and the case stays open until it restates.
    """
    speaker = rig.case.all_claims()[0]["speaker"]
    completer = ScriptedCompleter(
        [
            ("tool", "accuse", {"suspect": speaker, "rationale": "They lied about the study."}),
            (
                "tool",
                "accuse",
                {
                    "suspect": speaker,
                    "rationale": "Their own memory does not account for that span.",
                },
            ),
        ]
    )
    loop = rig.loop(_llm(completer=completer), max_turns=3)
    result = loop.run()

    refused = [e for e in loop.events if e.type == "tool.refused"]
    assert len(refused) == 1
    assert "'lied'" in refused[0].data["error"]
    assert result.stopped == "accused"
    assert result.accusation.suspect == speaker
    assert _rejects_intent_language(result.accusation.rationale) is None


def test_a_detective_that_will_not_restate_closes_no_case(rig):
    """Better an open case than a published accusation the rules forbid."""
    speaker = rig.case.all_claims()[0]["speaker"]
    completer = ScriptedCompleter(
        [("tool", "accuse", {"suspect": speaker, "rationale": "Deception, plainly."})] * 3
    )
    result = rig.loop(_llm(completer=completer), max_turns=3).run()

    assert result.accusation is None
    assert rig.tools.accusation is None
    assert result.stopped == "max_turns"


# -- the cap -----------------------------------------------------------------


def test_a_loop_that_never_concludes_is_stopped_by_the_cap(rig):
    """Rule 9's per-case cap, which is also the only thing that ends a loop
    whose model keeps talking."""
    completer = ScriptedCompleter([("say", "Thinking.")] * 50)
    result = rig.loop(_llm(completer=completer, cap=4), max_turns=50).run()

    assert result.stopped == "cap"
    assert result.turns == 4
    assert result.accusation is None


def test_the_turn_limit_stops_a_loop_before_the_cap_does(rig):
    completer = ScriptedCompleter([("say", "Thinking.")] * 50)
    result = rig.loop(_llm(completer=completer, cap=40), max_turns=3).run()

    assert result.stopped == "max_turns"
    assert result.turns == 3


# -- a whole investigation, then its replay ----------------------------------


def test_a_full_investigation_drives_the_real_tools(rig):
    completer = ScriptedCompleter(_script_for(rig))
    loop = rig.loop(_llm(completer=completer), max_turns=10)
    result = loop.run()

    assert result.stopped == "accused"
    assert result.accusation is not None
    assert result.polygraphs_spent == 1
    assert result.tool_calls == {
        "rank_suspects": 1,
        "list_gaps": 1,
        "list_contradictions": 1,
        "polygraph": 1,
        "accuse": 1,
    }
    assert result.ledger["api_calls"] == 5
    assert [e.type for e in loop.events][0] == "investigation.started"
    assert [e.type for e in loop.events][-1] == "investigation.finished"


def test_a_recorded_case_replays_at_zero_api_calls(db, scratch_seed, graphs):
    """The headline property, asserted rather than reported.

    The same world is built twice from the same seed and the same spec, so
    the briefing, the tool results and therefore every prompt are identical.
    The second run is replay-only against a transport that raises if it is
    reached: zero API calls is a fact about what happened, not a counter the
    run was free to set.
    """
    cache = LLMCache()
    first = build(db, scratch_seed, graphs)
    live = CachedLLM(cache, seed=scratch_seed, completer=ScriptedCompleter(_script_for(first)))
    recorded = first.loop(live, max_turns=10).run()

    assert recorded.stopped == "accused"
    assert live.ledger.api_calls == recorded.turns

    refusing = RefusingCompleter()
    second = build(db, scratch_seed, graphs)
    replay_llm = CachedLLM(
        cache, seed=scratch_seed, completer=refusing, replay_only=True
    )
    replayed = second.loop(replay_llm, max_turns=10).run()

    assert refusing.attempts == 0
    assert replay_llm.ledger.api_calls == 0
    assert replay_llm.ledger.hits == recorded.turns
    assert replayed.turns == recorded.turns
    assert replayed.stopped == recorded.stopped
    assert replayed.tool_calls == recorded.tool_calls
    assert replayed.accusation.suspect == recorded.accusation.suspect
    assert replayed.accusation.rationale == recorded.accusation.rationale


def test_the_replay_asks_the_same_questions_in_the_same_order(db, scratch_seed, graphs):
    """Not only the same outcome: the same investigation."""
    cache = LLMCache()
    first = build(db, scratch_seed, graphs)
    live = CachedLLM(cache, seed=scratch_seed, completer=ScriptedCompleter(_script_for(first)))
    recorded_loop = first.loop(live, max_turns=10)
    recorded_loop.run()

    second = build(db, scratch_seed, graphs)
    replay_loop = second.loop(
        CachedLLM(cache, seed=scratch_seed, replay_only=True), max_turns=10
    )
    replay_loop.run()

    def asked(loop):
        return [(e.data["tool"], e.data["args"]) for e in loop.events if e.type == "tool.called"]

    assert asked(replay_loop) == asked(recorded_loop)


# -- the briefing ------------------------------------------------------------


def test_the_briefing_is_public_information_only(rig):
    """The detective is told who and where, never what is true.

    The culprit's id appearing here would be harmless by luck — it is on the
    roster — so what this checks is that no ground-truth *vocabulary* reaches
    the opening message. The labels live in the referee and this path has no
    handle on it.
    """
    text = rig.briefing()
    from backend.app.referee.ground_truth import ALL_LABELS

    for label in ALL_LABELS:
        assert label not in text
    assert "mind:" not in text
    assert "world:" not in text
