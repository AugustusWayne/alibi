"""The detective's typed tools (spec 7). The only surface a detective gets.

Seven tools over the **public case graph**: `interview`, `list_contradictions`,
`list_gaps`, `check_travel`, `rank_suspects`, `polygraph`, `accuse`. The graph
computes every check; the model only chooses what to ask.

**Why none of these breaks the isolation rule (project rules, rule 6).** Several
take a `suspect` argument, which is a party named in the public case file, not
a memory store. The seed is bound when this object is constructed, by the
orchestrator; the suspects are a roster bound the same way. No parameter here
names a graph, and none resolves to one — `polygraph` reads the claim's own
public `BY` edge to decide whose account is examined, and refuses a suspect
who did not make the claim, so there is no call in which the caller chooses a
mind. The referee held behind this surface is the thing that can cross graphs,
and nothing it reads crosses back: a `PolygraphReport` carries a verdict,
redacted evidence shadows, gaps and where a chain ended. Never a private fact,
never a ground-truth label.

**The polygraph budget is the point, not decoration.** Spec 7 rations it to
two per case. It is what makes the detective choose, and it is why the
referee's chain conclusions are materialized here rather than in advance: a
case graph pre-loaded with `TRACED_TO` edges would already tell the detective
where every secondhand account began, and the graph-versus-transcript arm of
the benchmark (spec 8.3) would be measuring who was handed the answer. So
`polygraph` is the only writer of `TRACED_TO` in the application — the
referee's own eval runs and the human operator's board materialize chains
explicitly, outside any detective's case.

**What these tools may not say.** A verdict describes grounding, not intent
(rule 2). `accuse` records which suspect the detective named and the reasoning
it gave; it computes nothing about whether that is correct. Scoring against
ground truth lives in `referee/` and never reaches this surface.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from backend.app.audit.engine import AuditEngine
from backend.app.audit.verdicts import PENDING
from backend.app.case.graph import CaseGraph
from backend.app.case.scoreboard import rank_suspects as rank_scoreboard
from backend.app.referee.provenance import Chain, Referee

POLYGRAPH_BUDGET = 2
"""Spec 7. Per case, not per suspect and not per interview."""


class BudgetExhausted(RuntimeError):
    """The polygraph budget is spent.

    Raised rather than answered with an empty report. An empty report would be
    indistinguishable from a claim with nothing behind it, which is the one
    confusion this system cannot afford (project rules, rule 8).
    """


@dataclass(frozen=True)
class Question:
    """What an interview asks: about whom, and over what span.

    Structured, like the testimony it elicits, so no NLU sits between the
    question and the audit. `about=None` asks for a full account; a `window`
    narrows it to one span, which is what makes `list_gaps` useful — the
    detective reads an unaccounted-for span and asks about exactly that span.
    """

    about: str | None = None
    window: tuple[int, int] | None = None


@dataclass(frozen=True)
class ChainSummary:
    """Where a claim's provenance ended, as much of it as may be published.

    The same fields the `TRACED_TO` edge carries: which agent, in what role,
    which terminal state, how deep. Not the hops — those name facts inside
    private minds, and the detective has no business holding them.
    """

    terminal: str
    origin_agent: str | None
    carriers: tuple[str, ...]
    depth: int

    @classmethod
    def of(cls, chain: Chain) -> ChainSummary:
        return cls(
            terminal=chain.terminal,
            origin_agent=chain.origin_agent,
            carriers=tuple(dict.fromkeys(chain.carriers)),
            depth=len(chain.hops) - 1,
        )


@dataclass(frozen=True)
class PolygraphReport:
    """What one polygraph returns: a verdict, its shadows, its gaps, its chain.

    `chain` is None when the claim rests on no secondhand memory — there is
    nothing to trace, which is itself an answer.
    """

    claim_id: str
    speaker: str
    subject: str
    place: str
    t0: int
    t1: int
    modality: str
    verdict: str
    coverage: float
    uncovered: int
    support: tuple[dict, ...]
    conflict: tuple[dict, ...]
    gaps: tuple[tuple[int, int], ...]
    chain: ChainSummary | None


@dataclass(frozen=True)
class Accusation:
    """The detective's conclusion, recorded. Not graded here."""

    suspect: str
    rationale: str
    polygraphs_spent: int
    tool_calls: int


class DetectiveTools:
    """One investigation's tool surface, bound to one case."""

    TOOLS = (
        "interview",
        "list_contradictions",
        "list_gaps",
        "check_travel",
        "rank_suspects",
        "polygraph",
        "accuse",
    )
    """The seven tools of spec 7. `test_detective.py` asserts no signature here
    takes a graph name, a seed or an agent's mind."""

    def __init__(
        self,
        db: Any,
        seed: int,
        *,
        suspects: list,
        polygraph_budget: int = POLYGRAPH_BUDGET,
    ) -> None:
        self._case = CaseGraph(db, seed)
        self._engine = AuditEngine(db, seed)
        self._referee = Referee(db, seed)
        self._roster = {suspect.id: suspect for suspect in suspects}
        self._budget = polygraph_budget
        self._reports: dict[str, PolygraphReport] = {}
        self._interviews: Counter[str] = Counter()
        self._calls: Counter[str] = Counter()
        self._accusation: Accusation | None = None

    # -- state the orchestrator and the eval read ---------------------------

    @property
    def polygraphs_left(self) -> int:
        """Budget minus the number of *distinct claims* polygraphed.

        Distinct claims, because the budget rations which minds the referee
        opens on the detective's behalf. A second look at a claim already
        polygraphed opens nothing — its conclusion is in the case graph by
        then and the detective can read it there — so charging for it would
        make the budget a measure of call discipline instead.
        """
        return self._budget - len(self._reports)

    @property
    def accusation(self) -> Accusation | None:
        return self._accusation

    @property
    def calls(self) -> dict[str, int]:
        """Calls per tool, for the per-case cost column of spec 8.3."""
        return dict(self._calls)

    # -- the seven tools ----------------------------------------------------

    def interview(self, suspect: str, question: Question) -> list[dict]:
        """Ask one suspect about a person and a span; ingest and audit the answer.

        Returns each claim as the case graph now holds it, with `new` saying
        whether this interview added it. Testimony the case already records is
        reported as already known rather than ingested twice: asking again
        must not double a suspect's account, or the scoreboard would count
        the detective's own repetition against them.
        """
        self._require_open()
        self._calls["interview"] += 1
        witness = self._require_suspect(suspect)

        said = witness.testify(about=question.about, window=question.window)
        known = {
            (c["speaker"], c["subject"], c["place"], c["t0"], c["t1"], c["modality"]): c["id"]
            for c in self._case.all_claims()
        }
        self._interviews[suspect] += 1
        round_n = self._interviews[suspect]
        turn = self._case.latest_turn()

        answers: list[dict] = []
        for n, claim in enumerate(said, start=1):
            key = (suspect, claim.subject, claim.place, claim.t0, claim.t1, claim.modality)
            claim_id = known.get(key)
            is_new = claim_id is None
            if is_new:
                turn += 1
                claim_id = f"{suspect}-q{round_n}-c{n}"
                self._case.ingest_claim(
                    claim_id=claim_id,
                    speaker=suspect,
                    subject=claim.subject,
                    place=claim.place,
                    t0=claim.t0,
                    t1=claim.t1,
                    turn=turn,
                    modality=claim.modality,
                    relayed_from=claim.relayed_from,
                )
                self._engine.audit_claim(claim_id)
            answers.append({**self._case.claim(claim_id), "new": is_new})
        return answers

    def list_contradictions(self) -> list[dict]:
        """Q5 and Q6 over everything said so far, then read back.

        The checks are re-run on each call because an interview can add the
        claim that contradicts an earlier one. They are idempotent: both
        queries `MERGE` their edge on a `pair_id`, so running them twice
        records one contradiction, not two.
        """
        self._require_open()
        self._calls["list_contradictions"] += 1
        self._case.find_exclusive_presence()
        self._case.find_impossible_travel()
        return self._case.contradictions()

    def list_gaps(self, suspect: str | None = None) -> list[dict]:
        """The spans a suspect's own memory did not account for.

        Spec 7 calls this the sleeper tool, and it is: it hands over the exact
        windows to ask about. A gap is not an allegation — it is a span the
        audit examined and found nothing for.
        """
        self._require_open()
        self._calls["list_gaps"] += 1
        if suspect is not None:
            self._require_suspect(suspect)
        return self._case.gaps_by_speaker(suspect)

    def check_travel(self, place_a: str, place_b: str) -> dict:
        """How long the walk between two rooms takes, and which way it goes.

        The minutes come from the precomputed matrix — the same cell Q6 used —
        so the detective and the impossible-travel check can never disagree
        about the same pair. The route comes from the floor plan, for showing
        the work rather than asserting a number.
        """
        self._require_open()
        self._calls["check_travel"] += 1
        minutes = self._case.travel_minutes(place_a, place_b)
        if minutes is None:
            raise KeyError(
                f"the travel matrix has no cell for {place_a!r} -> {place_b!r}; "
                f"either the places are not on this floor plan or the matrix was "
                f"never built"
            )
        found = self._case.shortest_path(place_a, place_b)
        return {
            "from": place_a,
            "to": place_b,
            "minutes": minutes,
            "route": list(found[1]) if found else [],
        }

    def rank_suspects(self) -> list[dict]:
        """Q8 through the one ranking function, breakdown included.

        What this ranks is how much of what a suspect said their own memory
        does not account for. It is a reading order, not an accusation, and
        the breakdown travels with it so no caller can show the total alone.
        """
        self._require_open()
        self._calls["rank_suspects"] += 1
        return rank_scoreboard(self._case.scoreboard_rows())

    def polygraph(self, suspect: str, claim_id: str) -> PolygraphReport:
        """Examine one claim against its speaker's own memory. Budget: 2.

        The only door into a mind, and it is a one-way door: what comes back
        is the verdict, the redacted evidence shadows, the unaccounted-for
        spans, and where the provenance chain ended. Never the memory itself.

        This is also the only place in the application that writes `TRACED_TO`.
        A chain conclusion exists in the case graph exactly where a polygraph
        was spent, so the two-call budget rations real information: Q8's origin
        and carrier columns stay at zero until the detective pays for them.
        """
        self._require_open()
        self._calls["polygraph"] += 1
        claim = self._case.claim(claim_id)
        if claim["speaker"] != suspect:
            raise ValueError(
                f"claim {claim_id!r} was made by {claim['speaker']!r}, not {suspect!r}; "
                f"a polygraph examines the speaker's own account, and the speaker is "
                f"already public in the case file"
            )
        cached = self._reports.get(claim_id)
        if cached is not None:
            return cached
        if self.polygraphs_left <= 0:
            raise BudgetExhausted(
                f"this case allows {self._budget} polygraphs and both are spent "
                f"({', '.join(sorted(self._reports))}); the case graph still holds "
                f"the verdicts, gaps and contradictions the audit found"
            )

        if claim["verdict"] == PENDING:
            self._engine.audit_claim(claim_id)
            claim = self._case.claim(claim_id)

        chain = self._referee.trace_claim(claim_id)
        if chain is not None:
            self._referee.materialize_chain(chain)

        report = PolygraphReport(
            claim_id=claim_id,
            speaker=claim["speaker"],
            subject=claim["subject"],
            place=claim["place"],
            t0=claim["t0"],
            t1=claim["t1"],
            modality=claim["modality"],
            verdict=claim["verdict"],
            coverage=claim["coverage"],
            uncovered=claim["uncovered"],
            support=tuple(self._case.support_shadows_for_claim(claim_id)),
            conflict=tuple(self._case.conflict_shadows_for_claim(claim_id)),
            gaps=tuple(self._case.gaps_for_claim(claim_id)),
            chain=None if chain is None else ChainSummary.of(chain),
        )
        self._reports[claim_id] = report
        return report

    def accuse(self, suspect: str, rationale: str) -> Accusation:
        """Name a suspect and close the investigation.

        Recorded, not graded: whether the accusation is right is measured
        against ground truth by the referee, which this surface cannot reach.
        """
        self._require_open()
        self._calls["accuse"] += 1
        self._require_suspect(suspect)
        self._accusation = Accusation(
            suspect=suspect,
            rationale=rationale,
            polygraphs_spent=len(self._reports),
            tool_calls=sum(self._calls.values()),
        )
        return self._accusation

    # -- guards -------------------------------------------------------------

    def _require_open(self) -> None:
        if self._accusation is not None:
            raise ValueError(
                f"the case is closed: {self._accusation.suspect!r} was already accused"
            )

    def _require_suspect(self, suspect: str) -> Any:
        """Resolve a name against the roster bound at construction.

        A name that is not on it raises. The roster is how a public case-file
        id becomes an interviewable party without the caller ever naming a
        graph.
        """
        if suspect not in self._roster:
            raise KeyError(
                f"{suspect!r} is not a suspect in this case; the case file names "
                f"{sorted(self._roster)}"
            )
        return self._roster[suspect]
