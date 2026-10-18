"""The case routes and the SSE stream.

**What a route may serve.** The case graph, and only the case graph. A claim
with its verdict, the contradictions and gaps the audit materialized, the
scoreboard, the traces a polygraph paid for, and the event log. No mind, no
private fact, no ground-truth label (project rules, rules 2 and 6). The
resources are addressed by seed because the graphs are; no route takes a graph
name or an agent id.

**The scoreboard here is Q8's four original columns**, through the same
`rank_suspects` scoring function the detective's tool uses — but not through
the tool. The tool surface is the detective's rationed view: it closes when
the case is accused and it counts every call into the per-case cost column of
spec 8.3. A board refreshing a panel must not close with the case, and must
not be billed to the detective. The trace-derived origin and carrier columns
are a separate query on the referee/eval/reveal path and are not reachable
from here at all.

**No Cypher lives in this file.** Every read goes through `CaseGraph` or
`DetectiveTools`, whose queries are named constants in their own
`queries.py`.

**The stream.** `GET /cases/{seed}/events` is `text/event-stream`: the whole
buffered log first, then each new event as it lands, so a board that connects
late still sees the case from the beginning. It ends when the case's bus
closes or when `timeout` seconds pass, because an SSE response that can never
end is a leaked connection.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from backend.app.api import runner
from backend.app.api.board import board_payload
from backend.app.case.scoreboard import rank_suspects
from backend.app.config import settings
from backend.app.world.generator import WorldSpec

router = APIRouter(prefix="/cases", tags=["cases"])

POLL_SECONDS = 0.05
"""How often an open stream looks for new events. Small enough that a board
sees a turn as it happens, large enough that an idle case costs nothing."""


class OpenCaseRequest(BaseModel):
    """Open a case on one seed."""

    seed: int = Field(description="The seed. Its graphs are named from it.")
    pathologies: bool = Field(
        default=False,
        description=(
            "Also plant the broken-chain and temporal-violation chains, which "
            "make the terminal states of a provenance trace reachable."
        ),
    )


class InvestigateRequest(BaseModel):
    """Run the detective on an open case."""

    model: str | None = None
    max_turns: int | None = None
    cap: int | None = Field(
        default=None, description="Hard per-case LLM call cap. Defaults to the setting."
    )
    replay_only: bool = Field(
        default=False,
        description=(
            "Refuse to reach the API. A prompt that is not already in the "
            "replay cache fails the run rather than spending money."
        ),
    )


def _session(seed: int) -> runner.CaseSession:
    session = runner.registry.get(seed)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"no case is open on seed {seed}; POST /cases to open one",
        )
    return session


@router.post("", status_code=201)
def open_case(body: OpenCaseRequest) -> JSONResponse:
    """Generate a world, take the first statements, audit them, hold the case open."""
    spec = WorldSpec(
        plant_broken_chain=body.pathologies,
        plant_temporal_violation=body.pathologies,
    )
    try:
        session = runner.registry.open_exclusive(body.seed, spec=spec)
    except ValueError as exc:
        # Raised from inside the open lock, so this is authoritative: the case
        # exists and this caller did not generate anything.
        raise HTTPException(
            status_code=409,
            detail=(
                f"{exc}; its graphs are keyed by seed, so a second case on it "
                f"would share them. DELETE it first."
            ),
        ) from exc
    return JSONResponse(status_code=201, content=session.summary())


@router.get("")
def list_cases() -> dict:
    """The seeds with an open case."""
    return {"seeds": runner.registry.seeds()}


@router.get("/{seed}")
def case_summary(seed: int) -> dict:
    return _session(seed).summary()


@router.get("/{seed}/claims")
def case_claims(seed: int) -> dict:
    """Every claim with the verdict the audit gave it. No LIMIT, and no filter."""
    return {"claims": _session(seed).case.all_claims()}


@router.get("/{seed}/contradictions")
def case_contradictions(seed: int) -> dict:
    return {"contradictions": _session(seed).case.contradictions()}


@router.get("/{seed}/gaps")
def case_gaps(seed: int, suspect: str | None = None) -> dict:
    """The spans a suspect's own memory did not account for.

    `suspect` names a party in the public case file, not a memory store —
    the same reason the tool of this name takes one (rule 6).
    """
    return {"gaps": _session(seed).case.gaps_by_speaker(suspect)}


@router.get("/{seed}/scoreboard")
def case_scoreboard(seed: int) -> dict:
    """Q8's four columns, ranked, with the breakdown beside every total.

    The rows come from the case graph and the ranking from the one scoring
    function, deliberately not from `DetectiveTools.rank_suspects`: a board
    reading this panel is not the detective spending a turn, and a closed
    case still has a scoreboard to show.
    """
    return {"rows": rank_suspects(_session(seed).case.scoreboard_rows())}


@router.get("/{seed}/traces")
def case_traces(seed: int) -> dict:
    """The chain conclusions a polygraph paid for, and no others.

    Empty until the detective spends a polygraph. That is the point of the
    budget: `polygraph` is the only writer of `TRACED_TO` in the application.
    """
    return {"traces": _session(seed).case.traces()}


@router.get("/{seed}/board")
def case_board(seed: int) -> dict:
    """Everything the board draws, in one read, public information only.

    One request rather than six, because the board redraws from a whole case
    and a half-applied update would show a claim beside a tally that does not
    count it. The SSE stream says when to ask again.
    """
    session = _session(seed)
    return board_payload(
        session.case, seed, polygraphs_left=session.tools.polygraphs_left
    )


@router.get("/{seed}/events")
async def case_events(
    seed: int,
    cursor: int = Query(default=0, ge=0, description="Resume from this sequence number."),
    follow: bool = Query(default=True, description="Stay open for new events."),
    timeout: float = Query(default=120.0, gt=0, description="Seconds before closing."),
) -> StreamingResponse:
    """The case as a stream of events, from `cursor` onward."""
    bus = _session(seed).bus

    async def stream() -> Any:
        sent = cursor
        waited = 0.0
        while True:
            batch = bus.since(sent)
            for event in batch:
                sent = event["seq"] + 1
                waited = 0.0
                yield _sse(event)
            if not follow:
                break
            if bus.closed and not bus.since(sent):
                yield _sse({"seq": sent, "type": "stream.closed", "at": None, "data": {}})
                break
            if waited >= timeout:
                yield _sse(
                    {
                        "seq": sent,
                        "type": "stream.timeout",
                        "at": None,
                        "data": {"after_seconds": waited},
                    }
                )
                break
            await asyncio.sleep(POLL_SECONDS)
            waited += POLL_SECONDS

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{seed}/investigate", status_code=202)
def start_investigation(seed: int, body: InvestigateRequest | None = None) -> dict:
    """Start the detective loop on a worker thread and return at once.

    202, not 200: the case is accepted and will unfold on the stream. A board
    that wants the outcome watches `GET /cases/{seed}/events` or polls the
    summary.
    """
    session = _session(seed)
    if session.status == "investigating":
        raise HTTPException(
            status_code=409, detail=f"case {seed} is already being investigated"
        )
    if session.tools.accusation is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"case {seed} is closed: {session.tools.accusation.suspect} was "
                f"already accused"
            ),
        )
    body = body or InvestigateRequest()
    runner.start_investigation(
        session,
        cache=runner.registry.cache,
        model=body.model,
        max_turns=body.max_turns,
        cap=body.cap,
        replay_only=body.replay_only,
        completer=None if body.replay_only else _live_completer(),
    )
    return {"seed": seed, "status": "investigating"}


@router.delete("/{seed}")
def close_case(seed: int) -> dict:
    """Close a case and drop its graphs.

    The graphs are keyed by seed on a FalkorDB shared between checkouts, so a
    case left open is a world left on someone else's server.
    """
    _session(seed)
    runner.registry.close(seed)
    return {"seed": seed, "status": "closed"}


def _live_completer() -> Any:
    """The transport for a run that is allowed to reach a model.

    Resolved here rather than at import so a server with no transport
    configured still starts, serves the case graph and replays cases. It
    raises if `ALIBI_COMPLETER` is unset, which surfaces on the stream as a
    failed investigation rather than as a case that quietly did nothing.
    """
    from backend.app.agents.llm_cache import load_completer  # noqa: PLC0415

    return load_completer(settings.completer)


def _sse(event: dict) -> str:
    """One Server-Sent Event.

    `id` carries the sequence number, which is what a reconnecting board hands
    back as `cursor`.
    """
    return (
        f"id: {event['seq']}\n"
        f"event: {event['type']}\n"
        f"data: {json.dumps(event, default=str)}\n\n"
    )
