"""Replay seed 7777 end to end and write the case board's fixture.

The frontend reads `frontend/fixtures/case-7777.json` and has no API
dependency. That file is not hand-written: it is a dump of a real run, so
every number the board renders was computed by the audit engine rather than
invented to make a screenshot look good. Seed 7777 is deterministic, so the
dump is a reproducible replay — running this twice produces the same file.

**What is deliberately not in the fixture.** Nothing is read from
`world:{seed}`, and nothing is read off the `WorldPlan` except as the argument
`interview_all` needs. The plan knows who the culprit is; the case graph does
not, and the board shows what was proved rather than the answer key. The guard
at the bottom fails the dump if a ground-truth word reaches the file.

Run it through make, or with FALKOR_PORT set — a bare `python` reaches 6379,
which on this machine is another project's redis:

    FALKOR_PORT=6380 PYTHONPATH=. .venv/bin/python -m scripts.dump_case
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from backend.app.agents.scripted import interview_all
from backend.app.audit.engine import AuditEngine
from backend.app.case.graph import CaseGraph, case_graph_name
from backend.app.case.scoreboard import rank_suspects
from backend.app.db import connect
from backend.app.minds.access import mind_graph_name
from backend.app.referee.provenance import Referee
from backend.app.world.generator import (
    TICK_MAX,
    TICK_MIN,
    WorldSpec,
    generate,
    plan_world,
    world_graph_name,
)

SEED = 7777
OUT = Path("frontend/fixtures/case-7777.json")

# Both pathological chains are planted, so the fixture carries all three kinds
# of chain terminal the provenance strip can show — an origin the walk reaches,
# a cited record that exists nowhere, and a telling that precedes the knowing —
# rather than only the one a default world happens to produce.
SPEC = WorldSpec(plan_seed=SEED, plant_broken_chain=True, plant_temporal_violation=True)

# The case clock. Tick 0 is 18:00 and the window is the full 300 minutes,
# which is the axis the recorder draws whatever the data does.
CLOCK_START = "18:00"
CLOCK_END = "23:00"

# Words that would mean ground truth had leaked out of the referee's side of
# the seam, or that the interface had been handed a judgement of intent.
# Frozen in the one data file the repo keeps unpublishable vocabulary in, so
# that no module outside `referee/` spells them out — the same reason the
# detective's accusation guard reads its list from there.
FORBIDDEN = tuple(
    json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "backend/app/agents/intent_vocabulary.json"
        ).read_text()
    )["fixture_forbidden"]
)


def _fresh_graphs(db: Any) -> None:
    """Drop seed 7777's graphs so the replay starts from nothing.

    A second run over a populated case graph would MERGE onto the first run's
    claims and read back doubled counts. These graphs are regenerable from the
    seed alone, which is the whole point of dumping rather than hand-writing.
    """
    plan = plan_world(SEED, SPEC)
    names = [world_graph_name(SEED), case_graph_name(SEED)]
    names += [mind_graph_name(SEED, p.id) for p in plan.people]
    live = set(db.list_graphs())
    for name in names:
        if name in live:
            db.select_graph(name).delete()


def _tick_label(tick: int) -> str:
    """A tick as a wall clock reading. 18:00 plus `tick` minutes."""
    return f"{18 + tick // 60:02d}:{tick % 60:02d}"


def _chain_json(chain: Any) -> dict:
    """One provenance chain, hops in transmission order.

    The operator's board may show this: only the detective agent is rationed.
    """
    return {
        "claim_id": chain.claim_id,
        "speaker": chain.speaker,
        "terminal": chain.terminal,
        "origin_agent": chain.origin_agent,
        "is_origin": chain.is_origin,
        "is_ungrounded": chain.is_ungrounded,
        "carriers": list(chain.carriers),
        "detail": chain.detail,
        "hops": [asdict(hop) for hop in chain.hops],
    }


def build() -> dict:
    db = connect()
    db.connection.ping()
    _fresh_graphs(db)

    # 1. The world: places, routes, memories, planted provenance.
    plan = plan_world(SEED, SPEC)
    generate(db, SEED, spec=SPEC)

    # 2. The interviews, ingested as claims with verdict PENDING.
    ingested = interview_all(db, SEED, plan=plan)

    # 3. The audit: gather, decide, materialize, one claim at a time.
    audited = AuditEngine(db, SEED).audit_all()

    # 4. The cross-claim checks, which write the CONTRADICTS and CORROBORATES
    #    edges the scoreboard then aggregates.
    case = CaseGraph(db, SEED)
    case.find_exclusive_presence()
    case.find_impossible_travel()
    corroborations = case.find_corroboration()

    # 5. The referee's chain walk over every secondhand claim.
    referee = Referee(db, SEED)
    chains = referee.trace_all_hearsay()

    # ...and, for the board only, the conclusions written into the case graph.
    # The walk itself writes nothing: in the application only `polygraph`
    # materializes a chain, so the detective's two-call budget rations real
    # information (see `agents/detective.py`). This dump has no detective in
    # it — it is the human operator's view of a finished case, and the
    # operator may see everything — so it opts in here, in one visible line.
    for chain in chains:
        referee.materialize_chain(chain)

    # Everything below is read back out of the public case graph.
    claims = case.all_claims()
    places = case.places()
    place_ids = [p["id"] for p in places]
    relayed = {c["id"]: c["relayed_from"] for c in ingested}

    support = case.support_shadows()
    conflict = case.conflict_shadows()
    gaps = case.gaps()

    by_claim: dict[str, dict[str, list]] = {
        c["id"]: {"covered": [], "gaps": [], "support": [], "conflict": []} for c in claims
    }
    for row in support:
        entry = by_claim[row["claim_id"]]
        entry["support"].append(row["id"])
        entry["covered"].append([row["covers_t0"], row["covers_t1"]])
    for row in conflict:
        by_claim[row["claim_id"]]["conflict"].append(row["id"])
    for row in gaps:
        by_claim[row["claim_id"]]["gaps"].append([row["t0"], row["t1"]])

    claims_out = []
    for c in claims:
        e = by_claim[c["id"]]
        claims_out.append(
            {
                **c,
                "relayed_from": relayed.get(c["id"]),
                "covered": sorted(e["covered"]),
                "gaps": sorted(e["gaps"]),
                "support": sorted(e["support"]),
                "conflict": sorted(e["conflict"]),
            }
        )

    # The travel matrix, read cell by cell out of the precomputed TRAVEL_TIME
    # edges — the same cells the impossible-travel check reads.
    travel = {
        f"{a}|{b}": case.travel_minutes(a, b)
        for a in place_ids
        for b in place_ids
        if a != b
    }

    # The route behind each cell: the corridor-by-corridor walk `algo.SPpaths`
    # returned, so the board can draw the shortest path instead of a straight
    # line between two rooms (brief 5.9). The weight is asserted against the
    # matrix cell the impossible-travel check actually read: a route that did
    # not cost what the check was told would make the drawing misstate the
    # arithmetic beside it.
    routes: dict[str, list[str]] = {}
    for cell, minutes in travel.items():
        a, b = cell.split("|")
        found = case.shortest_path(a, b)
        if found is None:
            raise RuntimeError(
                f"no path between {a!r} and {b!r}, but the travel matrix holds "
                f"{minutes} minutes for that pair; the floor plan and the matrix "
                f"disagree"
            )
        weight, route = found
        if weight != minutes:
            raise RuntimeError(
                f"the shortest walk {a!r} to {b!r} costs {weight} minutes but the "
                f"travel matrix the impossible-travel check reads holds {minutes}"
            )
        routes[cell] = route

    speakers = sorted({c["speaker"] for c in claims})
    return {
        "meta": {
            "seed": SEED,
            "case_id": f"0x{SEED:04X}",
            "tick_min": TICK_MIN,
            "tick_max": TICK_MAX,
            "clock_start": CLOCK_START,
            "clock_end": CLOCK_END,
            "hour_labels": [
                {"tick": t, "label": _tick_label(t)} for t in range(0, TICK_MAX + 1, 60)
            ],
            "claims": len(claims_out),
            "audited": sum(1 for c in claims_out if c["verdict"] != "PENDING"),
            "interviews": len(speakers),
            "spec": {
                "plant_broken_chain": SPEC.plant_broken_chain,
                "plant_temporal_violation": SPEC.plant_temporal_violation,
                "n_places": SPEC.n_places,
                "n_people": SPEC.n_people,
                "exchanges": SPEC.exchanges,
            },
        },
        "suspects": case.suspects(),
        "incident": case.incident(),
        "claims": claims_out,
        "evidence": {"support": support, "conflict": conflict},
        "contradictions": case.contradictions(),
        "corroborations": corroborations,
        "traces": case.traces(),
        "chains": [_chain_json(ch) for ch in chains],
        "tally": case.verdict_tally(),
        "scoreboard": rank_suspects(case.scoreboard_rows()),
        "floor_plan": {
            "places": places,
            "corridors": case.adjacency(),
            "travel": travel,
            "routes": routes,
        },
        "audit_summary": {
            "uncovered_minutes": sum(a.uncovered for a in audited),
            "claims_with_gaps": sum(1 for a in audited if a.gaps),
        },
    }


def main() -> None:
    fixture = build()
    text = json.dumps(fixture, indent=2, sort_keys=False)

    lowered = text.lower()
    leaked = [w for w in FORBIDDEN if re.search(rf"\b{w}\b", lowered)]
    if leaked:
        raise RuntimeError(
            f"the fixture contains {leaked}, which the board must never be handed: "
            f"ground truth is referee-only and a verdict describes grounding, "
            f"not intent"
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text + "\n")
    print(f"wrote {OUT} ({len(text) + 1} bytes)")
    print("top-level keys:")
    for key in fixture:
        print(f"  {key}")


if __name__ == "__main__":
    main()
