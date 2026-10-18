"""The replay cache and the per-case cap (project rules, rule 9; spec 3 and 7).

Three properties carry this file, and all three are about money and
determinism rather than about correctness of any answer:

1. **The key is `(seed, agent, prompt_hash)`.** Three parts, as spec 7 writes
   it. Dropping any one of them would serve one case's answer to another, or
   one agent's answer to a different agent, and the benchmark would quietly
   stop comparing like with like.
2. **A recorded case replays at zero API calls.** Asserted with a transport
   that raises if it is reached, so the claim cannot be true-by-counter.
3. **The cap counts attempts, not misses.** A replayed run therefore takes
   exactly as many turns as the live run it replays. If the cap counted only
   misses, a cached run could outlive its recording and the word
   "bit-identical" would be wrong.

Nothing here knows what a claim or a verdict is. That is the point: the cache
moves opaque documents and never classifies one (rule 1).
"""

from __future__ import annotations

import pytest

from backend.app.agents.llm_cache import (
    CachedLLM,
    CacheMiss,
    CallCapExceeded,
    LLMCache,
    prompt_hash,
)

REQUEST = {"model": "m", "max_tokens": 16, "messages": [{"role": "user", "content": "hi"}]}


def _answer(text: str, *, in_tokens: int = 7, out_tokens: int = 3) -> dict:
    return {
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": text}],
        "usage": {"input_tokens": in_tokens, "output_tokens": out_tokens},
    }


class Counting:
    """A transport that counts and answers differently every time.

    Answering differently each call is what makes replay observable: if the
    second run returns the first answer, it came from the table.
    """

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, request: dict) -> dict:
        self.calls += 1
        return _answer(f"answer {self.calls}")


# -- the hash ----------------------------------------------------------------


def test_prompt_hash_ignores_key_order_but_nothing_else():
    """Dict ordering is not information; every value in the request is."""
    a = {"model": "m", "max_tokens": 1, "messages": []}
    b = {"messages": [], "max_tokens": 1, "model": "m"}
    assert prompt_hash(a) == prompt_hash(b)

    for changed in (
        {**a, "model": "other"},
        {**a, "max_tokens": 2},
        {**a, "messages": [{"role": "user", "content": "x"}]},
        {**a, "tools": []},
    ):
        assert prompt_hash(changed) != prompt_hash(a), changed


def test_prompt_hash_is_stable_across_processes():
    """A literal, so a cache written today is readable tomorrow.

    Pinned rather than recomputed: a change to the canonical form would
    silently invalidate every recorded case, and a test that recomputed the
    hash both sides would not notice.
    """
    assert prompt_hash({"model": "m"}) == (
        "548f58d1c36c715b44f0863472074a97c448d5b8d18164b92adf55592b127f86"
    )


# -- the three-part key ------------------------------------------------------


def test_the_cache_key_has_three_parts():
    """Same prompt, different seed or different agent, is a different question."""
    cache = LLMCache()
    cache.put(
        seed=1, agent="detective", prompt_hash="h", model="m", request={}, response=_answer("a")
    )

    assert cache.get(seed=1, agent="detective", prompt_hash="h") == _answer("a")
    assert cache.get(seed=2, agent="detective", prompt_hash="h") is None
    assert cache.get(seed=1, agent="p3", prompt_hash="h") is None
    assert cache.get(seed=1, agent="detective", prompt_hash="other") is None


def test_one_seeds_recording_is_not_served_to_another_case():
    """The isolation the key buys, through the wrapper rather than the store."""
    cache = LLMCache()
    transport = Counting()

    CachedLLM(cache, seed=100, completer=transport).complete(REQUEST, agent="detective")
    second = CachedLLM(cache, seed=200, completer=transport).complete(
        REQUEST, agent="detective"
    )

    assert transport.calls == 2
    assert second["content"][0]["text"] == "answer 2"


# -- replay ------------------------------------------------------------------


def test_a_recorded_prompt_replays_without_reaching_the_transport():
    cache = LLMCache()
    transport = Counting()
    live = CachedLLM(cache, seed=7, completer=transport)
    first = live.complete(REQUEST, agent="detective")

    replay = CachedLLM(cache, seed=7, completer=transport)
    again = replay.complete(REQUEST, agent="detective")

    assert again == first
    assert transport.calls == 1
    assert replay.ledger.api_calls == 0
    assert replay.ledger.hits == 1
    assert replay.ledger.calls == 1


def test_replay_only_refuses_a_miss_instead_of_spending(tmp_path):
    """A replay-only run that silently started calling out would stop being one."""
    cache = LLMCache(tmp_path / "cache.sqlite3")
    transport = Counting()
    llm = CachedLLM(cache, seed=7, completer=transport, replay_only=True)

    with pytest.raises(CacheMiss) as exc:
        llm.complete(REQUEST, agent="detective")

    assert transport.calls == 0
    assert "replay-only" in str(exc.value)


def test_a_cache_survives_being_reopened(tmp_path):
    """The whole point of SQLite over a dict: the recording outlives the process."""
    path = tmp_path / "cache.sqlite3"
    transport = Counting()
    CachedLLM(LLMCache(path), seed=7, completer=transport).complete(REQUEST, agent="detective")

    reopened = CachedLLM(LLMCache(path), seed=7, replay_only=True)
    answer = reopened.complete(REQUEST, agent="detective")

    assert answer["content"][0]["text"] == "answer 1"
    assert reopened.ledger.api_calls == 0


def test_forgetting_a_seed_leaves_other_seeds_recorded():
    cache = LLMCache()
    for seed in (1, 2):
        cache.put(
            seed=seed, agent="d", prompt_hash="h", model="m", request={}, response=_answer("a")
        )

    cache.forget(1)

    assert cache.count(1) == 0
    assert cache.count(2) == 1


# -- the cap -----------------------------------------------------------------


def test_the_cap_is_exact_and_the_call_past_it_is_refused():
    """The boundary, both sides. The cap-th call is allowed; the next is not."""
    llm = CachedLLM(LLMCache(), seed=7, completer=Counting(), cap=3)

    for n in range(3):
        llm.complete({**REQUEST, "nonce": n}, agent="detective")

    assert llm.calls_left == 0
    with pytest.raises(CallCapExceeded) as exc:
        llm.complete({**REQUEST, "nonce": 99}, agent="detective")
    assert "cap of 3" in str(exc.value)


def test_a_cache_hit_still_spends_a_call():
    """Otherwise a replayed run could take more turns than its recording.

    This is the property that makes "replays bit-identically" true of the
    whole loop and not only of each individual answer.
    """
    cache = LLMCache()
    transport = Counting()
    recorded = CachedLLM(cache, seed=7, completer=transport, cap=2)
    recorded.complete({**REQUEST, "nonce": 0}, agent="detective")
    recorded.complete({**REQUEST, "nonce": 1}, agent="detective")

    replay = CachedLLM(cache, seed=7, replay_only=True, cap=2)
    replay.complete({**REQUEST, "nonce": 0}, agent="detective")
    replay.complete({**REQUEST, "nonce": 1}, agent="detective")

    assert replay.ledger.hits == 2
    assert replay.ledger.api_calls == 0
    with pytest.raises(CallCapExceeded):
        replay.complete({**REQUEST, "nonce": 0}, agent="detective")


def test_a_missing_completer_is_a_miss_not_a_silent_empty_answer():
    """Rule 8, in the transport: nothing here invents a turn."""
    llm = CachedLLM(LLMCache(), seed=7)
    with pytest.raises(CacheMiss):
        llm.complete(REQUEST, agent="detective")


# -- the ledger --------------------------------------------------------------


def test_the_ledger_separates_turns_taken_from_calls_that_reached_the_api():
    """Spec 8.3's cost column. `api_calls` is the figure worth reporting."""
    cache = LLMCache()
    transport = Counting()
    llm = CachedLLM(cache, seed=7, completer=transport)

    llm.complete({**REQUEST, "nonce": 0}, agent="detective")
    llm.complete({**REQUEST, "nonce": 0}, agent="detective")
    llm.complete({**REQUEST, "nonce": 1}, agent="detective")

    assert llm.ledger.as_dict() == {
        "calls": 3,
        "hits": 1,
        "api_calls": 2,
        "input_tokens": 21,
        "output_tokens": 9,
        "per_agent": {"detective": 3},
    }
