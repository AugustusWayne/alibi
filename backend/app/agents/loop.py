"""The detective's decision loop: a model choosing what to ask, nothing more.

**What the model does here, exactly.** It picks the next tool call. That is the
whole of its authority. It never classifies a claim, never computes coverage,
never decides a contradiction and never names a chain's origin — those are
Cypher and the decision table, reached only through `DetectiveTools`, and the
loop copies their answers into the transcript verbatim (project rules, rule 1).
If every model in this file were replaced by a random choice of tool, every
verdict in the case graph would be identical; only which questions got asked
would change. That is the property this file has to preserve.

**Why a loop and not one prompt.** Spec 7 rations `polygraph` to two per case.
A rationing that the detective cannot see the consequences of is not a choice,
so the detective has to go round again: read the gaps, ask about one, see what
the audit made of the answer, and only then decide which claim is worth one of
its two looks. `list_gaps` is the sleeper tool precisely because it is read
between turns.

**Every call goes through `CachedLLM`** (rule 9), which holds both the replay
cache and the hard per-case cap. There is no other path to a model from here,
and the loop takes the cap as its own turn limit by default.

**Vocabulary is enforced, not requested.** A verdict describes grounding, not
intent (rule 2), and an accusation's rationale is the one string in this system
written by a model and shown to a person. The system prompt says so, and
`_rejects_intent_language` checks it deterministically before `accuse` runs: a
rationale that describes intent is refused back to the model, naming the word
it used, at the cost of a turn. The check is the guarantee; the prompt is only
a way to avoid spending turns on it. The words themselves are frozen in
`intent_vocabulary.json` beside this module, for the reasons written in it.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.app.agents.detective import (
    Accusation,
    BudgetExhausted,
    DetectiveTools,
    Question,
)
from backend.app.agents.llm_cache import CachedLLM, CallCapExceeded

DETECTIVE_AGENT = "detective"
"""The `agent` half of the cache key for every call this loop makes."""

INTENT_VOCABULARY_PATH = Path(__file__).resolve().parent / "intent_vocabulary.json"


def load_intent_words(path: Path | None = None) -> tuple[str, ...]:
    """The frozen list of words a rationale may not use (rule 2).

    Raises on an empty or missing list rather than defaulting to no words. A
    guard that silently stopped guarding would be worse than none, because
    everything downstream would still be built as though it were running.
    """
    data = json.loads((path or INTENT_VOCABULARY_PATH).read_text())
    words = tuple(data.get("intent_words") or ())
    if not words:
        raise ValueError(
            f"{path or INTENT_VOCABULARY_PATH} lists no intent words; the "
            f"accusation guard has nothing to check against"
        )
    return words


INTENT_WORDS = load_intent_words()
"""Loaded once at import. See the note in the JSON file for what is on it and
why it lives there rather than here."""

_INTENT_RE = re.compile(r"\b(" + "|".join(INTENT_WORDS) + r")\b", re.IGNORECASE)

SYSTEM_PROMPT = """You are the detective on a case. You investigate only by \
calling the tools below; you never state a finding the tools did not give you.

What the tools report is GROUNDING, not intent. A verdict says what a speaker's \
own memory accounts for:

- SUPPORTED: the speaker's own witnessed memory accounts for the claim.
- UNSUPPORTED: nothing bearing on it was found in the speaker's memory. Nothing \
was found. That is all it means. A witness can be unsupported because they \
blinked.
- CONTRADICTED: the speaker's own witnessed memory places the subject elsewhere \
at an overlapping time.
- INDETERMINATE: support is partial; the uncovered spans are recorded as gaps.
- HEARSAY: the only support is secondhand, so the grounding depends on another \
mind.

None of the five means a claim is false and none is a judgement about a person. \
You must never write that anyone lied, deceived, fabricated or was dishonest. An \
accusation whose rationale uses that vocabulary is rejected and you will be \
asked to restate it. Say what is unaccounted for, what is contradicted by the \
speaker's own memory, and where a chain of secondhand accounts ended.

You have a budget of exactly two polygraphs for the whole case. A polygraph is \
the only way to see where a claim's provenance ends, and spending one on a \
claim whose grounding you could have read from list_contradictions, list_gaps \
or rank_suspects is a wasted look. Read the board first: rank_suspects orders \
suspects by how much of what they said their own memory does not account for, \
and list_gaps hands you the exact unaccounted-for spans to interview about.

Work in this spirit: look at the whole board, interview into the gaps, and only \
then spend a polygraph. Gather all the evidence before you decide. Call exactly \
one tool per turn. Close the case with accuse when the evidence supports naming \
someone; accuse is the only way the case ends."""

TOOL_SCHEMAS: tuple[dict, ...] = (
    {
        "name": "interview",
        "description": (
            "Ask one suspect to account for a person over a span. Returns the "
            "claims they made, each already audited, with `new` saying whether "
            "this interview added it. Omit `about` for a full account; give "
            "`t0` and `t1` to ask about one window, which is what list_gaps "
            "hands you. Asking again for testimony already on record does not "
            "add it twice."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "suspect": {"type": "string", "description": "Suspect id, e.g. p3."},
                "about": {
                    "type": ["string", "null"],
                    "description": "Person id to ask about, or null for a full account.",
                },
                "t0": {
                    "type": ["integer", "null"],
                    "description": "Window start, inclusive. Null for no window.",
                },
                "t1": {
                    "type": ["integer", "null"],
                    "description": "Window end, exclusive. Null for no window.",
                },
            },
            "required": ["suspect", "about", "t0", "t1"],
        },
    },
    {
        "name": "list_contradictions",
        "description": (
            "Re-run the exclusive-presence and impossible-travel checks over "
            "everything said so far and return every contradiction found. "
            "Worth repeating after an interview, which can add the claim that "
            "contradicts an earlier one."
        ),
        "strict": True,
        "input_schema": {"type": "object", "additionalProperties": False, "properties": {}},
    },
    {
        "name": "list_gaps",
        "description": (
            "The spans a suspect's own memory did not account for, as the audit "
            "recorded them. Omit `suspect` for every gap in the case. A gap is "
            "not an allegation: it is a span that was examined and nothing was "
            "found for."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "suspect": {
                    "type": ["string", "null"],
                    "description": "Suspect id, or null for the whole case.",
                }
            },
            "required": ["suspect"],
        },
    },
    {
        "name": "check_travel",
        "description": (
            "Minutes of travel between two rooms and the route taken, from the "
            "same precomputed matrix the impossible-travel check uses."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "place_a": {"type": "string"},
                "place_b": {"type": "string"},
            },
            "required": ["place_a", "place_b"],
        },
    },
    {
        "name": "rank_suspects",
        "description": (
            "Order the suspects by how much of what they said their own memory "
            "does not account for, with the full breakdown of every term. A "
            "reading order, not an accusation."
        ),
        "strict": True,
        "input_schema": {"type": "object", "additionalProperties": False, "properties": {}},
    },
    {
        "name": "polygraph",
        "description": (
            "Examine one claim against its speaker's own memory. BUDGET: 2 FOR "
            "THE WHOLE CASE. Returns the verdict, redacted evidence shadows, "
            "the unaccounted-for spans and where the provenance chain ended — "
            "never the memory itself. The speaker must be the suspect who made "
            "the claim. Looking again at a claim already polygraphed is free."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "suspect": {"type": "string"},
                "claim_id": {"type": "string"},
            },
            "required": ["suspect", "claim_id"],
        },
    },
    {
        "name": "accuse",
        "description": (
            "Name a suspect and close the case. The rationale must describe "
            "grounding — what is unaccounted for, what the speaker's own memory "
            "contradicts, where a chain of secondhand accounts ended — and must "
            "not describe intent. It is recorded, not graded."
        ),
        "strict": True,
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "suspect": {"type": "string"},
                "rationale": {"type": "string"},
            },
            "required": ["suspect", "rationale"],
        },
    },
)
"""The seven tools of spec 7, in the order spec 7 lists them, as the model sees
them. One entry per `DetectiveTools.TOOLS` member and no others; a test holds
the two lists against each other so a tool cannot be added to one alone."""


@dataclass(frozen=True)
class Event:
    """One thing that happened, as the board sees it.

    Public information only: a tool's name, its arguments and what the case
    graph answered. Nothing from a mind, and no ground-truth label — the same
    seam the API holds (rule 6, rule 2).
    """

    seq: int
    type: str
    at: str
    data: dict

    def as_dict(self) -> dict:
        return {"seq": self.seq, "type": self.type, "at": self.at, "data": self.data}


@dataclass(frozen=True)
class Investigation:
    """What one run of the loop came to, and what it cost."""

    seed: int
    accusation: Accusation | None
    turns: int
    stopped: str
    tool_calls: dict[str, int] = field(default_factory=dict)
    polygraphs_spent: int = 0
    ledger: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "seed": self.seed,
            "accusation": None if self.accusation is None else asdict(self.accusation),
            "turns": self.turns,
            "stopped": self.stopped,
            "tool_calls": dict(self.tool_calls),
            "polygraphs_spent": self.polygraphs_spent,
            "ledger": dict(self.ledger),
        }


class LoopError(RuntimeError):
    """The loop cannot continue and will not guess its way past it."""


def _rejects_intent_language(text: str) -> str | None:
    """The word that makes a rationale unpublishable, or None.

    Deterministic and case-insensitive, matched on word boundaries so a word
    that merely contains one of them — `believe`, `relief` — is not caught.
    """
    found = _INTENT_RE.search(text)
    return None if found is None else found.group(1).lower()


def _render(value: Any) -> str:
    """A tool's real return value, as the model reads it.

    Verbatim and complete. Nothing is summarized, ranked or filtered on the way
    through — the point of this system is that what the graph proved is what
    gets acted on, and a loop that paraphrased its own evidence would be the
    first place that stopped being true.
    """
    if is_dataclass(value) and not isinstance(value, type):
        value = asdict(value)
    return json.dumps(value, default=str, sort_keys=False)


class DetectiveLoop:
    """One investigation: a model, the seven tools, and a bounded number of turns."""

    def __init__(
        self,
        tools: DetectiveTools,
        llm: CachedLLM,
        *,
        model: str,
        briefing: str,
        max_turns: int | None = None,
        max_tokens: int = 4096,
        effort: str = "high",
        on_event: Callable[[Event], None] | None = None,
    ) -> None:
        self._tools = tools
        self._llm = llm
        self._model = model
        self._briefing = briefing
        self._max_turns = max_turns if max_turns is not None else llm.cap
        self._max_tokens = max_tokens
        self._effort = effort
        self._on_event = on_event
        # Captured rather than read from the tools at the end: `DetectiveTools`
        # publishes what is left, not what the budget was, and the loop has no
        # business reaching past that for a private field.
        self._polygraph_budget = tools.polygraphs_left
        self._seq = 0
        self.events: list[Event] = []

    # -- events -------------------------------------------------------------

    def emit(self, type_: str, **data: Any) -> Event:
        event = Event(
            seq=self._seq,
            type=type_,
            at=datetime.now(UTC).isoformat(timespec="milliseconds"),
            data=data,
        )
        self._seq += 1
        self.events.append(event)
        if self._on_event is not None:
            self._on_event(event)
        return event

    # -- the loop -----------------------------------------------------------

    def run(self) -> Investigation:
        """Turn after turn until the case is closed, the cap is spent, or the
        turn limit is reached. Returns what happened either way."""
        messages: list[dict] = [{"role": "user", "content": self._briefing}]
        self.emit(
            "investigation.started",
            seed=self._llm.seed,
            model=self._model,
            max_turns=self._max_turns,
            cap=self._llm.cap,
            polygraph_budget=self._tools.polygraphs_left,
        )

        stopped = "max_turns"
        turns = 0
        while turns < self._max_turns:
            request = self._request(messages)
            try:
                response = self._llm.complete(request, agent=DETECTIVE_AGENT)
            except CallCapExceeded:
                stopped = "cap"
                break
            turns += 1

            if response.get("stop_reason") == "refusal":
                # Loud, not swallowed. A refused turn means the case cannot be
                # investigated as posed and nobody should see a half-run.
                raise LoopError(
                    f"the model declined the turn: {response.get('stop_details')}"
                )

            content = list(response.get("content") or [])
            messages.append({"role": "assistant", "content": content})
            self.emit(
                "turn.taken",
                turn=turns,
                stop_reason=response.get("stop_reason"),
                said=" ".join(
                    b.get("text", "") for b in content if b.get("type") == "text"
                ).strip(),
            )

            calls = [b for b in content if b.get("type") == "tool_use"]
            if not calls:
                # The model said something and stopped. Ask it to act; the cap
                # bounds how long this can go on.
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Call exactly one tool. The case ends only when you "
                            "call accuse."
                        ),
                    }
                )
                continue

            results = []
            for call in calls:
                results.append(self._dispatch(call))
            messages.append({"role": "user", "content": results})

            if self._tools.accusation is not None:
                stopped = "accused"
                break

        investigation = Investigation(
            seed=self._llm.seed,
            accusation=self._tools.accusation,
            turns=turns,
            stopped=stopped,
            tool_calls=self._tools.calls,
            polygraphs_spent=self._polygraph_budget - self._tools.polygraphs_left,
            ledger=self._llm.ledger.as_dict(),
        )
        self.emit("investigation.finished", **investigation.as_dict())
        return investigation

    def _request(self, messages: list[dict]) -> dict:
        """The request document, which is also the cache key's material.

        `tool_choice` is `auto` with the instruction to call one tool in the
        system prompt: the current models reject a forced `tool_choice`, and
        `strict` on every tool is what keeps the arguments schema-valid.
        """
        return {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "system": SYSTEM_PROMPT,
            "tools": list(TOOL_SCHEMAS),
            "tool_choice": {"type": "auto"},
            "output_config": {"effort": self._effort},
            "messages": messages,
        }

    # -- dispatch -----------------------------------------------------------

    def _dispatch(self, call: dict) -> dict:
        """Run one tool call and return the `tool_result` block for it.

        The errors caught here are the four the tool surface raises by design —
        an unknown suspect, a claim the suspect did not make, a spent budget, a
        room pair off the floor plan — and each is handed back as an error
        result so the detective can correct itself. Nothing else is caught: a
        query that breaks must raise and stop the run (rule 8).
        """
        name = call.get("name", "")
        args = call.get("input") or {}
        self.emit("tool.called", tool=name, args=args, call_id=call.get("id"))

        try:
            value = self._invoke(name, args)
        except (KeyError, ValueError, BudgetExhausted) as exc:
            message = f"{type(exc).__name__}: {exc}"
            self.emit("tool.refused", tool=name, args=args, error=message)
            return {
                "type": "tool_result",
                "tool_use_id": call.get("id"),
                "is_error": True,
                "content": message,
            }

        rendered = _render(value)
        self.emit("tool.result", tool=name, args=args, result=json.loads(rendered))
        if name == "accuse":
            self.emit("accusation", **asdict(value))
        return {
            "type": "tool_result",
            "tool_use_id": call.get("id"),
            "content": rendered,
        }

    def _invoke(self, name: str, args: dict) -> Any:
        """Map a tool name and its arguments onto the real tool.

        Explicit, one branch per tool, so no argument reaches `DetectiveTools`
        that the schema did not describe and no name resolves by `getattr`.
        """
        if name == "interview":
            t0, t1 = args.get("t0"), args.get("t1")
            if (t0 is None) != (t1 is None):
                raise ValueError(
                    "an interview window needs both t0 and t1, or neither; "
                    f"got t0={t0!r} t1={t1!r}"
                )
            window = None if t0 is None else (int(t0), int(t1))
            return self._tools.interview(
                args["suspect"], Question(about=args.get("about"), window=window)
            )
        if name == "list_contradictions":
            return self._tools.list_contradictions()
        if name == "list_gaps":
            return self._tools.list_gaps(args.get("suspect"))
        if name == "check_travel":
            return self._tools.check_travel(args["place_a"], args["place_b"])
        if name == "rank_suspects":
            return self._tools.rank_suspects()
        if name == "polygraph":
            return self._tools.polygraph(args["suspect"], args["claim_id"])
        if name == "accuse":
            rationale = str(args.get("rationale", ""))
            offending = _rejects_intent_language(rationale)
            if offending is not None:
                raise ValueError(
                    f"the rationale uses {offending!r}, which describes intent. A "
                    f"verdict describes grounding: say what is unaccounted for, "
                    f"what the speaker's own memory contradicts, or where a chain "
                    f"of secondhand accounts ended. Restate and call accuse again."
                )
            return self._tools.accuse(args["suspect"], rationale)
        raise ValueError(
            f"{name!r} is not one of the detective's tools; the case file offers "
            f"{list(DetectiveTools.TOOLS)}"
        )


def briefing(
    *,
    seed: int,
    suspects: list[dict],
    places: list[dict],
    incident: dict | None,
    claim_count: int,
    polygraph_budget: int,
) -> str:
    """The opening message: the public case file, and nothing else.

    Everything in it comes from the case graph, which holds public information
    only. No mind is read to write this, and no ground-truth label appears in
    it — the detective is told who and where, never what is true.
    """
    roster = ", ".join(f"{s['id']} ({s.get('name', s['id'])})" for s in suspects)
    rooms = ", ".join(f"{p['id']} ({p.get('name', p['id'])})" for p in places)
    when = (
        "The incident is not on the case file."
        if incident is None
        else (
            f"The incident is at {incident['place']} over "
            f"[{incident['t0']}, {incident['t1']})."
        )
    )
    return (
        f"Case {seed}.\n"
        f"Suspects: {roster}.\n"
        f"Rooms: {rooms}.\n"
        f"{when}\n"
        f"The case file already holds {claim_count} audited claims from the first "
        f"round of statements. You have {polygraph_budget} polygraphs.\n"
        f"Begin."
    )
