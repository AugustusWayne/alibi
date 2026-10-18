"""One case in flight: its graphs, its tools, its event log, its worker thread.

The board watches a case unfold, so a case has to exist between requests and
emit as it goes. This module is that state and nothing more — it owns no
Cypher (`CaseGraph` does) and makes no decision about a claim.

**A case is keyed by its seed, and one seed has one case.** The graphs are
named `world:{seed}`, `mind:{seed}:{agent}` and `case:{seed}`, so two
concurrent cases on one seed would be one case with two sets of books. The
registry refuses the second rather than quietly sharing.

**A seed's graphs are dropped before it is generated as well as after.**
`CREATE_PRESENCE` and `ingest_claim` append: generating into graphs an earlier
run left behind doubles the world, and every count the board shows comes out
wrong by a factor that looks plausible. This is the same hazard the eval
harness documents, and it is a real one on a FalkorDB shared between
checkouts.
"""

from __future__ import annotations

import threading
import traceback
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from backend.app.agents.detective import DetectiveTools
from backend.app.agents.llm_cache import CachedLLM, LLMCache
from backend.app.agents.loop import DetectiveLoop, Event, briefing
from backend.app.agents.scripted import build_suspects, interview_all
from backend.app.audit.engine import AuditEngine
from backend.app.case.graph import CaseGraph, case_graph_name
from backend.app.config import settings
from backend.app.db import connect
from backend.app.minds.access import mind_graph_name
from backend.app.world.generator import WorldSpec, generate, plan_world, world_graph_name


class EventBus:
    """An append-only log with a sequence number, read by any number of streams.

    Buffered rather than broadcast: a board that connects halfway through a
    case gets the whole case, and a reconnect resumes from a cursor instead of
    losing the turns it missed.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: list[dict] = []
        self._closed = False

    def publish(self, event: Event | dict) -> None:
        """Append one event, renumbering it to this bus's own sequence.

        The loop numbers its own events from zero and the bus also carries the
        case's generation events, so the bus is the authority on order.
        """
        payload = event.as_dict() if isinstance(event, Event) else dict(event)
        with self._lock:
            self._events.append({**payload, "seq": len(self._events)})

    def emit(self, type_: str, **data: Any) -> None:
        self.publish(
            {
                "type": type_,
                "at": datetime.now(UTC).isoformat(timespec="milliseconds"),
                "data": data,
            }
        )

    def since(self, cursor: int) -> list[dict]:
        with self._lock:
            return list(self._events[cursor:])

    def close(self) -> None:
        with self._lock:
            self._closed = True

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._closed

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._events)


@dataclass
class CaseSession:
    """Everything one open case holds. Public information only."""

    seed: int
    db: Any
    plan: Any
    case: CaseGraph
    tools: DetectiveTools
    bus: EventBus = field(default_factory=EventBus)
    status: str = "ready"
    investigation: dict | None = None
    error: str | None = None
    thread: threading.Thread | None = None

    @property
    def people(self) -> list[str]:
        return [p.id for p in self.plan.people]

    def summary(self) -> dict:
        """What the board shows above the strip rows.

        Counts and rosters, drawn from the case graph. The culprit is not here
        and cannot be: `GroundTruth` lives in the referee and this object has
        no handle on it.
        """
        return {
            "seed": self.seed,
            "status": self.status,
            "error": self.error,
            "suspects": self.case.suspects(),
            "places": self.case.places(),
            "incident": self.case.incident(),
            "claims": len(self.case.all_claims()),
            "verdicts": self.case.verdict_tally(),
            "contradictions": len(self.case.contradictions()),
            "gaps": len(self.case.gaps()),
            "traces": len(self.case.traces()),
            "polygraphs_left": self.tools.polygraphs_left,
            "tool_calls": self.tools.calls,
            "accusation": self.investigation,
        }


def graph_names(seed: int, people: list[str]) -> list[str]:
    """Every graph one seed owns."""
    return [world_graph_name(seed), case_graph_name(seed)] + [
        mind_graph_name(seed, agent) for agent in people
    ]


def drop_seed(db: Any, seed: int, people: list[str]) -> None:
    """Delete a seed's graphs. Teardown only, and it reports nothing."""
    for name in graph_names(seed, people):
        try:
            db.select_graph(name).delete()
        except Exception:  # noqa: BLE001, S110
            pass  # a graph never created has nothing to drop


def open_case(seed: int, *, spec: WorldSpec | None = None, db: Any = None) -> CaseSession:
    """Generate a world, take the first round of statements, audit them.

    The suspects here are scripted, which is the tested default path and the
    `--scripted` mode of spec 7. The detective is the only model in the
    system; nothing in this function calls one.
    """
    spec = spec or WorldSpec()
    db = db if db is not None else connect()
    plan = plan_world(spec.plan_seed if spec.plan_seed is not None else seed, spec)
    people = [p.id for p in plan.people]

    bus = EventBus()
    bus.emit("case.generating", seed=seed, people=people)
    drop_seed(db, seed, people)
    counts = generate(db, seed, spec=spec)
    bus.emit("case.generated", seed=seed, counts=counts)

    interview_all(db, seed, plan=plan)
    audited = AuditEngine(db, seed).audit_all()
    bus.emit("case.audited", seed=seed, claims=len(audited))

    session = CaseSession(
        seed=seed,
        db=db,
        plan=plan,
        case=CaseGraph(db, seed),
        tools=DetectiveTools(db, seed, suspects=build_suspects(db, seed, plan=plan)),
        bus=bus,
    )
    bus.emit("case.ready", **session.summary())
    return session


def investigate(
    session: CaseSession,
    *,
    cache: LLMCache,
    model: str | None = None,
    max_turns: int | None = None,
    cap: int | None = None,
    replay_only: bool = False,
    completer: Any = None,
) -> dict:
    """Run the detective loop on an open case, publishing every turn.

    Synchronous. `start_investigation` is what puts it on a thread; keeping
    the two apart means a test can run a whole case without a scheduler.
    """
    llm = CachedLLM(
        cache,
        seed=session.seed,
        completer=completer,
        cap=cap if cap is not None else settings.llm_call_cap,
        replay_only=replay_only,
    )
    loop = DetectiveLoop(
        session.tools,
        llm,
        model=model or settings.detective_model,
        briefing=briefing(
            seed=session.seed,
            suspects=session.case.suspects(),
            places=session.case.places(),
            incident=session.case.incident(),
            claim_count=len(session.case.all_claims()),
            polygraph_budget=session.tools.polygraphs_left,
        ),
        max_turns=max_turns,
        on_event=session.bus.publish,
    )
    session.status = "investigating"
    result = loop.run().as_dict()
    session.investigation = result
    session.status = "closed" if result["accusation"] is not None else "exhausted"
    return result


def start_investigation(session: CaseSession, **kwargs: Any) -> threading.Thread:
    """Put `investigate` on a worker thread so the SSE stream can be watched live.

    A failure is published and recorded, not swallowed: a case that broke says
    so on the stream, with its traceback, and its status says `failed`.
    Nothing here turns an error into an empty result (rule 8).
    """

    def work() -> None:
        try:
            investigate(session, **kwargs)
        except Exception as exc:  # noqa: BLE001 — reported, never hidden
            session.status = "failed"
            session.error = f"{type(exc).__name__}: {exc}"
            session.bus.emit(
                "investigation.failed",
                error=session.error,
                traceback=traceback.format_exc(),
            )
        finally:
            session.bus.close()

    thread = threading.Thread(target=work, name=f"case-{session.seed}", daemon=True)
    session.thread = thread
    thread.start()
    return thread


class CaseRegistry:
    """The open cases, one per seed, and the replay cache they share.

    The cache is opened on first use rather than at construction, so importing
    the API does not create a SQLite file as a side effect.
    """

    def __init__(self, cache_path: str | None = None) -> None:
        self._lock = threading.Lock()
        self._cases: dict[int, CaseSession] = {}
        self._cache_path = cache_path
        self._cache: LLMCache | None = None

    @property
    def cache(self) -> LLMCache:
        with self._lock:
            if self._cache is None:
                self._cache = LLMCache(self._cache_path or settings.llm_cache_path)
            return self._cache

    def add(self, session: CaseSession) -> None:
        with self._lock:
            if session.seed in self._cases:
                raise ValueError(
                    f"case {session.seed} is already open; its graphs are "
                    f"{graph_names(session.seed, session.people)} and a second "
                    f"case on this seed would share them. Close it first."
                )
            self._cases[session.seed] = session

    def get(self, seed: int) -> CaseSession | None:
        with self._lock:
            return self._cases.get(seed)

    def seeds(self) -> list[int]:
        with self._lock:
            return sorted(self._cases)

    def close(self, seed: int) -> CaseSession | None:
        with self._lock:
            session = self._cases.pop(seed, None)
        if session is not None:
            session.bus.close()
            drop_seed(session.db, seed, session.people)
        return session


registry = CaseRegistry()
"""The process-wide registry the routes read. One per server."""
