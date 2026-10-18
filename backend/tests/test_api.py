"""The case routes and the SSE stream, and the seam they are not allowed to cross.

The routes are the only part of this system a browser can reach, so this file
spends most of its length on what must *not* come out of them:

- **No mind.** There is no route that reads one and no parameter that names
  one (project rules, rule 6). `test_no_route_path_names_a_mind_a_world_or_a_
  truth` reads the app's own OpenAPI schema rather than a list maintained by
  hand, so a route added later is covered by it.
- **No ground-truth label.** The four labels in `referee/ground_truth.py` are
  scoring vocabulary (spec 8.1). `test_no_response_body_carries_a_ground_
  truth_label` walks every readable route on a real case and checks the
  serialized body.
- **No intent vocabulary.** A verdict describes grounding (rule 2). The same
  walk checks the words.

The graph is real. The LLM transport is scripted — see the note above
`ScriptedCompleter` in `conftest.py`.
"""

from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from backend.app.agents.llm_cache import LLMCache
from backend.app.agents.loop import INTENT_WORDS
from backend.app.api import routes, runner
from backend.app.main import app
from backend.app.referee.ground_truth import ALL_LABELS
from backend.tests.conftest import ScriptedCompleter

READ_ROUTES = (
    "",
    "/claims",
    "/contradictions",
    "/gaps",
    "/scoreboard",
    "/traces",
)
"""Every route that returns case data. Held against the app's own schema by
`test_every_case_route_is_covered_by_the_seam_walk`, so a route added without
a seam check fails here."""


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def case(client, scratch_seed, db):
    """An open case on a throwaway seed, closed and dropped either way.

    `runner.registry` is process-wide, as it is in a running server. A test
    that left a case in it would leave its graphs on a FalkorDB other
    checkouts are working against.
    """
    response = client.post("/cases", json={"seed": scratch_seed, "pathologies": True})
    assert response.status_code == 201, response.text
    try:
        yield scratch_seed
    finally:
        runner.registry.close(scratch_seed)


def _script_for(seed: int) -> list[tuple]:
    claims = runner.registry.get(seed).case.all_claims()
    target = claims[0]
    return [
        ("tool", "rank_suspects", {}),
        ("tool", "list_gaps", {"suspect": None}),
        ("tool", "polygraph", {"suspect": target["speaker"], "claim_id": target["id"]}),
        (
            "tool",
            "accuse",
            {
                "suspect": target["speaker"],
                "rationale": "Their own memory does not account for the claimed span.",
            },
        ),
    ]


@pytest.fixture
def scripted_detective(monkeypatch):
    """Point the investigate route at a scripted transport.

    The route builds its transport through one function so a test can replace
    exactly that and leave the rest of the path — the registry, the thread,
    the cache, the loop, the tools — running for real.
    """
    holder = {}

    def install(seed: int):
        completer = ScriptedCompleter(_script_for(seed))
        holder["completer"] = completer
        monkeypatch.setattr(routes, "_live_completer", lambda: completer)
        monkeypatch.setattr(runner.registry, "_cache", LLMCache(), raising=False)
        return completer

    install.holder = holder
    return install


def _finish(seed: int, timeout: float = 20.0) -> dict:
    """Wait for the worker thread to put the case down, then report it."""
    session = runner.registry.get(seed)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if session.status in {"closed", "exhausted", "failed"}:
            return session.summary()
        time.sleep(0.02)
    raise AssertionError(f"case {seed} was still {session.status} after {timeout}s")


# -- opening and closing a case ----------------------------------------------


def test_health_still_reports_the_database(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"


def test_opening_a_case_generates_audits_and_reports_it(client, case):
    body = client.get(f"/cases/{case}").json()

    assert body["seed"] == case
    assert body["status"] == "ready"
    assert body["claims"] > 0
    assert len(body["suspects"]) == len(runner.registry.get(case).people)
    assert sum(body["verdicts"].values()) == body["claims"]
    assert body["polygraphs_left"] == 2
    assert body["traces"] == 0


def test_a_second_case_on_the_same_seed_is_refused(client, case):
    """One seed, one case. The graphs are named from the seed, so two cases on
    it would be one case keeping two sets of books."""
    response = client.post("/cases", json={"seed": case})

    assert response.status_code == 409
    assert "already open" in response.json()["detail"]


def test_an_unopened_seed_is_a_404_not_an_empty_case(client, scratch_seed):
    """Rule 8 at the edge: nothing invents an empty case file."""
    response = client.get(f"/cases/{scratch_seed}")

    assert response.status_code == 404
    assert str(scratch_seed) in response.json()["detail"]


def test_closing_a_case_drops_its_graphs(client, scratch_seed, db):
    client.post("/cases", json={"seed": scratch_seed})
    people = runner.registry.get(scratch_seed).people

    assert client.delete(f"/cases/{scratch_seed}").status_code == 200

    live = set(db.list_graphs())
    assert not (set(runner.graph_names(scratch_seed, people)) & live)
    assert client.get(f"/cases/{scratch_seed}").status_code == 404


# -- what the case routes serve ----------------------------------------------


def test_the_read_routes_serve_the_case_graph(client, case):
    claims = client.get(f"/cases/{case}/claims").json()["claims"]
    scoreboard = client.get(f"/cases/{case}/scoreboard").json()["rows"]

    assert claims and all("verdict" in c for c in claims)
    assert scoreboard and all("score" in r and "breakdown" in r for r in scoreboard)
    assert client.get(f"/cases/{case}/traces").json()["traces"] == []


def test_the_scoreboard_route_keeps_q8s_four_original_columns(client, case):
    """The trace-derived origin and carrier columns are the referee's split and
    are not reachable from a detective-facing route."""
    rows = client.get(f"/cases/{case}/scoreboard").json()["rows"]

    assert "origin_ungrounded" not in rows[0]
    assert "carried_from_ungrounded" not in rows[0]


def test_gaps_can_be_narrowed_to_one_suspect(client, case):
    """`suspect` names a party in the public case file, not a memory store."""
    everyone = client.get(f"/cases/{case}/gaps").json()["gaps"]
    if not everyone:
        pytest.skip("this world produced no gaps")
    who = everyone[0]["speaker"]

    narrowed = client.get(f"/cases/{case}/gaps", params={"suspect": who}).json()["gaps"]

    assert narrowed
    assert {g["speaker"] for g in narrowed} == {who}


# -- the seam ----------------------------------------------------------------


def test_no_route_path_names_a_mind_a_world_or_a_truth(client):
    """Read from the app's own schema, so a later route cannot slip past it."""
    paths = client.get("/openapi.json").json()["paths"]

    for path in paths:
        lowered = path.lower()
        for forbidden in ("mind", "world", "truth", "ground", "referee", "culprit"):
            assert forbidden not in lowered, path


def test_every_case_route_is_covered_by_the_seam_walk(client):
    """The walk below is only worth anything if it reads every route."""
    paths = client.get("/openapi.json").json()["paths"]
    readable = {
        p.replace("/cases/{seed}", "").replace("/cases", "")
        for p, ops in paths.items()
        if "get" in ops and p.startswith("/cases")
    }

    assert readable - {"/events"} == set(READ_ROUTES)


def test_no_response_body_carries_a_ground_truth_label(client, case, scripted_detective):
    """Spec 8.1's labels are scoring vocabulary and never leave the referee.

    Walked after a full investigation, so the traces, the accusation and the
    event log are all populated when the check runs.
    """
    scripted_detective(case)
    client.post(f"/cases/{case}/investigate", json={})
    _finish(case)

    for route in READ_ROUTES:
        body = client.get(f"/cases/{case}{route}").text
        for label in ALL_LABELS:
            assert label not in body, f"{route} leaked {label}"

    stream = client.get(f"/cases/{case}/events", params={"follow": False}).text
    for label in ALL_LABELS:
        assert label not in stream, f"the event stream leaked {label}"


def test_no_response_body_describes_intent(client, case, scripted_detective):
    """Rule 2: a verdict describes grounding. The words are checked, not trusted."""
    scripted_detective(case)
    client.post(f"/cases/{case}/investigate", json={})
    _finish(case)

    bodies = [client.get(f"/cases/{case}{route}").text for route in READ_ROUTES]
    bodies.append(client.get(f"/cases/{case}/events", params={"follow": False}).text)

    for body in bodies:
        words = set(body.lower().replace('"', " ").replace(",", " ").split())
        assert not (words & set(INTENT_WORDS)), sorted(words & set(INTENT_WORDS))


def test_no_response_body_names_a_mind_graph(client, case):
    for route in READ_ROUTES:
        body = client.get(f"/cases/{case}{route}").text
        assert "mind:" not in body
        assert "world:" not in body


# -- the investigation and the stream ----------------------------------------


def test_investigating_a_case_runs_the_loop_and_records_an_accusation(
    client, case, scripted_detective
):
    completer = scripted_detective(case)

    accepted = client.post(f"/cases/{case}/investigate", json={})
    assert accepted.status_code == 202

    summary = _finish(case)
    assert summary["status"] == "closed"
    assert summary["accusation"]["accusation"]["suspect"]
    assert summary["accusation"]["stopped"] == "accused"
    assert summary["polygraphs_left"] == 1
    assert summary["traces"] >= 0
    assert completer.calls == summary["accusation"]["turns"]


def test_a_closed_case_will_not_be_investigated_twice(client, case, scripted_detective):
    scripted_detective(case)
    client.post(f"/cases/{case}/investigate", json={})
    _finish(case)

    again = client.post(f"/cases/{case}/investigate", json={})

    assert again.status_code == 409
    assert "already accused" in again.json()["detail"]


def test_the_stream_replays_the_case_from_the_beginning(client, case, scripted_detective):
    """A board that connects late still sees the whole case.

    This is why the bus buffers rather than broadcasts: the generation events
    happened before any browser existed.
    """
    scripted_detective(case)
    client.post(f"/cases/{case}/investigate", json={})
    _finish(case)

    events = _parse_sse(client.get(f"/cases/{case}/events", params={"follow": False}).text)

    assert [e["seq"] for e in events] == list(range(len(events)))
    assert events[0]["type"] == "case.generating"
    types = [e["type"] for e in events]
    assert "case.ready" in types
    assert "investigation.started" in types
    assert "tool.called" in types
    assert "accusation" in types
    assert types[-1] == "investigation.finished"


def test_the_stream_resumes_from_a_cursor(client, case, scripted_detective):
    scripted_detective(case)
    client.post(f"/cases/{case}/investigate", json={})
    _finish(case)

    whole = _parse_sse(client.get(f"/cases/{case}/events", params={"follow": False}).text)
    tail = _parse_sse(
        client.get(
            f"/cases/{case}/events", params={"follow": False, "cursor": len(whole) - 2}
        ).text
    )

    assert tail == whole[-2:]


def test_a_following_stream_ends_when_the_case_does(client, case, scripted_detective):
    """An SSE response that can never end is a leaked connection."""
    scripted_detective(case)
    client.post(f"/cases/{case}/investigate", json={})

    with client.stream(
        "GET", f"/cases/{case}/events", params={"follow": True, "timeout": 20}
    ) as response:
        body = "".join(chunk for chunk in response.iter_text())

    events = _parse_sse(body)
    assert [e["type"] for e in events][-2:] == ["investigation.finished", "stream.closed"]


def test_an_idle_stream_closes_on_its_timeout(client, case):
    """No investigation was started, so nothing will ever arrive."""
    with client.stream(
        "GET", f"/cases/{case}/events", params={"follow": True, "timeout": 0.2}
    ) as response:
        body = "".join(chunk for chunk in response.iter_text())

    assert _parse_sse(body)[-1]["type"] == "stream.timeout"


def test_a_replay_only_investigation_with_an_empty_cache_fails_loudly(client, case):
    """Rule 8: the run reports the miss; it does not quietly produce no case."""
    runner.registry._cache = LLMCache()

    client.post(f"/cases/{case}/investigate", json={"replay_only": True})
    summary = _finish(case)

    assert summary["status"] == "failed"
    assert "CacheMiss" in summary["error"]
    events = _parse_sse(client.get(f"/cases/{case}/events", params={"follow": False}).text)
    assert events[-1]["type"] == "investigation.failed"


def _parse_sse(body: str) -> list[dict]:
    """The `data:` payloads of an SSE body, in order."""
    return [
        json.loads(line[len("data: ") :])
        for line in body.splitlines()
        if line.startswith("data: ")
    ]
