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
