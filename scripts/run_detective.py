"""One case, investigated, then the same case replayed from cache.

    python -m scripts.run_detective --seed 7777                 # scripted plan
    python -m scripts.run_detective --seed 7777 --live          # a real model
    python -m scripts.run_detective --seed 7777 --keep-cache    # keep the recording

Two passes over one seed. The first records every turn into the SQLite replay
cache; the second rebuilds the identical world and runs the loop again with
the transport removed, which is how "replays at zero API calls" is shown
rather than asserted — pass two cannot reach a model, because there is
nothing there to reach.

The world, the minds, the case graph, the audit and all seven tools are real
in both passes. What `--live` changes is only who chooses the next tool call:

- `--scripted` (the default) walks a fixed plan — read the board, read the
  gaps, interview into one, re-check the contradictions, spend a polygraph,
  accuse. It demonstrates the loop, the budget and the cache with no key and
  no cost, and it is what CI can run. It is not a demonstration of a model's
  judgement and is not reported as one.
- `--live` puts a real model behind the same interface, resolved from
  `ALIBI_COMPLETER` ("package.module:factory"); this repo pins no vendor SDK
  and names no model, so `--live` needs both that and `ALIBI_DETECTIVE_MODEL`
  set. Every call still goes through the cache wrapper and the per-case cap
  (the project rules, rule 9); no path here bypasses either.

No ground-truth label is printed. This is the detective's view of the case,
and the detective never sees the answer key — `scripts/run_case.py` is the
scoring tool, and it is the one that may print labels.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from backend.app.agents.detective import DetectiveTools
from backend.app.agents.llm_cache import CachedLLM, LLMCache, load_completer
from backend.app.agents.loop import DetectiveLoop, briefing
from backend.app.agents.scripted import build_suspects, interview_all
from backend.app.audit.engine import AuditEngine
from backend.app.case.graph import CaseGraph
from backend.app.case.scoreboard import rank_suspects
from backend.app.config import settings
from backend.app.db import connect
from backend.app.eval.harness import drop_seed
from backend.app.world.generator import WorldSpec, generate, plan_world


class ScriptedPlan:
    """A fixed investigation, as a transport.

    It answers in the shape the API answers in, so the loop cannot tell the
    difference and no branch in `DetectiveLoop` exists for it. The plan is
    computed from the case graph when the pass starts, so it uses whatever
    suspects and claims the seed actually produced.
    """

    def __init__(self, steps: list[tuple[str, dict]]) -> None:
        self.steps = steps
        self.calls = 0

    def __call__(self, request: dict) -> dict:
        n = self.calls
        self.calls += 1
        if n >= len(self.steps):
            return {
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "Nothing further."}],
                "usage": {"input_tokens": 0, "output_tokens": 0},
            }
        name, args = self.steps[n]
        return {
            "stop_reason": "tool_use",
            "content": [{"type": "tool_use", "id": f"toolu_{n}", "name": name, "input": args}],
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }


class ReactivePlan:
    """A scripted detective that reads its own tool results.

    The same shape as the fixed plan above, but it picks *which* suspect and
    *which* claim from what the tools actually returned, so it works on any
    seed without being handed the answers. It parses the JSON this system
    writes into `tool_result` blocks — its own structured output, never prose
    — so there is no NLU here and no model.

    It exists so the board can be driven end to end with no credential and no
    cost. It is a transport, not a judgement: every verdict it reads was
    computed by Cypher and the decision table before it ever saw it.
    """

    def __init__(self) -> None:
        self.calls = 0
        self.top: str | None = None
        self.claim: str | None = None

    def _last_result(self, request: dict) -> Any:
        """The most recent tool result in the conversation, decoded."""
        for message in reversed(request.get("messages", [])):
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for block in reversed(content):
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    if block.get("is_error"):
                        return None
                    try:
                        return json.loads(block.get("content") or "null")
                    except json.JSONDecodeError:
                        return None
        return None

    def __call__(self, request: dict) -> dict:
        n = self.calls
        self.calls += 1
        result = self._last_result(request)

        if n == 0:
            step = ("rank_suspects", {})
        elif n == 1:
            # The scoreboard, highest unaccounted-for score first.
            self.top = result[0]["suspect"] if result else None
            step = ("list_gaps", {"suspect": self.top})
        elif n == 2:
            # A gap row names the claim it was found on, which is the claim
            # worth spending a look at.
            if result:
                self.claim = result[0]["claim_id"]
            step = ("list_contradictions", {})
        elif n == 3 and self.claim and self.top:
            step = ("polygraph", {"suspect": self.top, "claim_id": self.claim})
        elif self.top:
            step = (
                "accuse",
                {
                    "suspect": self.top,
                    "rationale": (
                        f"{self.top} tops the board on how much of what they said "
                        f"their own memory does not account for, and those spans "
                        f"overlap the incident window."
                    ),
                },
            )
        else:
            return {
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "Nothing to go on."}],
                "usage": {"input_tokens": 0, "output_tokens": 0},
            }

        name, args = step
        return {
            "stop_reason": "tool_use",
            "content": [{"type": "tool_use", "id": f"toolu_{n}", "name": name, "input": args}],
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }


def scripted_completer() -> ReactivePlan:
    """Factory for `ALIBI_COMPLETER=scripts.run_detective:scripted_completer`.

    Lets the orchestrator drive a whole case with no credential, which is how
    the board is exercised end to end before a real model is in the loop.
    """
    return ReactivePlan()


class NoTransport:
    """Pass two's transport. Reaching it is the failure, not a slow path."""

    def __call__(self, request: dict) -> dict:
        raise AssertionError(
            "pass two reached the network; it was supposed to replay from cache"
        )


def build(db, seed: int, *, pathologies: bool) -> tuple:
    """Generate, interview and audit one seed from nothing.

    Dropped before generating as well as after: `CREATE_PRESENCE` and
    `ingest_claim` append, so building into graphs an earlier pass left behind
    would double the world. This function runs twice on one seed.
    """
    spec = WorldSpec(plant_broken_chain=pathologies, plant_temporal_violation=pathologies)
    plan = plan_world(seed, spec)
    drop_seed(db, seed, [p.id for p in plan.people])
    generate(db, seed, spec=spec)
    interview_all(db, seed, plan=plan)
    AuditEngine(db, seed).audit_all()
    case = CaseGraph(db, seed)
    tools = DetectiveTools(db, seed, suspects=build_suspects(db, seed, plan=plan))
    return plan, case, tools


def scripted_plan(case: CaseGraph) -> ScriptedPlan:
    """The fixed investigation, written against this seed's actual board.

    The board is read through the scoring function directly, never through
    `DetectiveTools.rank_suspects`: writing the plan is not the detective
    taking a turn, and a tool call made here would be charged to the
    detective's per-case cost column and show up in the comparison as a turn
    the replay never took. The first run of this script did exactly that.
    """
    ranked = rank_suspects(case.scoreboard_rows())
    top = ranked[0]["suspect"]
    gaps = [g for g in case.gaps_by_speaker(top)] or case.gaps()
    mine = [c for c in case.all_claims() if c["speaker"] == top]
    target = mine[0] if mine else case.all_claims()[0]

    steps: list[tuple[str, dict]] = [
        ("rank_suspects", {}),
        ("list_gaps", {"suspect": top}),
    ]
    if gaps:
        g = gaps[0]
        steps.append(
            ("interview", {"suspect": top, "about": g["subject"], "t0": g["t0"], "t1": g["t1"]})
        )
    steps += [
        ("list_contradictions", {}),
        ("polygraph", {"suspect": target["speaker"], "claim_id": target["id"]}),
        (
            "accuse",
            {
                "suspect": top,
                "rationale": (
                    f"{top} tops the board on how much of what they said their own "
                    f"memory does not account for, and the spans left unaccounted "
                    f"for overlap the incident window."
                ),
            },
        ),
    ]
    return ScriptedPlan(steps)


def run_pass(
    db,
    seed: int,
    *,
    cache: LLMCache,
    label: str,
    live: bool,
    replay_only: bool,
    pathologies: bool,
    model: str,
) -> dict:
    plan, case, tools = build(db, seed, pathologies=pathologies)

    if replay_only:
        completer = NoTransport()
    elif live:
        completer = load_completer(settings.completer)
    else:
        completer = scripted_plan(case)

    llm = CachedLLM(cache, seed=seed, completer=completer, replay_only=replay_only)
    loop = DetectiveLoop(
        tools,
        llm,
        model=model,
        briefing=briefing(
            seed=seed,
            suspects=case.suspects(),
            places=case.places(),
            incident=case.incident(),
            claim_count=len(case.all_claims()),
            polygraph_budget=tools.polygraphs_left,
        ),
    )

    chose = (
        f"live model {model}"
        if live
        else "SCRIPTED PLAN — no model was called; these tool calls were fixed in advance"
    )
    print(f"\n{'=' * 72}\n{label}\n{'=' * 72}")
    print(f"  who chose each tool call: {chose}\n")
    result = loop.run()
    for event in loop.events:
        if event.type == "tool.called":
            print(f"  -> {event.data['tool']}({_args(event.data['args'])})")
        elif event.type == "tool.refused":
            print(f"     refused: {event.data['error'].splitlines()[0]}")
        elif event.type == "tool.result":
            print(f"     {_summarize(event.data['tool'], event.data['result'])}")

    print()
    print(f"  stopped            {result.stopped} after {result.turns} turns")
    print(f"  polygraphs spent   {result.polygraphs_spent} of 2")
    print(f"  traces in case     {len(case.traces())}")
    print(f"  tool calls         {result.tool_calls}")
    print(f"  LLM turns          {result.ledger['calls']}")
    print(f"  cache hits         {result.ledger['hits']}")
    print(f"  API CALLS          {result.ledger['api_calls']}")
    if result.accusation is not None:
        print(f"  accused            {result.accusation.suspect}")
        print(f"  rationale          {result.accusation.rationale}")
    drop_seed(db, seed, [p.id for p in plan.people])
    return result.as_dict()


def _args(args: dict) -> str:
    return ", ".join(f"{k}={v!r}" for k, v in args.items() if v is not None)


def _summarize(tool: str, result) -> str:
    if isinstance(result, list):
        return f"{len(result)} rows"
    if tool == "accuse":
        return f"accused {result['suspect']}"
    if isinstance(result, dict) and "verdict" in result:
        return (
            f"{result['claim_id']}: {result['verdict']}, coverage "
            f"{result['coverage']}, {len(result['gaps'])} gaps, chain "
            f"{(result.get('chain') or {}).get('terminal')}"
        )
    return str(result)[:120]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=7777)
    parser.add_argument(
        "--live",
        action="store_true",
        help="let the detective model choose the tool calls (costs money the "
        "first time; replays free after)",
    )
    parser.add_argument("--model", default=settings.detective_model or "scripted-plan")
    parser.add_argument(
        "--pathologies",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="plant the broken-chain and temporal-violation chains (on by default)",
    )
    parser.add_argument("--cache", default=None, help="path to the replay cache")
    parser.add_argument(
        "--keep-cache",
        action="store_true",
        help="keep the recording instead of using a throwaway one",
    )
    args = parser.parse_args(argv)

    db = connect()
    db.connection.ping()
    print(f"FalkorDB {settings.falkor_host}:{settings.falkor_port}  seed {args.seed}")
    print(f"detective: {'live model ' + args.model if args.live else 'scripted plan'}")

    with tempfile.TemporaryDirectory() as tmp:
        path = args.cache or (
            settings.llm_cache_path if args.keep_cache else str(Path(tmp) / "replay.sqlite3")
        )
        cache = LLMCache(path)
        print(f"replay cache: {path}")

        first = run_pass(
            db,
            args.seed,
            cache=cache,
            label="PASS 1 — recording",
            live=args.live,
            replay_only=False,
            pathologies=args.pathologies,
            model=args.model,
        )
        second = run_pass(
            db,
            args.seed,
            cache=cache,
            label="PASS 2 — replay-only, no transport configured",
            live=args.live,
            replay_only=True,
            pathologies=args.pathologies,
            model=args.model,
        )

    print(f"\n{'=' * 72}")
    same = (
        first["turns"] == second["turns"]
        and first["tool_calls"] == second["tool_calls"]
        and first["accusation"] == second["accusation"]
    )
    print(
        "chosen by:                "
        + (f"live model {args.model}" if args.live else "SCRIPTED PLAN, not a model")
    )
    print(f"identical investigation:  {same}")
    print(f"API calls, pass 1:        {first['ledger']['api_calls']}")
    print(f"API calls, pass 2:        {second['ledger']['api_calls']}")
    return 0 if same and second["ledger"]["api_calls"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
