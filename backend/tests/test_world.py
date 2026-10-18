"""World generator invariants (spec section 10).

Three properties the generator must hold, because the audit engine is only
trustworthy if the world it runs against is coherent:

1. **Identical world per seed.** The whole system is deterministic, so a demo
   and a benchmark replay exactly.
2. **Every route is travel-feasible.** A generated person cannot teleport, or
   the impossible-travel check would be firing on the generator's own bugs.
3. **Every transmission is temporally consistent** — `source.learned_at <=
   tick`. Someone cannot pass on what they did not yet know.

A fourth, implied by the first: nothing in the generator may depend on wall
clock time, the global `random` module, or iteration order over an unsorted
set.
"""

from __future__ import annotations

from backend.app.audit.time_contract import overlaps, travel_feasible
from backend.app.world.generator import WorldSpec, generate, plan_world

SEED = 4242


def test_identical_world_per_seed():
    """Two plans from one seed are equal, field for field.

    Compared as plain data before anything touches a graph, so a difference
    shows up as a diff of the plan rather than a mysterious count mismatch.
    """
    a = plan_world(SEED)
    b = plan_world(SEED)
    assert a == b


def test_different_seeds_give_different_worlds():
    """Otherwise the determinism test above would pass vacuously."""
    assert plan_world(SEED) != plan_world(SEED + 1)


def test_every_route_is_travel_feasible():
    """Consecutive presences of one person leave time for the walk between them.

    Checked against the generator's own shortest-path matrix, so a route that
    hops between two non-adjacent rooms has to pay the full multi-corridor
    cost, not just one edge.
    """
    plan = plan_world(SEED)
    for person in plan.people:
        segments = [p for p in plan.presences if p.person == person.id]
        for earlier, later in zip(segments, segments[1:], strict=False):
            need = plan.travel[(earlier.place, later.place)] if earlier.place != later.place else 0
            assert travel_feasible(earlier.t1, later.t0, need), (
                f"{person.id}: {earlier.place}@[{earlier.t0},{earlier.t1}) -> "
                f"{later.place}@[{later.t0},{later.t1}) needs {need} minutes, "
                f"has {later.t0 - earlier.t1}"
            )


def test_one_person_is_never_in_two_places_at_once():
    """The ground truth must not itself be an exclusive-presence contradiction."""
    plan = plan_world(SEED)
    for person in plan.people:
        segments = [p for p in plan.presences if p.person == person.id]
        for i, a in enumerate(segments):
            for b in segments[i + 1 :]:
                if a.place != b.place:
                    assert not overlaps(a.t0, a.t1, b.t0, b.t1), (
                        f"{person.id} is in {a.place} and {b.place} at once"
                    )


def test_every_transmission_is_temporally_consistent():
    """`source.learned_at <= tick` for every transmission.

    A violation means an agent passed on something before they knew it. The
    referee reports that as CHAIN_TEMPORAL_VIOLATION when it finds it in a
    *claim*; finding it in the generator's own output would mean the ground
    truth was incoherent.
    """
    plan = plan_world(SEED)
    by_id = {f.id: f for f in plan.facts}
    for tr in plan.transmissions:
        source = by_id.get(tr.src_fact_id)
        if source is None:
            # Only a planted fabrication may reference a fact that does not
            # exist, and the generator records that intent explicitly.
            assert tr.src_fact_id in {f.src_fact_id for f in plan.fabrications}, (
                f"transmission {tr.id} cites unknown fact {tr.src_fact_id} "
                f"and is not a recorded fabrication"
            )
            continue
        assert source.learned_at <= tr.tick, (
            f"transmission {tr.id} at tick {tr.tick} cites fact "
            f"{source.id} learned at {source.learned_at}"
        )


def test_hearsay_facts_are_learned_when_they_were_heard():
    """A hearsay fact's `learned_at` is its transmission tick, not its t0.

    This is the field that makes the chain's temporal check possible at all.
    """
    plan = plan_world(SEED)
    ticks = {tr.fact_id: tr.tick for tr in plan.transmissions}
    for fact in plan.facts:
        if fact.src == "hearsay":
            assert fact.id in ticks, f"hearsay fact {fact.id} has no transmission"
            assert fact.learned_at == ticks[fact.id]
        if fact.src == "witnessed":
            assert fact.learned_at == fact.t0


def test_the_floor_plan_is_connected_and_sized_per_spec():
    """10-12 places, integer corridor minutes, every pair reachable."""
    plan = plan_world(SEED)
    assert 10 <= len(plan.places) <= 12
    for (a, b), minutes in plan.adjacency.items():
        assert isinstance(minutes, int) and minutes > 0
        assert plan.adjacency[(b, a)] == minutes, "corridors are symmetric"
    ids = [p.id for p in plan.places]
    for a in ids:
        for b in ids:
            if a != b:
                assert plan.travel[(a, b)] > 0, f"{a} -> {b} unreachable"


def test_seven_suspects_one_incident_and_a_culprit_present_for_it():
    """Spec 10's cast, and the one fact that makes the case solvable."""
    plan = plan_world(SEED)
    assert len(plan.people) == 7
    roles = [p.role for p in plan.people]
    assert roles.count("culprit") == 1
    assert roles.count("accomplice") <= 1

    culprit = next(p for p in plan.people if p.role == "culprit")
    present = [
        pr
        for pr in plan.presences
        if pr.person == culprit.id
        and pr.place == plan.incident.place
        and overlaps(pr.t0, pr.t1, plan.incident.t0, plan.incident.t1)
    ]
    assert present, "the culprit must be at the incident while it happens"


def test_the_culprit_fabrication_is_recorded_as_planted():
    """Deception labels are ground truth, written by the generator only.

    `PlantedFabrication` is what makes scoring possible without guessing. It
    is referee-only and never leaves the scoring path — which is also why the
    audit engine has no access to it.
    """
    plan = plan_world(SEED)
    assert plan.fabrications, "the culprit fabricates exactly one thing"
    culprit = next(p for p in plan.people if p.role == "culprit")
    for fab in plan.fabrications:
        assert fab.by_person == culprit.id
        assert fab.reason


def test_the_fabrication_reaches_an_honest_mind_as_hearsay():
    """The innocent-repeater case: an honest suspect holds it secondhand.

    This is the demo moment and the reason HEARSAY is a verdict rather than a
    footnote. The repeater is not deceiving anyone — their own memory
    genuinely contains what they were told.
    """
    plan = plan_world(SEED)
    honest = {p.id for p in plan.people if p.role == "honest"}
    by_id = {f.id: f for f in plan.facts}

    relayed = [by_id[fid] for fab in plan.fabrications for fid in fab.relayed_fact_ids]
    assert relayed, "the fabrication was never passed to anyone"
    assert any(f.owner in honest for f in relayed), "no honest mind received it"
    for fact in relayed:
        assert fact.src == "hearsay", "a relayed fabrication arrives as hearsay"


def test_the_culprits_fabrication_is_cited_but_unwitnessed():
    """The culprit's *witnessed* memory stays truthful about where it was.

    Rewritten for M2. M1 had the relay cite a fact id that existed in no
    mind, which the referee can only ever report as CHAIN_BROKEN — a state
    spec 5.7 calls ambiguous and says is not an origin. A world whose sole
    fabrication is unattributable cannot exercise the three ORIGIN states at
    all, so the cited fact now exists in the culprit's own mind as `inferred`.

    An inferred memory neither grounds nor refutes (5.5's last row), so the
    chain reaches the culprit and finds the record present but unbacked,
    while the culprit's witnessed memory of the incident room conflicts with
    it. The assertion is stricter than M1's, not weaker: the fact must exist,
    must belong to the culprit, must not be witnessed, and must sit at a
    different place from where the culprit really was.
    """
    plan = plan_world(SEED)
    by_id = {f.id: f for f in plan.facts}
    culprit = next(p for p in plan.people if p.role == "culprit")

    for fab in (f for f in plan.fabrications if f.pathology == "none"):
        cited = by_id.get(fab.src_fact_id)
        assert cited is not None, "a traceable fabrication must cite a real record"
        assert cited.owner == culprit.id
        assert cited.src == "inferred", "the culprit is never given a memory it could not have"
        assert cited.place != plan.incident.place

    # No witnessed memory anywhere places the culprit at the alibi room then.
    for fab in plan.fabrications:
        for fact in plan.facts:
            if fact.src != "witnessed" or fact.subject != culprit.id:
                continue
            if fact.place == fab.place:
                assert not overlaps(fact.t0, fact.t1, fab.t0, fab.t1), (
                    f"witnessed fact {fact.id} backs the fabricated alibi"
                )


def test_pathological_chains_are_planted_only_when_asked_for():
    """The default world has one clean, traceable fabrication and no others.

    The broken and early-telling chains exist so the referee's detection of
    each is tested rather than assumed, which means they must not leak into
    the default world and skew the verdict mix.
    """
    default = plan_world(SEED)
    assert [f.pathology for f in default.fabrications] == ["none"]

    both = plan_world(
        SEED,
        WorldSpec(plant_broken_chain=True, plant_temporal_violation=True),
    )
    assert sorted(f.pathology for f in both.fabrications) == [
        "broken_chain", "none", "temporal_violation",
    ]


def test_generate_writes_the_world_and_is_reproducible(db, scratch_seed, graphs):
    """Generating twice into fresh graphs produces identical counts.

    The plan is already proved deterministic above; this proves the write path
    does not introduce order-dependence of its own.
    """
    from backend.app.case.graph import case_graph_name
    from backend.app.minds.access import mind_graph_name
    from backend.app.world.generator import world_graph_name

    def build(seed: int) -> dict:
        graphs(world_graph_name(seed))
        graphs(case_graph_name(seed))
        plan = plan_world(SEED)
        for person in plan.people:
            graphs(mind_graph_name(seed, person.id))
        return generate(db, seed, spec=WorldSpec(plan_seed=SEED))

    first = build(scratch_seed)
    second = build(scratch_seed + 500)
    assert first == second


def test_generated_world_audits_without_contradicting_the_honest(db, scratch_seed, graphs):
    """End to end: generate, testify, audit.

    The properties that matter are structural, not a particular verdict mix:
    every claim gets a verdict, and an honest suspect's claims about
    themselves are never CONTRADICTED by their own memory — if they were, the
    generator and the audit would disagree about the same world.
    """
    from backend.app.agents.scripted import interview_all
    from backend.app.audit.engine import AuditEngine
    from backend.app.case.graph import CaseGraph, case_graph_name
    from backend.app.minds.access import mind_graph_name
    from backend.app.world.generator import world_graph_name

    seed = scratch_seed
    graphs(world_graph_name(seed))
    graphs(case_graph_name(seed))
    plan = plan_world(SEED)
    for person in plan.people:
        graphs(mind_graph_name(seed, person.id))

    generate(db, seed, spec=WorldSpec(plan_seed=SEED))
    claims = interview_all(db, seed, plan=plan)
    assert claims, "the scripted suspects said nothing"

    results = AuditEngine(db, seed).audit_all()
    assert len(results) == len(claims)
    assert all(r.verdict != "PENDING" for r in results)

    honest = {p.id for p in plan.people if p.role == "honest"}
    for r in results:
        if r.speaker in honest and r.subject == r.speaker:
            assert r.verdict != "CONTRADICTED", (
                f"honest {r.speaker} contradicted by their own memory on {r.claim_id}"
            )

    case = CaseGraph(db, seed)
    case.find_exclusive_presence()
    case.find_impossible_travel()
    case.find_corroboration()
    tally = case.verdict_tally()
    assert sum(tally.values()) == len(claims)


# -- scripted suspects -------------------------------------------------------
#
# The suspects are tested here, alongside the generator, because what a
# suspect can say is a function of the world that gave it its memories. M3's
# LLM suspects are expected to be cut, which makes these the final suspect
# implementation rather than a test double.


def test_testimony_is_deterministic(db, scratch_seed, graphs):
    """Same mind, same policy, same claims in the same order."""
    from backend.app.agents.scripted import build_suspects
    from backend.app.case.graph import case_graph_name
    from backend.app.minds.access import mind_graph_name
    from backend.app.world.generator import world_graph_name

    seed = scratch_seed
    graphs(world_graph_name(seed))
    graphs(case_graph_name(seed))
    plan = plan_world(SEED)
    for person in plan.people:
        graphs(mind_graph_name(seed, person.id))
    generate(db, seed, spec=WorldSpec(plan_seed=SEED))

    first = [s.testify() for s in build_suspects(db, seed, plan=plan)]
    second = [s.testify() for s in build_suspects(db, seed, plan=plan)]
    assert first == second


def test_the_claim_cap_does_not_favour_early_testimony(db, scratch_seed, graphs):
    """A cap must sample the evening, not truncate it.

    Taking the earliest N claims drops the back half of everyone's evening,
    which is a biased sample rather than a cap: late-evening claims could
    never be audited at all. The kept claims must span the same range as the
    full set.
    """
    from backend.app.agents.scripted import build_suspects
    from backend.app.case.graph import case_graph_name
    from backend.app.minds.access import mind_graph_name
    from backend.app.world.generator import world_graph_name

    seed = scratch_seed
    graphs(world_graph_name(seed))
    graphs(case_graph_name(seed))
    plan = plan_world(SEED)
    for person in plan.people:
        graphs(mind_graph_name(seed, person.id))
    generate(db, seed, spec=WorldSpec(plan_seed=SEED))

    talkative = None
    for suspect in build_suspects(db, seed, plan=plan):
        uncapped = suspect.testify(limit=None)
        if len(uncapped) > len(suspect.testify()):
            talkative = (suspect, uncapped)
            break
    assert talkative, "no suspect exceeded the cap, so this test proves nothing"

    suspect, uncapped = talkative
    capped = suspect.testify()
    assert len(capped) < len(uncapped)
    # The last claim kept must reach roughly as late as the last one dropped.
    assert capped[-1].t1 >= uncapped[-1].t1 - 10, (
        f"cap kept nothing after tick {capped[-1].t1} while testimony ran to "
        f"{uncapped[-1].t1}; the cap is truncating, not sampling"
    )


def test_testimony_can_be_scoped_to_a_window(db, scratch_seed, graphs):
    """An interview asks about a window, and gets claims about that window.

    This is what makes the cap harmless in practice: a detective asking about
    the incident window gets every claim bearing on it, not a sample.
    """
    from backend.app.agents.scripted import build_suspects
    from backend.app.case.graph import case_graph_name
    from backend.app.minds.access import mind_graph_name
    from backend.app.world.generator import world_graph_name

    seed = scratch_seed
    graphs(world_graph_name(seed))
    graphs(case_graph_name(seed))
    plan = plan_world(SEED)
    for person in plan.people:
        graphs(mind_graph_name(seed, person.id))
    generate(db, seed, spec=WorldSpec(plan_seed=SEED))

    window = (plan.incident.t0, plan.incident.t1)
    for suspect in build_suspects(db, seed, plan=plan):
        for claim in suspect.testify(window=window):
            assert overlaps(claim.t0, claim.t1, *window), (
                f"{suspect.id} answered about [{claim.t0},{claim.t1}) "
                f"when asked about {window}"
            )


def test_the_innocent_repeater_voices_what_it_was_told(db, scratch_seed, graphs):
    """The demo moment, asserted rather than hoped for.

    An honest suspect who received the culprit's fabrication must actually say
    it when asked about that window, and the audit must call it HEARSAY —
    grounded in a memory of being told, naming the source. The repeater is not
    deceiving anyone, and nothing in the verdict says they are.
    """
    from backend.app.agents.scripted import build_suspects
    from backend.app.audit.engine import AuditEngine
    from backend.app.case.graph import CaseGraph, case_graph_name
    from backend.app.minds.access import mind_graph_name
    from backend.app.world.generator import world_graph_name

    seed = scratch_seed
    graphs(world_graph_name(seed))
    graphs(case_graph_name(seed))
    plan = plan_world(SEED)
    for person in plan.people:
        graphs(mind_graph_name(seed, person.id))
    generate(db, seed, spec=WorldSpec(plan_seed=SEED))

    fab = plan.fabrications[0]
    by_id = {f.id: f for f in plan.facts}
    repeaters = {by_id[fid].owner for fid in fab.relayed_fact_ids}
    assert repeaters, "the fabrication was never relayed"

    case = CaseGraph(db, seed)
    engine = AuditEngine(db, seed)
    found = []
    for suspect in build_suspects(db, seed, plan=plan):
        if suspect.id not in repeaters:
            continue
        for n, claim in enumerate(suspect.testify(window=(fab.t0, fab.t1)), start=1):
            if claim.place != fab.place or claim.subject != fab.by_person:
                continue
            claim_id = f"{suspect.id}-rep{n}"
            case.ingest_claim(
                claim_id=claim_id, speaker=suspect.id, subject=claim.subject,
                place=claim.place, t0=claim.t0, t1=claim.t1, turn=n,
                modality=claim.modality, relayed_from=claim.relayed_from,
            )
            found.append(engine.audit_claim(claim_id))

    assert found, "the repeater never voiced the fabrication it was told"
    assert any(r.verdict == "HEARSAY" for r in found), (
        f"expected a HEARSAY verdict, got {[r.verdict for r in found]}"
    )
    hearsay = next(r for r in found if r.verdict == "HEARSAY")
    assert hearsay.hearsay_support[0]["heard_from"] == fab.by_person


def test_a_policy_change_changes_only_what_is_said(db, scratch_seed, graphs):
    """The policy is a real knob: the same memory yields different testimony.

    RETICENT withholds secondhand knowledge, so it says strictly less than
    HONEST from an identical mind — and never says anything HONEST would not.
    """
    from backend.app.agents.scripted import HONEST, RETICENT, build_suspects
    from backend.app.case.graph import case_graph_name
    from backend.app.minds.access import mind_graph_name
    from backend.app.world.generator import world_graph_name

    seed = scratch_seed
    graphs(world_graph_name(seed))
    graphs(case_graph_name(seed))
    plan = plan_world(SEED)
    for person in plan.people:
        graphs(mind_graph_name(seed, person.id))
    generate(db, seed, spec=WorldSpec(plan_seed=SEED))

    suspect = build_suspects(db, seed, plan=plan)[0]
    honest = set(suspect.with_policy(HONEST).testify(limit=None))
    reticent = set(suspect.with_policy(RETICENT).testify(limit=None))

    assert reticent < honest, "RETICENT must say strictly less than HONEST"
    assert all(c.relayed_from is None for c in reticent)
    assert any(c.relayed_from is not None for c in honest)


def test_a_withheld_window_leaves_a_gap_rather_than_a_conflict(db, scratch_seed, graphs):
    """An evasive suspect declines a window; nothing it says conflicts.

    Declining to account for a span is not deception and the audit does not
    treat it as such — the window simply goes unclaimed.
    """
    from backend.app.agents.scripted import build_suspects, evasive
    from backend.app.case.graph import case_graph_name
    from backend.app.minds.access import mind_graph_name
    from backend.app.world.generator import world_graph_name

    seed = scratch_seed
    graphs(world_graph_name(seed))
    graphs(case_graph_name(seed))
    plan = plan_world(SEED)
    for person in plan.people:
        graphs(mind_graph_name(seed, person.id))
    generate(db, seed, spec=WorldSpec(plan_seed=SEED))

    window = (plan.incident.t0, plan.incident.t1)
    suspect = build_suspects(db, seed, plan=plan)[0].with_policy(evasive(window))
    for claim in suspect.testify(limit=None):
        assert not overlaps(claim.t0, claim.t1, *window)


def test_claims_are_identical_across_two_independent_generations(db, scratch_seed, graphs):
    """The same world written into two separate graph sets yields the same claims.

    `test_testimony_is_deterministic` only re-reads one written world, so it
    could not catch order-dependence introduced by the *write* path — if
    `generate` wrote facts in a different order, ids would shift and testimony
    would diverge while that test stayed green. This regenerates from scratch
    into a different seed's graphs and compares the claims themselves.
    """
    from backend.app.agents.scripted import build_suspects
    from backend.app.case.graph import case_graph_name
    from backend.app.minds.access import mind_graph_name
    from backend.app.world.generator import world_graph_name

    plan = plan_world(SEED)

    def testimony(seed: int):
        graphs(world_graph_name(seed))
        graphs(case_graph_name(seed))
        for person in plan.people:
            graphs(mind_graph_name(seed, person.id))
        generate(db, seed, spec=WorldSpec(plan_seed=SEED))
        return [
            (s.id, s.testify(limit=None)) for s in build_suspects(db, seed, plan=plan)
        ]

    first = testimony(scratch_seed)
    second = testimony(scratch_seed + 700)

    assert first == second
    assert any(claims for _, claims in first), "nobody testified, so this proves nothing"
