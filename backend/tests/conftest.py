"""Shared fixtures. The graph-backed tests talk to a real FalkorDB.

There is deliberately no mock and no skip-if-unreachable. A mocked graph would
prove the Python decided correctly about rows it invented; the thing worth
testing is that these Cypher queries return what the decision table expects
from the server we pinned. If FalkorDB is down, these tests fail loudly with
instructions rather than passing vacuously.
"""

from __future__ import annotations

import itertools

import pytest

from backend.app.config import settings
from backend.app.db import connect

_counter = itertools.count()


@pytest.fixture(scope="session")
def db():
    try:
        client = connect()
        client.connection.ping()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"cannot reach FalkorDB at {settings.falkor_host}:{settings.falkor_port} "
            f"({type(exc).__name__}: {exc}). Run `make up`. Note this machine "
            f"publishes FalkorDB on 6380, so drive the tests through `make test` "
            f"— the Makefile exports FALKOR_PORT, a bare pytest will not."
        ) from exc
    return client


@pytest.fixture
def scratch_seed():
    """A seed unique to one test, so parallel graphs cannot collide."""
    return 900_000 + next(_counter)


@pytest.fixture
def graphs(db, scratch_seed):
    """Hands out graphs and deletes every one it handed out, pass or fail."""
    handed_out = []

    def take(name: str):
        g = db.select_graph(name)
        handed_out.append(g)
        return g

    yield take
    for g in handed_out:
        try:
            g.delete()
        except Exception:  # noqa: BLE001, S110
            pass  # teardown only: a graph never created has nothing to drop


# -- the LLM transport, scripted --------------------------------------------
#
# The graph is never faked in this suite, and these do not fake it. What they
# stand in for is the HTTP transport: one request document in, one response
# document out, which is exactly the `Completer` contract that `CachedLLM`
# calls and records. Everything downstream of the response — every tool, every
# query, every verdict — is the real thing.
#
# A scripted detective is also the honest way to test a decision loop. What is
# worth asserting is that the loop drives the real tools, respects the budget
# and the cap, and lets no model output become a verdict. None of that is a
# property of which model answered.


class ScriptedCompleter:
    """A transport that answers from a fixed script, turn by turn.

    Each step is either `("tool", name, args)` or `("say", text)`. Running off
    the end of the script yields a text turn, which the loop answers by asking
    for a tool call — so a short script cannot make a run hang, it makes it
    reach the cap.
    """

    def __init__(self, script, *, model: str = "scripted"):
        self.script = list(script)
        self.model = model
        self.requests: list[dict] = []

    def __call__(self, request: dict) -> dict:
        n = len(self.requests)
        self.requests.append(request)
        step = self.script[n] if n < len(self.script) else ("say", "Still looking.")
        usage = {"input_tokens": 100 + n, "output_tokens": 20}
        if step[0] == "tool":
            _, name, args = step
            return {
                "id": f"msg_{n}",
                "model": self.model,
                "stop_reason": "tool_use",
                "content": [
                    {"type": "text", "text": f"Turn {n}: calling {name}."},
                    {"type": "tool_use", "id": f"toolu_{n}", "name": name, "input": args},
                ],
                "usage": usage,
            }
        return {
            "id": f"msg_{n}",
            "model": self.model,
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": step[1]}],
            "usage": usage,
        }

    @property
    def calls(self) -> int:
        return len(self.requests)


class RefusingCompleter:
    """A transport that fails if it is reached at all.

    This is how "the replay made zero API calls" is asserted rather than
    reported: a run that touched the network under this transport does not
    produce a smaller number, it fails.
    """

    def __init__(self) -> None:
        self.attempts = 0

    def __call__(self, request: dict) -> dict:
        self.attempts += 1
        raise AssertionError(
            "the transport was reached during a run that was supposed to replay "
            "from cache"
        )
