"""The deterministic world generator (spec section 10).

Two phases, deliberately separate:

- `plan_world(seed)` builds the whole evening as **plain immutable data**, with
  no database involved. Determinism is testable by comparing two plans field
  for field, and an invariant failure shows up as a diff rather than as a
  mysterious count mismatch in a graph.
- `generate(db, seed, ...)` writes a plan into `world:{seed}`, the seven
  `mind:{seed}:{agent}` graphs and `case:{seed}`.

**Determinism rules this module obeys.** One `random.Random(seed)`, threaded
explicitly; no module-level `random`; no wall clock; no iteration over an
unsorted set or a dict whose insertion order depends on anything but the seed.
Every collection that feeds a decision is sorted first. The whole demo and the
whole benchmark replay exactly because of this.

**Only the generator creates provenance** (PROJECT_RULES.md rule 5). Transmissions,
hearsay facts and `PlantedFabrication` records are written here and nowhere
else. The audit engine reads them; it never adds one.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from itertools import permutations
from typing import Any

from backend.app.audit.time_contract import overlaps
from backend.app.case.graph import CaseGraph
from backend.app.minds.access import MindAccess
from backend.app.world import queries as q

TICK_MIN = 0
TICK_MAX = 300

ROOM_NAMES = [
    ("hall", "Entrance Hall"),
    ("kitchen", "Kitchen"),
    ("library", "Library"),
    ("study", "Study"),
    ("cellar", "Wine Cellar"),
    ("conservatory", "Conservatory"),
    ("gallery", "Long Gallery"),
    ("ballroom", "Ballroom"),
    ("scullery", "Scullery"),
    ("terrace", "Terrace"),
    ("billiard", "Billiard Room"),
    ("attic", "Attic"),
]

PERSON_NAMES = [
    ("p1", "Avery"),
    ("p2", "Blake"),
    ("p3", "Cato"),
    ("p4", "Dara"),
    ("p5", "Esme"),
    ("p6", "Faris"),
    ("p7", "Gale"),
]


def world_graph_name(seed: int) -> str:
    """`world:{seed}` — the one place this string is built."""
    return f"world:{seed}"


@dataclass(frozen=True)
class WorldSpec:
    """Knobs on the generator. Defaults are the spec 10 numbers.

    `plan_seed` separates *which world* from *which graphs*: a test can write
    the same world into two different seeds' graphs and compare, which is how
    the write path is proved free of order-dependence.
    """

    plan_seed: int | None = None
    n_places: int = 11
    n_people: int = 7
    witness_miss_probability: float = 0.10
    with_accomplice: bool = True
    exchanges: int = 14
    incident_length: int = 20


@dataclass(frozen=True)
class Place:
    id: str
    name: str


@dataclass(frozen=True)
class Person:
    id: str
    name: str
    role: str  # honest | culprit | accomplice


@dataclass(frozen=True)
class Presence:
    """A true route segment: `person` really was at `place` over [t0, t1)."""

    person: str
    place: str
    t0: int
    t1: int


@dataclass(frozen=True)
class PlannedFact:
    """A memory to be written into exactly one mind.

    `owner` is whose mind holds it, which is not the same as `subject`, the
    person it is about. `learned_at` is when the owner came to hold it:
    `t0` for something witnessed, the transmission tick for hearsay.
    """

    id: str
    owner: str
    kind: str
    src: str
    subject: str
    place: str
    t0: int
    t1: int
    learned_at: int


@dataclass(frozen=True)
class PlannedTransmission:
    """One act of telling. `src_fact_id` points into the speaker's own graph."""

    id: str
    fact_id: str
    owner: str
    tick: int
    src_agent: str
    src_fact_id: str


@dataclass(frozen=True)
class Incident:
    id: str
    place: str
    t0: int
    t1: int


@dataclass(frozen=True)
class PlantedFabrication:
    """Ground truth about one thing the generator told an agent to assert.

    Referee-only, and the reason ground-truth scoring never has to infer
    intent from the audit's own output.
    `src_fact_id` is the dangling reference the fabricator cites when passing
    it on — it is deliberately not a real fact, so the referee's chain walk
    terminates in a nameable state rather than in silence.
    """

    claim_key: str
    by_person: str
    reason: str
    place: str
    t0: int
    t1: int
    src_fact_id: str
    relayed_fact_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorldPlan:
    """A whole evening as data. Compared field-for-field by the seed test."""

    seed: int
    places: tuple[Place, ...]
    adjacency: dict[tuple[str, str], int]
    travel: dict[tuple[str, str], int]
    people: tuple[Person, ...]
    presences: tuple[Presence, ...]
    incident: Incident
    facts: tuple[PlannedFact, ...]
    transmissions: tuple[PlannedTransmission, ...]
    fabrications: tuple[PlantedFabrication, ...]
    rejected: int = 0
    notes: tuple[str, ...] = field(default_factory=tuple)


# -- floor plan ---------------------------------------------------------------


def _floor_plan(rng: random.Random, n_places: int) -> tuple[tuple[Place, ...], dict]:
    """A connected floor plan: a spanning chain plus a few extra corridors.

    The chain guarantees connectivity without a retry loop, so the generator
    never has to reject a world for an unreachable room. The extra corridors
    make the shortest path interesting enough that `algo.SPpaths` has real
    work to do and the travel check is not trivially satisfiable.
    """
    chosen = ROOM_NAMES[:n_places]
    places = tuple(Place(id=pid, name=name) for pid, name in chosen)
    ids = [p.id for p in places]

    order = ids[:]
    rng.shuffle(order)
    adjacency: dict[tuple[str, str], int] = {}

    def link(a: str, b: str, minutes: int) -> None:
        adjacency[(a, b)] = minutes
        adjacency[(b, a)] = minutes

    for a, b in zip(order, order[1:], strict=False):
        link(a, b, rng.randint(2, 6))

    # A handful of shortcuts, chosen from a sorted candidate list so the
    # selection cannot depend on set iteration order.
    candidates = sorted(
        (a, b) for i, a in enumerate(order) for b in order[i + 2 :] if (a, b) not in adjacency
    )
    rng.shuffle(candidates)
    for a, b in candidates[: max(2, n_places // 3)]:
        link(a, b, rng.randint(3, 7))

    return places, adjacency


def _all_pairs_travel(ids: list[str], adjacency: dict[tuple[str, str], int]) -> dict:
    """Floyd-Warshall over the floor plan.

    The *case graph* builds its matrix with `algo.SPpaths`, which is the real
    load-bearing use. This copy exists so `plan_world` can be pure data with no
    database, and `test_world` asserts the two agree.
    """
    dist = {(a, b): (0 if a == b else 10**6) for a in ids for b in ids}
    for (a, b), minutes in sorted(adjacency.items()):
        dist[(a, b)] = min(dist[(a, b)], minutes)
    for k in ids:
        for i in ids:
            for j in ids:
                through = dist[(i, k)] + dist[(k, j)]
                if through < dist[(i, j)]:
                    dist[(i, j)] = through
    return {pair: d for pair, d in dist.items() if pair[0] != pair[1]}


# -- routes -------------------------------------------------------------------


def _route(
    rng: random.Random,
    person: str,
    ids: list[str],
    travel: dict[tuple[str, str], int],
    *,
    must_be_at: tuple[str, int, int] | None = None,
) -> list[Presence]:
    """One person's evening, built so it is travel-feasible by construction.

    A segment ends, the walk to the next room is paid in full from the
    shortest-path matrix, and only then does the next segment start. There is
    no rejection sampling and no repair pass: the invariant holds because the
    construction cannot violate it.

    `must_be_at` pins one segment — how the culprit is placed at the incident.
    """
    segments: list[Presence] = []
    pinned = must_be_at

    place = rng.choice(sorted(ids))
    t = rng.randint(0, 10)

    if pinned is not None:
        pin_place, pin_t0, pin_t1 = pinned
        # Start somewhere that can reach the pinned room in time.
        reachable = sorted(
            p for p in ids if p == pin_place or travel[(p, pin_place)] <= pin_t0 - 5
        )
        place = rng.choice(reachable) if reachable else pin_place
        t = 0

    while t < TICK_MAX:
        if pinned is not None:
            pin_place, pin_t0, pin_t1 = pinned
            need = 0 if place == pin_place else travel[(place, pin_place)]
            if t + need >= pin_t0:
                # Time to take up the pinned position.
                segments.append(Presence(person, pin_place, pin_t0, pin_t1))
                place, t, pinned = pin_place, pin_t1, None
                continue
            dwell = min(rng.randint(8, 25), pin_t0 - need - t)
            if dwell < 5:
                segments.append(Presence(person, pin_place, pin_t0, pin_t1))
                place, t, pinned = pin_place, pin_t1, None
                continue
        else:
            dwell = rng.randint(10, 35)

        t1 = min(t + dwell, TICK_MAX)
        if t1 > t:
            segments.append(Presence(person, place, t, t1))
        if t1 >= TICK_MAX:
            break

        nxt = rng.choice(sorted(p for p in ids if p != place))
        t = t1 + travel[(place, nxt)]
        place = nxt

    return segments


# -- memories -----------------------------------------------------------------


def _witness_facts(
    rng: random.Random,
    presences: list[Presence],
    *,
    miss_probability: float,
) -> list[PlannedFact]:
    """What each person remembers: their own movements, and who they saw.

    Co-located people witness each other, with a miss probability so natural
    gaps exist. Those gaps are the point — a world where everyone sees
    everything has no INDETERMINATE claims and nothing for the detective to
    ask about.
    """
    facts: list[PlannedFact] = []
    n = 0

    # Everyone remembers where they themselves were.
    for pr in sorted(presences, key=lambda p: (p.person, p.t0, p.place)):
        n += 1
        facts.append(
            PlannedFact(
                id=f"f{n}",
                owner=pr.person,
                kind="did",
                src="witnessed",
                subject=pr.person,
                place=pr.place,
                t0=pr.t0,
                t1=pr.t1,
                learned_at=pr.t0,
            )
        )

    # And who else was in the room, each direction decided independently.
    ordered = sorted(presences, key=lambda p: (p.t0, p.person, p.place))
    for i, a in enumerate(ordered):
        for b in ordered[i + 1 :]:
            if a.person == b.person or a.place != b.place:
                continue
            if not overlaps(a.t0, a.t1, b.t0, b.t1):
                continue
            o0, o1 = max(a.t0, b.t0), min(a.t1, b.t1)
            for watcher, watched in ((a.person, b.person), (b.person, a.person)):
                if rng.random() < miss_probability:
                    continue  # they were there, but did not register it
                n += 1
                facts.append(
                    PlannedFact(
                        id=f"f{n}",
                        owner=watcher,
                        kind="saw",
                        src="witnessed",
                        subject=watched,
                        place=a.place,
                        t0=o0,
                        t1=o1,
                        learned_at=o0,
                    )
                )
    return facts


def _exchanges(
    rng: random.Random,
    presences: list[Presence],
    facts: list[PlannedFact],
    *,
    count: int,
    next_fact_n: int,
) -> tuple[list[PlannedFact], list[PlannedTransmission]]:
    """Pairs who met pass on 1-2 witnessed facts each.

    Temporal consistency holds by construction: the tick is inside the window
    the two shared, and only facts the speaker had already learned by that
    tick are eligible. An agent cannot pass on what it did not yet know.
    """
    meetings = []
    ordered = sorted(presences, key=lambda p: (p.t0, p.person, p.place))
    for i, a in enumerate(ordered):
        for b in ordered[i + 1 :]:
            if a.person == b.person or a.place != b.place:
                continue
            if overlaps(a.t0, a.t1, b.t0, b.t1):
                meetings.append((max(a.t0, b.t0), min(a.t1, b.t1), a.person, b.person))
    meetings.sort()
    if not meetings:
        return [], []

    rng.shuffle(meetings)
    by_owner: dict[str, list[PlannedFact]] = {}
    for f in facts:
        by_owner.setdefault(f.owner, []).append(f)

    new_facts: list[PlannedFact] = []
    transmissions: list[PlannedTransmission] = []
    n = next_fact_n
    t_n = 0

    for o0, o1, speaker, listener in meetings[:count]:
        tick = o0 if o1 - o0 <= 1 else rng.randrange(o0, o1)
        for direction in ((speaker, listener), (listener, speaker)):
            teller, hearer = direction
            eligible = sorted(
                (
                    f
                    for f in by_owner.get(teller, [])
                    if f.src == "witnessed" and f.learned_at <= tick and f.subject != hearer
                ),
                key=lambda f: f.id,
            )
            if not eligible:
                continue
            for source in rng.sample(eligible, min(len(eligible), rng.randint(1, 2))):
                n += 1
                t_n += 1
                new_facts.append(
                    PlannedFact(
                        id=f"f{n}",
                        owner=hearer,
                        kind="heard",
                        src="hearsay",
                        subject=source.subject,
                        place=source.place,
                        t0=source.t0,
                        t1=source.t1,
                        learned_at=tick,
                    )
                )
                transmissions.append(
                    PlannedTransmission(
                        id=f"tr{t_n}",
                        fact_id=f"f{n}",
                        owner=hearer,
                        tick=tick,
                        src_agent=teller,
                        src_fact_id=source.id,
                    )
                )
    return new_facts, transmissions


def _plant_fabrication(
    rng: random.Random,
    *,
    culprit: Person,
    honest_ids: list[str],
    incident: Incident,
    places: list[str],
    presences: list[Presence],
    next_fact_n: int,
    next_tr_n: int,
) -> tuple[PlantedFabrication, list[PlannedFact], list[PlannedTransmission]]:
    """The culprit asserts it was elsewhere, and tells someone so.

    The culprit's *own mind stays truthful* — it holds no memory of being in
    the alibi room, so the claim it makes has nothing in its own memory to
    ground it. What it passes on cites `src_fact_id`, a fact that does not
    exist anywhere, so the chain the referee walks later terminates in a
    nameable state instead of resolving to a real memory.

    The honest suspect who receives it has done nothing wrong: their memory
    genuinely contains what they were told. That is the innocent-repeater
    case, and the reason HEARSAY is one of the five verdicts.
    """
    elsewhere = sorted(p for p in places if p != incident.place)
    alibi_place = rng.choice(elsewhere)
    claim_key = f"{culprit.id}|{alibi_place}|{incident.t0}|{incident.t1}"
    dangling = f"f-void-{culprit.id}"

    # Tell someone the culprit actually met, after the incident.
    windows = sorted(
        (max(a.t0, b.t0), min(a.t1, b.t1), b.person)
        for a in presences
        if a.person == culprit.id
        for b in presences
        if b.person in honest_ids
        and b.place == a.place
        and overlaps(a.t0, a.t1, b.t0, b.t1)
        and max(a.t0, b.t0) >= incident.t1
    )
    facts: list[PlannedFact] = []
    transmissions: list[PlannedTransmission] = []
    relayed: list[str] = []

    if windows:
        o0, o1, listener = windows[0]
        tick = o0 if o1 - o0 <= 1 else rng.randrange(o0, o1)
        fid = f"f{next_fact_n + 1}"
        facts.append(
            PlannedFact(
                id=fid,
                owner=listener,
                kind="heard",
                src="hearsay",
                subject=culprit.id,
                place=alibi_place,
                t0=incident.t0,
                t1=incident.t1,
                learned_at=tick,
            )
        )
        transmissions.append(
            PlannedTransmission(
                id=f"tr{next_tr_n + 1}",
                fact_id=fid,
                owner=listener,
                tick=tick,
                src_agent=culprit.id,
                src_fact_id=dangling,
            )
        )
        relayed.append(fid)

    fab = PlantedFabrication(
        claim_key=claim_key,
        by_person=culprit.id,
        reason="places itself away from the incident room during the incident window",
        place=alibi_place,
        t0=incident.t0,
        t1=incident.t1,
        src_fact_id=dangling,
        relayed_fact_ids=tuple(relayed),
    )
    return fab, facts, transmissions


# -- the plan -----------------------------------------------------------------


def plan_world(seed: int, spec: WorldSpec | None = None) -> WorldPlan:
    """Build a whole evening as immutable data. No database involved."""
    spec = spec or WorldSpec()
    rng = random.Random(seed)

    places, adjacency = _floor_plan(rng, spec.n_places)
    ids = [p.id for p in places]
    travel = _all_pairs_travel(ids, adjacency)

    culprit_idx = rng.randrange(spec.n_people)
    accomplice_idx = None
    if spec.with_accomplice:
        others = [i for i in range(spec.n_people) if i != culprit_idx]
        accomplice_idx = rng.choice(others)
    people = tuple(
        Person(
            id=pid,
            name=name,
            role=(
                "culprit"
                if i == culprit_idx
                else "accomplice"
                if i == accomplice_idx
                else "honest"
            ),
        )
        for i, (pid, name) in enumerate(PERSON_NAMES[: spec.n_people])
    )
    culprit = people[culprit_idx]

    incident_place = rng.choice(sorted(ids))
    incident_t0 = rng.randrange(60, 200)
    incident = Incident(
        id="incident",
        place=incident_place,
        t0=incident_t0,
        t1=incident_t0 + spec.incident_length,
    )

    presences: list[Presence] = []
    for person in people:
        pin = (
            (incident.place, incident.t0, incident.t1) if person.id == culprit.id else None
        )
        presences.extend(_route(rng, person.id, ids, travel, must_be_at=pin))

    facts = _witness_facts(rng, presences, miss_probability=spec.witness_miss_probability)
    heard, transmissions = _exchanges(
        rng, presences, facts, count=spec.exchanges, next_fact_n=len(facts)
    )
    facts = facts + heard

    honest_ids = sorted(p.id for p in people if p.role == "honest")
    fab, fab_facts, fab_transmissions = _plant_fabrication(
        rng,
        culprit=culprit,
        honest_ids=honest_ids,
        incident=incident,
        places=ids,
        presences=presences,
        next_fact_n=len(facts),
        next_tr_n=len(transmissions),
    )
    facts = facts + fab_facts
    transmissions = transmissions + fab_transmissions

    return WorldPlan(
        seed=seed,
        places=places,
        adjacency=adjacency,
        travel=travel,
        people=people,
        presences=tuple(presences),
        incident=incident,
        facts=tuple(facts),
        transmissions=tuple(transmissions),
        fabrications=(fab,),
        rejected=0,
        notes=(
            f"culprit={culprit.id}",
            f"incident={incident.place}@[{incident.t0},{incident.t1})",
        ),
    )


# -- writing it out -----------------------------------------------------------


def generate(db: Any, seed: int, spec: WorldSpec | None = None) -> dict[str, int]:
    """Write a plan into the world, mind and case graphs. Returns counts.

    The counts are what `test_world` compares across two seeds to prove the
    write path adds no order-dependence of its own.
    """
    spec = spec or WorldSpec()
    plan = plan_world(spec.plan_seed if spec.plan_seed is not None else seed, spec)

    world = db.select_graph(world_graph_name(seed))
    for place in plan.places:
        world.query(q.UPSERT_PLACE, {"id": place.id, "name": place.name})
    for person in plan.people:
        world.query(
            q.UPSERT_PERSON, {"id": person.id, "name": person.name, "role": person.role}
        )
    for (a, b), minutes in sorted(plan.adjacency.items()):
        if a < b:
            world.query(q.UPSERT_ADJACENCY, {"a": a, "b": b, "minutes": minutes})
    for pr in plan.presences:
        world.query(
            q.CREATE_PRESENCE,
            {"person": pr.person, "place": pr.place, "t0": pr.t0, "t1": pr.t1},
        )
    world.query(
        q.UPSERT_INCIDENT,
        {
            "id": plan.incident.id,
            "place": plan.incident.place,
            "t0": plan.incident.t0,
            "t1": plan.incident.t1,
        },
    )
    for fab in plan.fabrications:
        world.query(
            q.CREATE_PLANTED_FABRICATION,
            {"claim_key": fab.claim_key, "by_person": fab.by_person, "reason": fab.reason},
        )

    # Minds. Each person's memories go into their own graph and nowhere else.
    minds = {p.id: MindAccess(db, seed, p.id) for p in plan.people}
    for mind in minds.values():
        for place in plan.places:
            mind.upsert_place(place.id, place.name)
        for person in plan.people:
            mind.upsert_person(person.id, person.name)
    for fact in plan.facts:
        minds[fact.owner].write_fact(
            fact_id=fact.id,
            kind=fact.kind,
            src=fact.src,
            subject=fact.subject,
            place=fact.place,
            t0=fact.t0,
            t1=fact.t1,
            learned_at=fact.learned_at,
        )
    for tr in plan.transmissions:
        minds[tr.owner].write_transmission(
            fact_id=tr.fact_id,
            transmission_id=tr.id,
            tick=tr.tick,
            src_agent=tr.src_agent,
            src_fact_id=tr.src_fact_id,
        )

    # The case file: the public floor plan, the suspects, the incident, and the
    # precomputed travel matrix built with algo.SPpaths.
    case = CaseGraph(db, seed)
    for place in plan.places:
        case.upsert_place(place.id, place.name)
    for (a, b), minutes in sorted(plan.adjacency.items()):
        if a < b:
            case.upsert_adjacency(a, b, minutes)
    for person in plan.people:
        case.upsert_suspect(person.id, person.name)
    case.upsert_incident(
        plan.incident.id, plan.incident.place, plan.incident.t0, plan.incident.t1
    )
    matrix_cells = case.build_travel_matrix([p.id for p in plan.places])

    # The two travel matrices must agree, or the audit would be checking
    # against a different floor plan than the one people walked.
    for a, b in permutations(sorted(p.id for p in plan.places), 2):
        on_graph = case.travel_minutes(a, b)
        if on_graph != plan.travel[(a, b)]:
            raise RuntimeError(
                f"travel matrix disagreement {a}->{b}: algo.SPpaths says {on_graph}, "
                f"the generator's own shortest path says {plan.travel[(a, b)]}"
            )

    return {
        "places": len(plan.places),
        "people": len(plan.people),
        "presences": len(plan.presences),
        "facts": len(plan.facts),
        "transmissions": len(plan.transmissions),
        "fabrications": len(plan.fabrications),
        "travel_cells": matrix_cells,
    }
