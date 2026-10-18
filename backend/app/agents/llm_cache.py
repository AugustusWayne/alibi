"""The LLM replay cache and the hard per-case call cap (spec 3, project rules, rule 9).

Every LLM call in this system goes through `CachedLLM`. Nothing else may hold a
model client. Two separate jobs live here, and both are required by rule 9:

**The cache.** SQLite, keyed by `(seed, agent, prompt_hash)` exactly as spec 3
and spec 7 specify. The first run of a case costs money and varies; every run
after it replays bit-identically from this table at zero API calls, which is
what makes the demo and the benchmark reproducible without taking the models
out of the system. The key is three parts because a prompt hash alone would
collide across cases that ask the same question of different worlds, and an
agent's replay must never be served another agent's answer.

**The cap.** A hard ceiling on calls per case, enforced in code before the
transport is reached. It bounds cost on a run that is not yet cached and it
bounds the detective's loop, which would otherwise be terminated only by the
model's own willingness to stop.

**A cache hit still spends a call.** The cap counts attempts, not misses. If
replay were uncapped, a cached run could take more turns than the live run it
replays, and "bit-identical replay" would be false the moment a case ran long.
`api_calls` is tracked separately, and it is the number this system reports as
the cost of a run.

**SQLite is for the replay cache and eval metadata only, never graph state**
(spec 3). Nothing in this module knows what a claim or a verdict is.

**No verdict is produced here.** This module moves opaque request and response
documents. It never inspects them, and a model's answer never becomes a
verdict anywhere downstream of it (rule 1).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_CALL_CAP = 24
"""Calls per case. A detective with seven tools and two polygraphs that has not
concluded in two dozen turns is not going to, and a runaway loop against a live
API is the one failure mode that costs real money while looking like progress."""

# -- SQL. Not Cypher: no graph state is ever written here (spec 3). Kept as
# named constants beside each other for the same reason the Cypher is — one
# place to read what this store actually does.

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS llm_calls (
    seed        INTEGER NOT NULL,
    agent       TEXT    NOT NULL,
    prompt_hash TEXT    NOT NULL,
    model       TEXT    NOT NULL,
    request     TEXT    NOT NULL,
    response    TEXT    NOT NULL,
    PRIMARY KEY (seed, agent, prompt_hash)
)
"""
"""The replay table. The primary key is spec 3's cache key, so a second write
of the same key is the same question being asked again, not a new row."""

SELECT_CALL = """
SELECT response FROM llm_calls
WHERE seed = ? AND agent = ? AND prompt_hash = ?
"""
"""What did this agent answer, in this case, to exactly this prompt?"""

INSERT_CALL = """
INSERT OR REPLACE INTO llm_calls (seed, agent, prompt_hash, model, request, response)
VALUES (?, ?, ?, ?, ?, ?)
"""
"""Record one live answer so the next run of this case never asks again."""

COUNT_CALLS = "SELECT COUNT(*) FROM llm_calls WHERE seed = ?"
"""How many distinct prompts has this case recorded?"""

DELETE_SEED = "DELETE FROM llm_calls WHERE seed = ?"
"""Forget one case's recordings, so it can be re-recorded from scratch."""


class CallCapExceeded(RuntimeError):
    """The per-case LLM call cap is spent.

    Raised rather than returning a synthetic answer. A fabricated final turn
    would put words in the model's mouth and then let the loop act on them.
    """


class CacheMiss(LookupError):
    """A prompt was not in the cache and this run is not allowed to call out.

    Replay-only runs raise this instead of quietly reaching the network: a
    benchmark that silently started spending money would stop being a replay.
    """


def prompt_hash(request: dict) -> str:
    """Hash a whole request document, canonically.

    Everything that can change the answer is in the hash — model, system,
    messages, tools, sampling and effort settings — because anything left out
    would let two different questions share one cached answer. Keys are
    sorted so Python's dict ordering cannot change a hash between runs.
    """
    canonical = json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class LLMCache:
    """The SQLite store behind `CachedLLM`. Opened once, shared across threads.

    `check_same_thread=False` with a lock, because the API serves a case from a
    worker thread while the request thread reads counters. SQLite is perfectly
    happy with that as long as one lock serializes the writes, and this store
    sees a handful of rows per case.
    """

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute(CREATE_TABLE)
        self._conn.commit()

    def get(self, *, seed: int, agent: str, prompt_hash: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(SELECT_CALL, (seed, agent, prompt_hash)).fetchone()
        return None if row is None else json.loads(row[0])

    def put(
        self,
        *,
        seed: int,
        agent: str,
        prompt_hash: str,
        model: str,
        request: dict,
        response: dict,
    ) -> None:
        payload = (
            seed,
            agent,
            prompt_hash,
            model,
            json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
            json.dumps(response, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
        )
        with self._lock:
            self._conn.execute(INSERT_CALL, payload)
            self._conn.commit()

    def count(self, seed: int) -> int:
        with self._lock:
            return int(self._conn.execute(COUNT_CALLS, (seed,)).fetchone()[0])

    def forget(self, seed: int) -> None:
        """Drop one case's recordings. Re-recording a case is an explicit act."""
        with self._lock:
            self._conn.execute(DELETE_SEED, (seed,))
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()


@dataclass
class CallLedger:
    """What one case spent. The cost column of spec 8.3.

    `calls` is turns taken, `api_calls` is turns that actually reached the
    model. A fully replayed case has `api_calls == 0` and that is the figure
    worth reporting.
    """

    calls: int = 0
    hits: int = 0
    api_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    per_agent: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "calls": self.calls,
            "hits": self.hits,
            "api_calls": self.api_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "per_agent": dict(self.per_agent),
        }


Completer = Callable[[dict], dict]
"""A transport: one request document in, one response document out.

Deliberately a plain callable over plain dicts. The cache stores exactly what
goes over the wire, so a replayed turn and a live turn are the same bytes
through the same code, and no SDK object has to survive a round trip to disk.
"""


class CachedLLM:
    """The only way to call a model in this system.

    Bound to one case by `seed`, so a caller cannot read another case's replay
    even by accident — the same reason no agent tool takes a graph name
    (rule 6).
    """

    def __init__(
        self,
        cache: LLMCache,
        *,
        seed: int,
        completer: Completer | None = None,
        cap: int = DEFAULT_CALL_CAP,
        replay_only: bool = False,
    ) -> None:
        self._cache = cache
        self._seed = seed
        self._completer = completer
        self._cap = cap
        self._replay_only = replay_only
        self.ledger = CallLedger()

    @property
    def seed(self) -> int:
        return self._seed

    @property
    def cap(self) -> int:
        return self._cap

    @property
    def calls_left(self) -> int:
        return self._cap - self.ledger.calls

    def complete(self, request: dict, *, agent: str) -> dict:
        """One turn. Cache first, cap always, transport only on a miss.

        The cap is checked before the cache, because the cap bounds the loop
        and a replayed loop must take the same number of turns as the live one
        it is replaying.
        """
        if self.ledger.calls >= self._cap:
            raise CallCapExceeded(
                f"case {self._seed}: the per-case LLM call cap of {self._cap} is spent "
                f"({self.ledger.api_calls} of them reached the API). Raise the cap "
                f"deliberately or shorten the loop; this is not a transient failure."
            )

        digest = prompt_hash(request)
        self.ledger.calls += 1
        self.ledger.per_agent[agent] = self.ledger.per_agent.get(agent, 0) + 1

        cached = self._cache.get(seed=self._seed, agent=agent, prompt_hash=digest)
        if cached is not None:
            self.ledger.hits += 1
            self._count_usage(cached)
            return cached

        if self._replay_only:
            raise CacheMiss(
                f"case {self._seed}: agent {agent!r} asked a prompt "
                f"({digest[:12]}) that is not in {self._cache.path}. This run is "
                f"replay-only, so nothing was sent. Record the case once with "
                f"replay_only=False, or check what changed the prompt."
            )
        if self._completer is None:
            raise CacheMiss(
                f"case {self._seed}: agent {agent!r} missed the cache and no "
                f"completer is configured, so there is nothing to call."
            )

        response = self._completer(request)
        self.ledger.api_calls += 1
        self._count_usage(response)
        self._cache.put(
            seed=self._seed,
            agent=agent,
            prompt_hash=digest,
            model=str(request.get("model", "")),
            request=request,
            response=response,
        )
        return response

    def _count_usage(self, response: dict) -> None:
        usage = response.get("usage") or {}
        self.ledger.input_tokens += int(usage.get("input_tokens") or 0)
        self.ledger.output_tokens += int(usage.get("output_tokens") or 0)


def sdk_completer(client: Any = None) -> Completer:
    """The live transport. The model vendor's SDK is imported here and nowhere else.

    One function is the whole coupling to it. Imported lazily so the scripted
    path, the eval harness and every replayed run work with the SDK absent and
    no key configured — which is most of the time, and all of CI.

    The import name, the pinned package and the model id elsewhere in this
    repo are third-party identifiers the program needs in order to resolve and
    call: they are not this project's own naming and nothing here is attributed
    to a vendor.
    """

    def complete(request: dict) -> dict:
        nonlocal client
        if client is None:
            import llm_sdk  # noqa: PLC0415 — deliberately lazy; see the docstring

            client = llm_sdk.Client()
        message = client.messages.create(**request)
        return message.to_dict()

    return complete
