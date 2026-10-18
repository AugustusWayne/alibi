"""Scripted suspects: deterministic testimony, with a configurable policy.

This is a real component, not a test double. It makes the whole audit engine
exercisable with zero LLM calls, zero cost and zero flakiness, and it stays in
the repo as `--scripted` mode for CI and as insurance against the LLM path.

**What a scripted suspect can and cannot do.** It answers from `recall` over
its own mind — and only its own mind, because `MindAccess` is bound at
construction and `recall` takes no agent parameter (project rules, rule 6).
What it is *permitted to say beyond its memory* is the `FabricationPolicy`: a
small set of explicit knobs, each of which corresponds to something a real
testimony might do.

**The policy describes testimony behaviour, not character.** A suspect running
`evasive` is not thereby concealing wrongdoing; it declines to account for a
window. The audit reports the resulting claim as INDETERMINATE or UNSUPPORTED,
which says only that its memory did not account for that span.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from backend.app.audit.time_contract import overlaps
from backend.app.audit.verdicts import HEARSAY_SRC, THROUGHOUT, WITNESSED
from backend.app.case.graph import CaseGraph
from backend.app.minds.access import Fact, MindAccess


@dataclass(frozen=True)
class Claim:
    """A structured claim. No NLU is needed to audit this.

    Matches the `testify` tool's shape from spec 7: the suspect states who,
    where, when and how strongly, and optionally who told it so.
    """

    subject: str
    place: str
    t0: int
    t1: int
    modality: str = THROUGHOUT
    relayed_from: str | None = None


@dataclass(frozen=True)
class FabricationPolicy:
    """What a suspect is permitted to assert that its own memory does not hold.

    Every field is an explicit permission. The default is a suspect that says
    only what it witnessed, which is the honest case.

    - `speak_witnessed`: testify from witnessed memory.
    - `speak_hearsay`: testify from secondhand memory, naming the source. This
      is how the innocent repeater arises — not misreporting, just a
      memory of having been told something.
    - `speak_planted`: assert the specific fabrications the world generator
      recorded for this agent. Only the generator decides what those are; this
      flag only decides whether the agent voices them.
    - `withhold_window`: decline to account for a span, leaving a gap rather
      than a conflict.
    - `merge_adjacent`: round two adjacent memories of the same room into one
      continuous claim. A real witness does this constantly; it produces
      claims slightly wider than the memory behind them, which is exactly the
      partial-support case worth testing.
    - `modality`: the strength every claim is asserted with.
    - `max_claims`: cap on an unprompted full-evening account, so one
      talkative suspect cannot dominate the scoreboard by sheer volume. It
      samples the evening evenly rather than taking the earliest N — see
      `_cap`. A windowed interview is never capped.
    """

    speak_witnessed: bool = True
    speak_hearsay: bool = False
    speak_planted: bool = False
    withhold_window: tuple[int, int] | None = None
    merge_adjacent: bool = False
    modality: str = THROUGHOUT
    max_claims: int = 20


HONEST = FabricationPolicy(speak_witnessed=True, speak_hearsay=True)
"""Says what it saw and what it was told, and names who told it."""

RETICENT = FabricationPolicy(speak_witnessed=True, speak_hearsay=False)
"""Says only what it saw firsthand. Secondhand knowledge goes unmentioned."""

CULPRIT = FabricationPolicy(
    speak_witnessed=True, speak_hearsay=False, speak_planted=True, merge_adjacent=True
)
"""Voices the generator's planted alibi alongside its real memories."""

ACCOMPLICE = FabricationPolicy(
    speak_witnessed=True, speak_hearsay=True, speak_planted=True
)
"""Corroborates the planted alibi as though it had been told it."""


def evasive(window: tuple[int, int]) -> FabricationPolicy:
    """A suspect who will not account for one window."""
    return FabricationPolicy(speak_witnessed=True, speak_hearsay=True, withhold_window=window)


POLICY_BY_ROLE = {
    "honest": HONEST,
    "culprit": CULPRIT,
    "accomplice": ACCOMPLICE,
}
"""Default policy per generated role. A caller may override any of them."""


class ScriptedSuspect:
    """A suspect that testifies deterministically from its own memory."""

    def __init__(
        self,
        mind: MindAccess,
        *,
        policy: FabricationPolicy = HONEST,
        planted: tuple = (),
    ) -> None:
        self._mind = mind
        self._policy = policy
        # What the generator recorded this agent as permitted to assert. The
        # agent cannot add to this list; it can only decline to voice it.
        self._planted = tuple(planted)

    @property
    def id(self) -> str:
        return self._mind.agent

    @property
    def policy(self) -> FabricationPolicy:
        return self._policy

    def with_policy(self, policy: FabricationPolicy) -> ScriptedSuspect:
        """A copy under a different policy, for comparing testimony behaviours."""
        return ScriptedSuspect(self._mind, policy=policy, planted=self._planted)

    def recall(
        self,
        *,
        subject: str | None = None,
        place: str | None = None,
        t_range: tuple[int, int] | None = None,
    ) -> list[Fact]:
        """The agent's own `recall` tool. Its own mind, and no way to say otherwise."""
        return self._mind.recall(subject=subject, place=place, t_range=t_range)

    def testify(
        self,
        *,
        about: str | None = None,
        window: tuple[int, int] | None = None,
        limit: int | bool | None = -1,
    ) -> list[Claim]:
        """Everything this suspect will say, as structured claims.

        `about` narrows to one subject and `window` to one time range — which
        is what an interview actually is: a question about a person and a
        span, answered from memory.

        `limit` defaults to the policy's `max_claims`; pass `None` for an
        uncapped account. A `window` is never capped, because a question about
        a specific span deserves every claim bearing on it.

        Deterministic: the same mind, policy and question produce the same
        claims in the same order, every time.
        """
        p = self._policy
        facts = self.recall(subject=about, t_range=window)
        claims: list[Claim] = []

        if p.speak_witnessed:
            claims.extend(self._from_memory([f for f in facts if f.src == WITNESSED],
                                            relayed=False))
        if p.speak_hearsay:
            claims.extend(self._from_memory([f for f in facts if f.src == HEARSAY_SRC],
                                            relayed=True))
        if p.speak_planted:
            claims.extend(
                Claim(
                    subject=fab.by_person,
                    place=fab.place,
                    t0=fab.t0,
                    t1=fab.t1,
                    modality=p.modality,
                )
                for fab in self._planted
                if (about is None or fab.by_person == about)
                and (window is None or overlaps(fab.t0, fab.t1, *window))
            )

        if p.withhold_window is not None:
            w0, w1 = p.withhold_window
            claims = [c for c in claims if not overlaps(c.t0, c.t1, w0, w1)]
        if window is not None:
            claims = [c for c in claims if overlaps(c.t0, c.t1, *window)]

        # Sorted so turn order is a property of the testimony, not of dict
        # iteration. De-duplicated because two memories of the same subject in
        # the same room over the same span are one statement.
        claims = sorted(
            set(claims),
            key=lambda c: (c.t0, c.t1, c.subject, c.place, c.relayed_from or ""),
        )
        if window is not None or limit is None:
            return claims
        return _cap(claims, p.max_claims if limit == -1 else int(limit))

    def _from_memory(self, facts: list[Fact], *, relayed: bool) -> list[Claim]:
        """Turn memories into claims, optionally merging adjacent same-room ones.

        Merging is the one place a scripted suspect says something wider than
        any single memory it holds. That is deliberate and it is honest
        behaviour: a witness who was in the kitchen 21:00-21:05 and again
        21:07-21:15 will say "I was in the kitchen the whole time". The audit
        then finds partial support and a two-minute gap, which is the
        INDETERMINATE case arising naturally rather than being injected.
        """
        p = self._policy
        ordered = sorted(facts, key=lambda f: (f.subject, f.place, f.t0, f.t1, f.id))
        claims: list[Claim] = []
        for fact in ordered:
            source = fact.heard_from if relayed else None
            if (
                p.merge_adjacent
                and claims
                and claims[-1].subject == fact.subject
                and claims[-1].place == fact.place
                and claims[-1].relayed_from == source
                and fact.t0 - claims[-1].t1 <= 3
            ):
                claims[-1] = replace(claims[-1], t1=max(claims[-1].t1, fact.t1))
                continue
            claims.append(
                Claim(
                    subject=fact.subject,
                    place=fact.place,
                    t0=fact.t0,
                    t1=fact.t1,
                    modality=p.modality,
                    relayed_from=source,
                )
            )
        return claims


def _cap(claims: list[Claim], limit: int) -> list[Claim]:
    """Keep at most `limit` claims, sampled evenly across the account.

    Taking the earliest `limit` claims would drop the back half of everyone's
    evening — a biased sample, not a cap, and one that would make late-evening
    claims unauditable no matter what they said. Evenly spaced indices keep
    the whole evening represented, including the last statement, and are
    deterministic for a given input.
    """
    if limit <= 0 or len(claims) <= limit:
        return claims
    if limit == 1:
        return [claims[0]]
    step = (len(claims) - 1) / (limit - 1)
    picked = sorted({round(i * step) for i in range(limit)})
    return [claims[i] for i in picked]


def build_suspects(
    db: Any,
    seed: int,
    *,
    plan: Any,
    policies: dict[str, FabricationPolicy] | None = None,
) -> list[ScriptedSuspect]:
    """One scripted suspect per person in the world, policy chosen by role.

    `policies` overrides by agent id, which is how a test or the eval harness
    compares the same world under different testimony behaviours.
    """
    overrides = policies or {}
    suspects = []
    for person in plan.people:
        policy = overrides.get(person.id, POLICY_BY_ROLE.get(person.role, HONEST))
        planted = tuple(f for f in plan.fabrications if f.by_person == person.id)
        suspects.append(
            ScriptedSuspect(
                MindAccess(db, seed, person.id), policy=policy, planted=planted
            )
        )
    return suspects


def interview_all(
    db: Any,
    seed: int,
    *,
    plan: Any,
    policies: dict[str, FabricationPolicy] | None = None,
) -> list[dict]:
    """Interview every suspect and ingest what they say into the case graph.

    Returns the ingested claims as dicts. Claim ids are `{speaker}-c{n}` and
    turns are assigned in suspect order, so a case built twice from one seed
    has identical claim ids — which is what makes the audit's output
    comparable between runs.
    """
    case = CaseGraph(db, seed)
    ingested: list[dict] = []
    turn = 0
    for suspect in build_suspects(db, seed, plan=plan, policies=policies):
        for n, claim in enumerate(suspect.testify(), start=1):
            turn += 1
            claim_id = f"{suspect.id}-c{n}"
            case.ingest_claim(
                claim_id=claim_id,
                speaker=suspect.id,
                subject=claim.subject,
                place=claim.place,
                t0=claim.t0,
                t1=claim.t1,
                turn=turn,
                modality=claim.modality,
                relayed_from=claim.relayed_from,
            )
            ingested.append(
                {
                    "id": claim_id,
                    "speaker": suspect.id,
                    "subject": claim.subject,
                    "place": claim.place,
                    "t0": claim.t0,
                    "t1": claim.t1,
                    "turn": turn,
                    "modality": claim.modality,
                    "relayed_from": claim.relayed_from,
                }
            )
    return ingested
