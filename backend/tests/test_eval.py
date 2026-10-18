"""The eval harness (spec section 8): its answer key, its arithmetic, its rules.

Three kinds of test here, and they are deliberately different in character.

`metrics.py` is pure, so it is tested against hand-written records where the
right answer is countable by eye. That is the point of keeping it pure: a
figure that can only be checked by running 24 seeds is a figure nobody checks.

`PlanTruth` is the answer key, and an answer key cannot be tested against the
thing it scores. So it is tested against the generator's own records and
against the graph-backed `GroundTruth` reader, on seed 7777 — the development
seed, which `test_provenance.py` already uses for exactly this comparison and
which is kept out of `eval/seeds.json` for that reason.

The last group are the repo's own rules as tests: the matrix dimensions are the
spec's enums and not a number anyone typed, the frozen seed list stays disjoint
from the development and test seeds, the eval writes no `TRACED_TO`, and the
scoring vocabulary does not escape `referee/`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from backend.app.audit.verdicts import (
    ALL_VERDICTS,
    CONTRADICTED,
    HEARSAY,
    INDETERMINATE,
    SUPPORTED,
    THROUGHOUT,
    UNSUPPORTED,
)
from backend.app.case.graph import CaseGraph, case_graph_name
from backend.app.eval import metrics as m
from backend.app.eval.harness import run_seed
from backend.app.eval.seeds import DEVELOPMENT_SEED, TEST_SEED_FLOOR, load_seeds
from backend.app.minds.access import mind_graph_name
from backend.app.referee.ground_truth import (
    ALL_LABELS,
    DELIBERATE_FABRICATION,
    FALSE_LABELS,
    HONEST_ERROR,
    RELAYED_FALSEHOOD,
    TRUE_CLAIM,
    GapTruth,
    GroundTruth,
    PlanTruth,
)
from backend.app.referee.terminals import ORIGIN_TERMINALS, ORIGIN_UNSUPPORTED
from backend.app.world.generator import WorldSpec, plan_world, world_graph_name

SEED = 7777
"""The development seed. Inspected at length, so it is not in the eval set."""


# -- the dimensions come from the spec, not from this file -------------------


def test_the_matrix_is_five_verdicts_by_four_labels():
    """Spec 5.5 lists five verdicts; spec 8.1 lists four labels.

    Asserted against the enums rather than against literals written here, so a
    sixth verdict or a fifth label breaks this test instead of quietly
    producing a matrix with a row the report does not print.
    """
    assert ALL_VERDICTS == (SUPPORTED, UNSUPPORTED, CONTRADICTED, INDETERMINATE, HEARSAY)
    assert ALL_LABELS == (
        TRUE_CLAIM,
        DELIBERATE_FABRICATION,
        RELAYED_FALSEHOOD,
        HONEST_ERROR,
    )
    assert len(ALL_VERDICTS) == 5
    assert len(ALL_LABELS) == 4
    assert TRUE_CLAIM not in FALSE_LABELS
    assert set(FALSE_LABELS) | {TRUE_CLAIM} == set(ALL_LABELS)


# -- metrics, over records countable by eye ----------------------------------


@dataclass(frozen=True)
class Rec:
    """The subset of `ClaimRecord` the metrics actually read."""

    verdict: str = SUPPORTED
    label: str = TRUE_CLAIM
    witnessed_backing: bool = True
    witnessed_conflict: bool = False
    any_overlapping_memory: bool = True
    truth_origin: str | None = None
    truth_chain_root: str | None = None
    chain_terminal: str | None = None
    chain_origin: str | None = None


def test_the_confusion_matrix_keeps_every_row_even_at_zero():
    c = m.confusion([Rec(), Rec(), Rec(verdict=CONTRADICTED, label=HONEST_ERROR)])

    assert c.total == 3
    assert c.cells[(SUPPORTED, TRUE_CLAIM)] == 2
    assert c.cells[(CONTRADICTED, HONEST_ERROR)] == 1
    # A verdict that never arose keeps its row, at zero. An absent row and a
    # zero row mean different things and the reader must be able to tell.
    assert c.cells[(UNSUPPORTED, TRUE_CLAIM)] == 0
    assert len(c.cells) == len(ALL_VERDICTS) * len(ALL_LABELS)
    assert c.row_total(SUPPORTED) == 2
    assert c.column_total(HONEST_ERROR) == 1
    assert sum(c.row_total(v) for v in ALL_VERDICTS) == c.total


def test_a_verdict_outside_the_enum_raises_rather_than_growing_the_matrix():
    """The dimensions are the spec's. An unknown pair is a contract break."""
    with pytest.raises(ValueError, match="outside the declared enums"):
        m.confusion([Rec(verdict="PROBABLY_FINE")])


def test_grounding_and_falsehood_are_scored_against_different_truths():
    """The same engine signal, two questions — and that is the whole result.

    One claim is grounded in the speaker's own memory and false anyway. The
    engine says SUPPORTED, which is correct about grounding and silent about
    truth. Grounding scores it a true negative; falsehood scores it a miss.
    """
    records = [
        # grounded and true: both questions get a true negative.
        Rec(verdict=SUPPORTED, label=TRUE_CLAIM, witnessed_backing=True),
        # grounded but false: the memory backs it, the world does not.
        Rec(verdict=SUPPORTED, label=HONEST_ERROR, witnessed_backing=True),
        # ungrounded and false: both questions get a true positive.
        Rec(verdict=CONTRADICTED, label=DELIBERATE_FABRICATION, witnessed_backing=False),
    ]
    grounding = m.grounding_pr(records)
    falsehood = m.falsehood_pr(records)

    assert (grounding.tp, grounding.fp, grounding.fn, grounding.tn) == (1, 0, 0, 2)
    assert grounding.precision == 1.0
    assert grounding.recall == 1.0

    assert (falsehood.tp, falsehood.fp, falsehood.fn, falsehood.tn) == (1, 0, 1, 1)
    assert falsehood.precision == 1.0
    assert falsehood.recall == 0.5

    # The gap between the two recalls is the "grounded is not true" finding.
    assert falsehood.recall < grounding.recall


def test_precision_is_undefined_not_zero_when_nothing_was_predicted():
    pr = m.falsehood_pr([Rec(verdict=SUPPORTED, label=TRUE_CLAIM)])
    assert pr.tp == 0 and pr.fp == 0
    assert pr.precision is None
    assert pr.f1 is None


def test_chain_broken_is_reported_beside_origin_accuracy_and_never_inside_it():
    """Spec 5.7 calls CHAIN_BROKEN ambiguous and not an origin.

    So a broken chain is not scored as having named the wrong agent: it did not
    name one. It leaves the resolved denominator and shows up in its own rate.
    """
    records = [
        Rec(truth_origin="p4", chain_terminal=ORIGIN_UNSUPPORTED, chain_origin="p4"),
        Rec(truth_origin="p4", chain_terminal=ORIGIN_UNSUPPORTED, chain_origin="p2"),
        Rec(truth_origin="p4", chain_terminal="CHAIN_BROKEN", chain_origin=None),
        Rec(truth_origin="p4", chain_terminal="CHAIN_TEMPORAL_VIOLATION", chain_origin=None),
        # No ground-truth origin: outside the subset entirely.
        Rec(truth_origin=None, chain_terminal="ORIGIN_WITNESSED", chain_origin="p1"),
    ]
    o = m.origin_accuracy(records)

    assert o.subset == 4
    assert o.resolved == 2
    assert o.correct == 1
    assert o.misnamed == 1
    assert o.unresolved == 2
    assert o.accuracy_over_resolved == 0.5
    assert o.accuracy_over_subset == 0.25
    # Rates are over every chain in the run, including the one outside the subset.
    assert o.chains_total == 5
    assert o.chain_broken == 1
    assert o.chain_temporal_violation == 1
    assert o.chain_broken_rate == 1 / 5


def test_a_claim_the_engine_never_traced_is_not_counted_as_a_wrong_answer():
    o = m.origin_accuracy([Rec(truth_origin="p4", chain_terminal=None)])
    assert o.subset == 0
    assert o.chains_total == 0
    assert o.accuracy_over_resolved is None


def test_gap_precision_separates_elsewhere_from_in_transit():
    """Three outcomes, kept apart: which one is a hit depends on the question."""

    @dataclass(frozen=True)
    class G:
        truth: str

    g = m.gap_precision(
        [
            G(GapTruth.ELSEWHERE),
            G(GapTruth.ELSEWHERE),
            G(GapTruth.IN_TRANSIT),
            G(GapTruth.AT_CLAIMED_PLACE),
        ]
    )
    assert (g.total, g.elsewhere, g.in_transit, g.at_claimed_place) == (4, 2, 1, 1)
    assert g.strict == 0.5
    assert g.loose == 0.75


def test_backing_by_verdict_shows_where_grounding_recall_goes():
    rows = m.backing_by_verdict(
        [
            Rec(verdict=HEARSAY, witnessed_backing=False),
            Rec(verdict=INDETERMINATE, witnessed_backing=False),
            Rec(verdict=SUPPORTED, witnessed_backing=True),
        ]
    )
    assert rows[HEARSAY] == (0, 1)
    assert rows[INDETERMINATE] == (0, 1)
    assert rows[SUPPORTED] == (1, 0)
    assert rows[UNSUPPORTED] == (0, 0)


def test_the_generator_rejection_rate_is_reported_as_zero_not_omitted():
    """Spec 8.4.2 asks for the rate. Zero explained is data; absent is not."""

    @dataclass(frozen=True)
    class R:
        seed: int
        rejected: int = 0
        fabrications: int = 1
        relayed_fabrications: int = 1

    y = m.generator_yield([R(seed=1), R(seed=2, relayed_fabrications=0)])
    assert y.seeds == 2
    assert y.rejected == 0
    assert y.rejection_rate == 0.0
    assert y.without_relayed_fabrication == 1
    assert y.seeds_without_relay == (2,)
    assert y.unrelayed_rate == 0.5


# -- the frozen seed list ----------------------------------------------------


def test_the_frozen_seeds_avoid_the_development_and_test_seeds():
    """Spec 8.4.3: the evaluation set is disjoint from what has been looked at."""
    seeds = load_seeds()
    assert 20 <= len(seeds) <= 30
    assert len(set(seeds)) == len(seeds)
    assert DEVELOPMENT_SEED not in seeds
    assert all(s < TEST_SEED_FLOOR for s in seeds)


def test_the_seed_file_records_the_rule_it_was_generated_by():
    """Rule-generated, so there is nothing to cherry-pick — and it is checkable."""
    doc = json.loads(Path("eval/seeds.json").read_text())
    assert doc["_rule"] == "10000 + 37k for k = 1..24"
    assert doc["seeds"] == [10_000 + 37 * k for k in range(1, 25)]
    assert doc["_development_seed"] == DEVELOPMENT_SEED


def test_a_seed_list_containing_the_development_seed_is_refused(tmp_path):
    """Raises rather than filtering: a bad freeze must not change a denominator."""
    path = tmp_path / "seeds.json"
    path.write_text(json.dumps({"seeds": [1, 2, DEVELOPMENT_SEED]}))
    with pytest.raises(ValueError, match="cannot be part of a blind evaluation set"):
        load_seeds(path)


def test_a_seed_list_with_duplicates_is_refused(tmp_path):
    path = tmp_path / "seeds.json"
    path.write_text(json.dumps({"seeds": [5, 5, 6]}))
    with pytest.raises(ValueError, match="duplicate seeds"):
        load_seeds(path)


# -- the answer key, against the generator's own records ---------------------


@pytest.fixture
def plan():
    return plan_world(SEED, WorldSpec(plant_broken_chain=True, plant_temporal_violation=True))


def test_the_planted_claim_is_labelled_a_deliberate_fabrication(plan):
    """The culprit voicing its own planted alibi, labelled from the plan alone."""
    truth = PlanTruth(plan)
    fab = next(f for f in plan.fabrications if f.pathology == "none")

    labelled = truth.label_claim(
        {
            "speaker": fab.by_person,
            "subject": fab.by_person,
            "place": fab.place,
            "t0": fab.t0,
            "t1": fab.t1,
            "modality": THROUGHOUT,
        }
    )
    assert labelled.label == DELIBERATE_FABRICATION
    assert labelled.true_of_world is False
    assert labelled.origin_agent == fab.by_person
    assert fab.by_person == truth.culprit()


def test_the_repeater_is_labelled_a_relayed_falsehood_with_the_right_origin(plan):
    """The innocent repeater's claim is false, and the plan names where it began.

    The label is about the provenance of the falsehood, not about the repeater:
    their memory genuinely holds what they were told. The origin it names is
    read out of the plan, independently of the referee's chain walk, so the
    origin-identification metric is not scoring the walk against itself.
    """
    truth = PlanTruth(plan)
    fab = next(f for f in plan.fabrications if f.pathology == "none")
    by_id = {f.id: f for f in plan.facts}
    repeater = by_id[fab.relayed_fact_ids[0]].owner

    labelled = truth.label_claim(
        {
            "speaker": repeater,
            "subject": fab.by_person,
            "place": fab.place,
            "t0": fab.t0,
            "t1": fab.t1,
            "modality": THROUGHOUT,
        }
    )
    assert labelled.label == RELAYED_FALSEHOOD
    assert labelled.origin_agent == fab.by_person
    assert labelled.witnessed_backing is False
    assert repeater != fab.by_person


def test_a_claim_matching_the_true_route_is_labelled_true(plan):
    """Labelled from the subject's own presence, at the strength asserted."""
    truth = PlanTruth(plan)
    presence = plan.presences[0]

    labelled = truth.label_claim(
        {
            "speaker": presence.person,
            "subject": presence.person,
            "place": presence.place,
            "t0": presence.t0,
            "t1": presence.t1,
            "modality": THROUGHOUT,
        }
    )
    assert labelled.label == TRUE_CLAIM
    assert labelled.true_of_world is True


def test_a_throughout_claim_wider_than_the_true_presence_is_not_true(plan):
    """Half-open and strict: one minute past the route is already false.

    The `merge_adjacent` case, which is where HONEST_ERROR comes from. Asserting
    THROUGHOUT over a span the subject only partly occupied does not match the
    world, and the label says so without implying anyone meant it.
    """
    truth = PlanTruth(plan)
    presence = next(p for p in plan.presences if p.t1 - p.t0 > 3)

    assert truth.true_of_world(
        subject=presence.person, place=presence.place,
        t0=presence.t0, t1=presence.t1, modality=THROUGHOUT,
    )
    assert not truth.true_of_world(
        subject=presence.person, place=presence.place,
        t0=presence.t0, t1=presence.t1 + 1, modality=THROUGHOUT,
    )
    # AT_SOME_POINT is satisfied by the same overrun, which is what the
    # modality means.
    assert truth.true_of_world(
        subject=presence.person, place=presence.place,
        t0=presence.t0, t1=presence.t1 + 1, modality="AT_SOME_POINT",
    )


def test_a_gap_the_subject_spent_elsewhere_is_distinguished_from_one_in_transit(plan):
    """The three gap outcomes, each read off the subject's true route."""
    truth = PlanTruth(plan)
    first = plan.presences[0]
    second = next(p for p in plan.presences if p.person == first.person and p.t0 > first.t1)

    inside = truth.label_gap(
        subject=first.person, place=first.place, t0=first.t0, t1=first.t1
    )
    assert inside.verdict == GapTruth.AT_CLAIMED_PLACE

    at_other_room = truth.label_gap(
        subject=first.person, place=first.place, t0=second.t0, t1=second.t1
    )
    assert at_other_room.verdict == GapTruth.ELSEWHERE


# -- the answer key against the graph-backed reader --------------------------


@pytest.fixture
def world(db, scratch_seed, graphs):
    """Seed 7777's world, written into a scratch seed's graphs."""
    spec = WorldSpec(plan_seed=SEED, plant_broken_chain=True, plant_temporal_violation=True)
    seed = scratch_seed
    graphs(world_graph_name(seed))
    graphs(case_graph_name(seed))
    for person in plan_world(SEED, spec).people:
        graphs(mind_graph_name(seed, person.id))
    return seed, spec


def test_the_plan_answer_key_agrees_with_the_graph_one(db, world):
    """Two readings of the same answer key must name the same culprit.

    `PlanTruth` reads the generator's plan; `GroundTruth` reads `world:{seed}`
    after it was written. A disagreement would mean the write path altered the
    world, and every label in an eval run would be suspect — so the harness
    checks this on every seed, and this test checks the check.
    """
    seed, spec = world
    run = run_seed(db, seed, spec=spec, drop=False)

    assert run.culprit == GroundTruth(db, seed).culprit()
    assert run.culprit == PlanTruth(plan_world(SEED, spec)).culprit()


def test_a_run_labels_every_claim_and_stays_inside_both_enums(db, world):
    seed, spec = world
    run = run_seed(db, seed, spec=spec, drop=False)

    assert run.claim_count > 0
    assert all(c.verdict in ALL_VERDICTS for c in run.claims)
    assert all(c.label in ALL_LABELS for c in run.claims)
    # The matrix is buildable, which is the contract metrics.confusion enforces.
    assert m.confusion(list(run.claims)).total == run.claim_count


def test_the_eval_writes_no_trace_into_the_case_graph(db, world):
    """The eval is not the detective, and must not spend its budget for it.

    `TRACED_TO` exists exactly where a polygraph was spent. An eval run that
    materialized the referee's conclusions would put the answer into a case
    graph nobody asked, and leave spec 8.3's graph-versus-transcript arm
    measuring who was handed it. So the chains are scored from the `Chain`
    objects in memory and the case graph keeps none of them.
    """
    seed, spec = world
    run = run_seed(db, seed, spec=spec, drop=False)

    assert run.chains > 0, "this world must produce chains for the assertion to mean anything"
    assert CaseGraph(db, seed).traces() == []


def test_a_run_scores_the_chains_it_traced(db, world):
    """Every traced chain ends in one of the seven states, and origins resolve."""
    seed, spec = world
    run = run_seed(db, seed, spec=spec, drop=False)

    traced = [c for c in run.claims if c.chain_terminal is not None]
    assert len(traced) == run.chains
    assert all(c.chain_origin is None for c in traced if c.chain_terminal
               not in ORIGIN_TERMINALS)

    o = m.origin_accuracy(list(run.claims))
    assert o.chains_total == run.chains
    assert o.subset <= o.chains_total


def test_dropping_a_seed_leaves_nothing_behind(db, scratch_seed, graphs):
    """24 seeds is 216 graphs on a server other sessions share."""
    seed = scratch_seed
    spec = WorldSpec(plan_seed=SEED)
    for person in plan_world(SEED, spec).people:
        graphs(mind_graph_name(seed, person.id))
    graphs(world_graph_name(seed))
    graphs(case_graph_name(seed))

    run_seed(db, seed, spec=spec, drop=True)
    live = set(db.list_graphs())
    assert world_graph_name(seed) not in live
    assert case_graph_name(seed) not in live


# -- the project rules, rule 2, as a test ------------------------------------


SHIPPED_SUFFIXES = (
    ".py",
    ".json",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".css",
    ".html",
    ".sql",
    ".txt",
    ".yaml",
    ".yml",
)
"""File types this repo ships code or data in.

An allow-list rather than "everything that is not binary", so a new kind of
file is not silently exempted the day it is added."""

VOCABULARY_ROOTS = (Path("backend/app"), Path("scripts"), Path("frontend/src"))
"""Where shipped code and data live. `frontend/src` is scanned when the branch
has it; the backend branches do not, and a missing root is not a pass."""

VOCABULARY_EXCEPTIONS = (
    Path("backend/app/referee"),
    Path("backend/app/agents/intent_vocabulary.json"),
)
"""The only two places the vocabulary may appear, and why each one may.

`referee/` is scoring: spec 8.1's labels are computed there and rule 2 permits
them there and nowhere else. `intent_vocabulary.json` is the opposite case —
it lists the words so that `agents/loop.py` can refuse to publish any of them
in an accusation's rationale. Defining a word in order to forbid it is not the
thing rule 2 prohibits, and the guard cannot work without the list.

Nothing else is exempt. In particular this is a path list, not a suffix list:
a second JSON file carrying the vocabulary would fail, which is the point.
"""

VOCABULARY_DOCS_NOTE = """Markdown is deliberately not scanned. `ALIBI_SPEC.md`
says "never the word 'lie'", and the brief, the rules and this repo's progress
notes all have to discuss the rule in order to state it. Scanning prose would
fail on text that is correct."""


def test_the_scoring_vocabulary_does_not_escape_the_referee_package():
    """Deception vocabulary lives only in `backend/app/referee/` (rule 2).

    The eval reports a label *computed* in the referee package and may name
    it, but nothing else the repo ships may define that vocabulary or call a
    claim a lie. This checks the four words rule 2 names, on word boundaries,
    so "believe" does not trip on "lie".

    **Every shipped code and data file, not only Python.** The earlier form of
    this test globbed `*.py`, which left a JSON, a stylesheet or a `.tsx`
    component free to carry the words. That was theoretical until M4 added
    `intent_vocabulary.json`; it is a precedent now, so the scan follows the
    files rather than one language, and the two places the vocabulary is
    allowed are named paths rather than a pattern anything could match.
    """
    forbidden = re.compile(r"\b(lie|lies|liar|liars|lying|deception|deceptive)\b", re.I)
    offenders = []
    scanned = 0
    for root in VOCABULARY_ROOTS:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix not in SHIPPED_SUFFIXES:
                continue
            if any(path == e or e in path.parents for e in VOCABULARY_EXCEPTIONS):
                continue
            scanned += 1
            for n, line in enumerate(path.read_text().splitlines(), start=1):
                if forbidden.search(line):
                    offenders.append(f"{path}:{n}: {line.strip()}")
    assert scanned > 0, f"scanned nothing; {VOCABULARY_ROOTS} found no shipped files"
    assert not offenders, "deception vocabulary outside referee/:\n" + "\n".join(offenders)


def test_the_vocabulary_scan_covers_more_than_python():
    """The guard above is only worth its name if a data file would fail it.

    Written because the previous form of the test passed a JSON file silently.
    This asserts the scan's reach directly rather than trusting the glob.
    """
    assert ".json" in SHIPPED_SUFFIXES
    assert {".ts", ".tsx", ".css", ".html"} <= set(SHIPPED_SUFFIXES)
    assert ".md" not in SHIPPED_SUFFIXES, VOCABULARY_DOCS_NOTE


def test_only_two_paths_may_hold_the_vocabulary():
    """Both exceptions are named paths, so neither can widen by accident."""
    assert VOCABULARY_EXCEPTIONS == (
        Path("backend/app/referee"),
        Path("backend/app/agents/intent_vocabulary.json"),
    )
    assert Path("backend/app/agents/intent_vocabulary.json").exists()


def test_the_eval_package_contains_no_inline_cypher():
    """All Cypher lives in `**/queries.py` (project rules); the eval adds none.

    It scores through the existing readers, so there is nothing to put in a
    queries.py — and this asserts it stayed that way rather than growing a
    query in a harness where no comment would state what it answers.
    """
    cypher = re.compile(r"\b(MATCH|MERGE|CREATE|RETURN|OPTIONAL MATCH)\b")
    for path in sorted(Path("backend/app/eval").rglob("*.py")):
        hits = [
            line.strip()
            for line in path.read_text().splitlines()
            if cypher.search(line) and "queries" not in line
        ]
        assert not hits, f"inline Cypher in {path}: {hits}"


def test_running_a_seed_twice_gives_the_same_case_not_a_doubled_one(db, scratch_seed, graphs):
    """A seed's graphs are cleared before the run, not only after it.

    `CREATE_PRESENCE` and `ingest_claim` append. Generating into graphs that
    already hold a world ingests and audits every claim a second time, and the
    report's counts are then wrong by a factor that looks entirely plausible.
    These graphs are keyed by seed on a server shared between checkouts, so an
    inherited `case:{seed}` is an ordinary occurrence — this caught a doubled
    development-seed run the first time the harness was used.
    """
    seed = scratch_seed
    spec = WorldSpec(plan_seed=SEED)
    for person in plan_world(SEED, spec).people:
        graphs(mind_graph_name(seed, person.id))
    graphs(world_graph_name(seed))
    graphs(case_graph_name(seed))

    first = run_seed(db, seed, spec=spec, drop=False)
    second = run_seed(db, seed, spec=spec, drop=False)

    assert second.claim_count == first.claim_count
    assert [c.claim_id for c in second.claims] == [c.claim_id for c in first.claims]
    assert [c.verdict for c in second.claims] == [c.verdict for c in first.claims]
    assert len(second.gaps) == len(first.gaps)
    assert second.chains == first.chains
    # And the claim ids are unique, which a doubled case would break.
    ids = [c.claim_id for c in first.claims]
    assert len(ids) == len(set(ids))


def test_the_answer_key_takes_hearsay_in_the_order_the_referee_does(plan):
    """A claim can rest on several secondhand memories with different origins.

    `trace_claim` walks the first in `(t0, id)` order, so the answer key must
    name the root of that one. Sorting them any other way names the root of a
    chain the referee did not follow, and the origin metric then counts a
    disagreement between two answers that are each right about a different
    chain. That is what it did on seed 10074 before the two orderings were
    tied together, and this pins them together.
    """
    truth = PlanTruth(plan)
    support = truth._hearsay_support(
        speaker="p1", subject="p1", place="hall", t0=0, t1=300
    )
    assert [f.id for f in support] == [
        f.id for f in sorted(support, key=lambda f: (f.t0, f.id))
    ]


def test_a_claim_with_several_chains_is_counted_as_such(db, world):
    """The engine traces the first chain; the report says how often there are more."""
    seed, spec = world
    run = run_seed(db, seed, spec=spec, drop=False)

    multi = m.multi_chain_claims(list(run.claims))
    assert multi == sum(1 for c in run.claims if c.truth_hearsay_entries > 1)
    # Every traced claim rests on at least one secondhand memory.
    traced = [c for c in run.claims if c.chain_terminal is not None]
    assert all(c.truth_hearsay_entries >= 1 for c in traced)


def test_grounding_is_scored_against_what_the_two_verdicts_actually_mean():
    """UNSUPPORTED means nothing overlapping; CONTRADICTED means refuted.

    Neither means "memory covered this only partly" — spec 5.5 routes that to
    INDETERMINATE. So a partially-covered claim is not in this metric's
    denominator, and a metric that put it there would be scoring the engine
    against a signal it is specified not to emit.
    """
    partly_covered = Rec(
        verdict=INDETERMINATE,
        witnessed_backing=False,      # memory does not FULLY cover it
        witnessed_conflict=False,     # but nothing refutes it
        any_overlapping_memory=True,  # and something does bear on it
    )
    nothing_at_all = Rec(
        verdict=UNSUPPORTED,
        witnessed_backing=False,
        witnessed_conflict=False,
        any_overlapping_memory=False,
    )
    refuted = Rec(
        verdict=CONTRADICTED,
        witnessed_backing=False,
        witnessed_conflict=True,
        any_overlapping_memory=True,
    )
    grounded = Rec(verdict=SUPPORTED)

    g = m.strict_grounding_pr([partly_covered, nothing_at_all, refuted, grounded])
    assert (g.tp, g.fp, g.fn, g.tn) == (2, 0, 0, 2)
    assert g.precision == 1.0
    assert g.recall == 1.0

    # The stricter question counts the partially-covered claim as a miss, which
    # is the design decision, not an error.
    f = m.grounding_pr([partly_covered, nothing_at_all, refuted, grounded])
    assert (f.tp, f.fp, f.fn, f.tn) == (2, 0, 1, 1)
    assert f.recall < g.recall


def test_the_answer_key_separates_nothing_found_from_partial_coverage(plan):
    """`any_overlapping_memory` is every source and every place, per spec 5.5."""
    truth = PlanTruth(plan)
    presence = plan.presences[0]

    # The speaker's own route segment: they hold witnessed memory of it.
    assert truth.any_overlapping_memory(
        speaker=presence.person, subject=presence.person,
        t0=presence.t0, t1=presence.t1,
    )
    assert not truth.witnessed_conflict(
        speaker=presence.person, subject=presence.person, place=presence.place,
        t0=presence.t0, t1=presence.t1,
    )
    # The same window, claimed for a different room, is refuted by that memory.
    other = next(p.id for p in plan.places if p.id != presence.place)
    assert truth.witnessed_conflict(
        speaker=presence.person, subject=presence.person, place=other,
        t0=presence.t0, t1=presence.t1,
    )
