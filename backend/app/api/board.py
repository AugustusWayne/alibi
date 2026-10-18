"""The board's payload, assembled from the public case graph and nothing else.

The board was built against `frontend/fixtures/case-7777.json`, which
`scripts/dump_case.py` writes. That script is the operator's tool and may
cross the seam; this module serves a browser and may not. The payload here is
the same shape, built from the same readers, with one deliberate difference.

**A chain's hops are not served, and cannot be.** A hop names a fact id, the
tick it was transmitted and when the hearer learned it — all of it inside a
private mind. The fixture carries them because an operator dumping their own
case may see them; no route may (project rules, rule 6). What goes out is
what a `TRACED_TO` edge already published: the terminal state, the origin, the
carriers and the depth. The board degrades to those, naming the cited speaker
from the claim's own public `relayed_from` instead of from hop 1.

**Trails appear only where a polygraph was spent.** The fixture has a chain
for every hearsay claim because the dump materializes them all. In a live case
`polygraph` is the only writer of `TRACED_TO`, so the board shows a trail
exactly where the detective paid for one. That is the budget, visible.

No Cypher lives here: every value comes from a named reader on `CaseGraph`.
"""

from __future__ import annotations

from typing import Any

from backend.app.audit.verdicts import PENDING
from backend.app.case.graph import CaseGraph

TICK_MAX = 300
"""The case clock, 18:00 to 23:00. The axis the recorder draws whatever the
data does — the same constant `scripts/dump_case.py` writes into the fixture."""


def _tick_label(tick: int) -> str:
    """Tick 0 is 18:00. One minute per tick."""
    return f"{18 + tick // 60:02d}:{tick % 60:02d}"


def _chain_rows(case: CaseGraph) -> list[dict]:
    """One published chain conclusion per claim, from the `TRACED_TO` edges.

    `ALL_TRACES` returns a row per role, so origin and carriers arrive
    separately and are folded back into the one conclusion the board draws.
    """
    by_claim: dict[str, dict] = {}
    for row in case.traces():
        entry = by_claim.setdefault(
            row["claim_id"],
            {
                "claim_id": row["claim_id"],
                "speaker": "",
                "terminal": row["terminal"],
                "origin_agent": None,
                "is_origin": False,
                "is_ungrounded": bool(row.get("ungrounded")),
                "carriers": [],
                "detail": "",
                # Deliberately empty: a hop names a private fact. See the
                # module docstring.
                "hops": [],
            },
        )
        if row.get("role") == "origin":
            entry["origin_agent"] = row["agent"]
            entry["is_origin"] = True
        else:
            entry["carriers"].append(row["agent"])
    return list(by_claim.values())


def board_payload(
    case: CaseGraph, seed: int, *, polygraphs_left: int | None = None
) -> dict[str, Any]:
    """Everything the board draws, in the shape the fixture already has.

    `polygraphs_left` is the detective's remaining budget, which the board
    shows on the recorder. It is the one number here that is not read off the
    case graph, because a budget is a property of the investigation rather
    than of the case; a dumped fixture carries none and the board falls back
    to the full budget.
    """
    claims = case.all_claims()
    support = case.support_shadows()
    conflict = case.conflict_shadows()
    gaps = case.gaps()

    # The per-claim rollups the board reads off each bar. Built exactly as the
    # dump builds them: covered spans come from the slice each support shadow
    # was recorded as covering, never recomputed here.
    per_claim: dict[str, dict] = {
        c["id"]: {"covered": [], "gaps": [], "support": [], "conflict": []} for c in claims
    }
    for row in support:
        entry = per_claim.get(row["claim_id"])
        if entry is not None:
            entry["covered"].append([row["covers_t0"], row["covers_t1"]])
            entry["support"].append(row["id"])
    for row in conflict:
        entry = per_claim.get(row["claim_id"])
        if entry is not None:
            entry["conflict"].append(row["id"])
    for row in gaps:
        entry = per_claim.get(row["claim_id"])
        if entry is not None:
            entry["gaps"].append([row["t0"], row["t1"]])

    claims_out = []
    for c in claims:
        extra = per_claim[c["id"]]
        claims_out.append(
            {
                **c,
                "covered": sorted(extra["covered"]),
                "gaps": sorted(extra["gaps"]),
                "support": extra["support"],
                "conflict": extra["conflict"],
            }
        )

    places = case.places()
    place_ids = [p["id"] for p in places]
    # Read cell by cell out of the precomputed TRAVEL_TIME edges — the same
    # cells the impossible-travel check reads, so the board and the check can
    # never disagree about a pair.
    travel: dict[str, int] = {}
    routes: dict[str, list[str]] = {}
    for a in place_ids:
        for b in place_ids:
            if a == b:
                continue
            minutes = case.travel_minutes(a, b)
            if minutes is None:
                continue
            travel[f"{a}|{b}"] = minutes
            found = case.shortest_path(a, b)
            if found is not None:
                routes[f"{a}|{b}"] = list(found[1])

    speakers = {c["speaker"] for c in claims}
    return {
        "meta": {
            "seed": seed,
            "case_id": f"0x{seed:04X}",
            "tick_min": 0,
            "tick_max": TICK_MAX,
            "hour_labels": [
                {"tick": t, "label": _tick_label(t)} for t in range(0, TICK_MAX + 1, 60)
            ],
            "claims": len(claims_out),
            "audited": sum(1 for c in claims_out if c["verdict"] != PENDING),
            "interviews": len(speakers),
            "live": True,
            "polygraphs_left": polygraphs_left,
        },
        "suspects": case.suspects(),
        "incident": case.incident(),
        "claims": claims_out,
        "evidence": {"support": support, "conflict": conflict},
        "contradictions": case.contradictions(),
        "chains": _chain_rows(case),
        "tally": case.verdict_tally(),
        "floor_plan": {
            "places": places,
            "corridors": case.adjacency(),
            "travel": travel,
            "routes": routes,
        },
        "audit_summary": {
            "uncovered_minutes": sum(int(c["uncovered"] or 0) for c in claims),
            "claims_with_gaps": sum(1 for c in claims_out if c["gaps"]),
        },
    }
