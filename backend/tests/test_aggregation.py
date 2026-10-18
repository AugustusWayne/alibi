"""Q8, the suspect scoreboard, against a hand-built graph with known answers.

The counting rule, stated once and tested here:

  **A contradiction counts once per suspect who made either claim.**

`CONTRADICTS` is matched undirected, so the naive query counts every
contradiction twice — once from each endpoint. Both speakers in a pair carry
it, but neither carries it twice.

The scoreboard ranks suspects by how much of what they said is unaccounted
for. That is a measure of grounding, not of guilt: a suspect can top this
board because they were alone all evening.
"""

from __future__ import annotations

from backend.app.case.graph import CaseGraph, case_graph_name
from backend.app.case.scoreboard import SCORED_TERMS, load_weights, rank_suspects


def _case(db, seed, graphs) -> CaseGraph:
    graphs(case_graph_name(seed))
    case = CaseGraph(db, seed)
    for pid, name in [("kitchen", "Kitchen"), ("library", "Library"), ("hall", "Hall")]:
        case.upsert_place(pid, name)
    return case


def test_contradiction_counts_once_per_speaker_not_once_per_endpoint(db, scratch_seed, graphs):
    """s1 and s2 each make one claim about s3; the two claims conflict.

    One contradiction, two speakers. Each must show exactly 1, not 2.
    """
    case = _case(db, scratch_seed, graphs)
    case.ingest_claim(claim_id="c1", speaker="s1", subject="s3", place="kitchen",
                      t0=0, t1=15, turn=1, modality="THROUGHOUT")
    case.ingest_claim(claim_id="c2", speaker="s2", subject="s3", place="library",
                      t0=5, t1=20, turn=2, modality="THROUGHOUT")

    found = case.find_exclusive_presence()
    assert len(found) == 1, "one conflicting pair, found once (a.id < b.id)"

    rows = {r["suspect"]: r for r in case.scoreboard_rows()}
    assert rows["s1"]["other_contradictions"] == 1
    assert rows["s2"]["other_contradictions"] == 1
    assert rows["s1"]["self_contradictions"] == 0
    assert rows["s2"]["self_contradictions"] == 0
    # s3 is the subject of both claims but the speaker of neither.
    assert rows["s3"]["claims"] == 0
    assert rows["s3"]["other_contradictions"] == 0


def test_self_contradiction_is_counted_separately(db, scratch_seed, graphs):
    """The split this milestone adds to spec 5.12.

    s1 contradicts itself (c1 vs c2) and is also contradicted by s2 (c3 vs c4).
    Spec 5.12's anonymous match would report s1 with 2 contradictions and give
    no way to tell those two apart, scoring internal inconsistency the same as
    being disputed by someone else. Expected here:

      s1 -> claims=3, self=1, other=1
      s2 -> claims=1, self=0, other=1
    """
    case = _case(db, scratch_seed, graphs)
    # s1 puts itself in two places at once.
    case.ingest_claim(claim_id="c1", speaker="s1", subject="s1", place="kitchen",
                      t0=0, t1=15, turn=1, modality="THROUGHOUT")
    case.ingest_claim(claim_id="c2", speaker="s1", subject="s1", place="library",
                      t0=5, t1=20, turn=2, modality="THROUGHOUT")
    # s1 and s2 disagree about where s3 was.
    case.ingest_claim(claim_id="c3", speaker="s1", subject="s3", place="kitchen",
                      t0=100, t1=115, turn=3, modality="THROUGHOUT")
    case.ingest_claim(claim_id="c4", speaker="s2", subject="s3", place="library",
                      t0=105, t1=120, turn=4, modality="THROUGHOUT")

    case.find_exclusive_presence()

    rows = {r["suspect"]: r for r in case.scoreboard_rows()}
    assert (rows["s1"]["claims"], rows["s1"]["self_contradictions"],
            rows["s1"]["other_contradictions"]) == (3, 1, 1)
    assert (rows["s2"]["claims"], rows["s2"]["self_contradictions"],
            rows["s2"]["other_contradictions"]) == (1, 0, 1)


def test_gaps_are_counted_per_suspect(db, scratch_seed, graphs):
    """Gap nodes are counted by identity, so two identical spans count twice."""
    case = _case(db, scratch_seed, graphs)
    case.ingest_claim(claim_id="c1", speaker="s1", subject="s1", place="kitchen",
                      t0=0, t1=15, turn=1, modality="THROUGHOUT")
    case.ingest_claim(claim_id="c2", speaker="s1", subject="s1", place="kitchen",
                      t0=20, t1=35, turn=2, modality="THROUGHOUT")
    case.materialize_gap(claim_id="c1", g0=0, g1=5)
    case.materialize_gap(claim_id="c1", g0=10, g1=15)
    case.materialize_gap(claim_id="c2", g0=20, g1=25)

    rows = {r["suspect"]: r for r in case.scoreboard_rows()}
    assert rows["s1"]["gaps"] == 3
    assert rows["s1"]["claims"] == 2


def test_a_suspect_with_nothing_scores_zero(db, scratch_seed, graphs):
    """A suspect who made no claims appears with zeros, not missing.

    OPTIONAL MATCH plus collect(DISTINCT c.id) must yield an empty list, and
    size() of it must be 0 — not 1 from a collected null.
    """
    case = _case(db, scratch_seed, graphs)
    case.upsert_suspect("quiet", "Quiet")

    rows = {r["suspect"]: r for r in case.scoreboard_rows()}
    assert rows["quiet"] == {
        "suspect": "quiet", "claims": 0, "self_contradictions": 0,
        "other_contradictions": 0, "gaps": 0,
        "originated_ungrounded": 0, "carried_ungrounded": 0,
    }


def test_impossible_travel_contradiction_records_gap_and_need(db, scratch_seed, graphs):
    """Q6 over the precomputed matrix, with the shortfall recorded on the edge."""
    case = _case(db, scratch_seed, graphs)
    case.upsert_adjacency("kitchen", "hall", 4)
    case.upsert_adjacency("hall", "library", 5)
    written = case.build_travel_matrix(["kitchen", "hall", "library"])
    assert written == 6, "3 places -> 6 ordered pairs"
    assert case.travel_minutes("kitchen", "library") == 9, "4 + 5 via the hall"

    # Claimed in the kitchen until 20, then the library from 25. Nine needed,
    # five available.
    case.ingest_claim(claim_id="a", speaker="s1", subject="s1", place="kitchen",
                      t0=0, t1=20, turn=1, modality="THROUGHOUT")
    case.ingest_claim(claim_id="b", speaker="s1", subject="s1", place="library",
                      t0=25, t1=40, turn=2, modality="THROUGHOUT")

    found = case.find_impossible_travel()
    assert len(found) == 1
    assert found[0]["gap"] == 5
    assert found[0]["needed"] == 9

    rows = {r["suspect"]: r for r in case.scoreboard_rows()}
    assert rows["s1"]["self_contradictions"] == 1


def test_a_feasible_journey_is_not_flagged(db, scratch_seed, graphs):
    """Exactly enough time to walk is feasible. The boundary, on the graph."""
    case = _case(db, scratch_seed, graphs)
    case.upsert_adjacency("kitchen", "library", 5)
    case.build_travel_matrix(["kitchen", "library"])

    case.ingest_claim(claim_id="a", speaker="s1", subject="s1", place="kitchen",
                      t0=0, t1=10, turn=1, modality="THROUGHOUT")
    case.ingest_claim(claim_id="b", speaker="s1", subject="s1", place="library",
                      t0=15, t1=30, turn=2, modality="THROUGHOUT")

    assert case.find_impossible_travel() == []


def test_exclusive_presence_and_travel_partition_the_cases(db, scratch_seed, graphs):
    """No claim pair may be flagged by both checks (spec 4.0).

    Overlapping claims at different places are a two-places-at-once problem;
    non-overlapping ones are a travel problem. The two checks must not both
    fire on the same pair, or the scoreboard would double-count one fault.
    """
    case = _case(db, scratch_seed, graphs)
    case.upsert_adjacency("kitchen", "hall", 4)
    case.upsert_adjacency("hall", "library", 5)
    case.build_travel_matrix(["kitchen", "hall", "library"])

    # An overlapping pair, and a too-tight sequential pair.
    case.ingest_claim(claim_id="o1", speaker="s1", subject="s1", place="kitchen",
                      t0=0, t1=15, turn=1, modality="THROUGHOUT")
    case.ingest_claim(claim_id="o2", speaker="s1", subject="s1", place="library",
                      t0=5, t1=20, turn=2, modality="THROUGHOUT")
    case.ingest_claim(claim_id="t1", speaker="s2", subject="s2", place="kitchen",
                      t0=100, t1=120, turn=3, modality="THROUGHOUT")
    case.ingest_claim(claim_id="t2", speaker="s2", subject="s2", place="library",
                      t0=125, t1=140, turn=4, modality="THROUGHOUT")

    case.find_exclusive_presence()
    case.find_impossible_travel()

    by_pair: dict[frozenset[str], set[str]] = {}
    for row in case.contradictions():
        by_pair.setdefault(frozenset({row["a"], row["b"]}), set()).add(row["kind"])

    assert by_pair == {
        frozenset({"o1", "o2"}): {"exclusive_presence"},
        frozenset({"t1", "t2"}): {"impossible_travel"},
    }
    for pair, kinds in by_pair.items():
        assert len(kinds) == 1, f"{pair} flagged by both checks"


def test_corroboration_requires_two_different_speakers(db, scratch_seed, graphs):
    """Q7. One speaker agreeing with themselves is not corroboration."""
    case = _case(db, scratch_seed, graphs)
    case.ingest_claim(claim_id="c1", speaker="s1", subject="s3", place="kitchen",
                      t0=0, t1=15, turn=1, modality="THROUGHOUT")
    case.ingest_claim(claim_id="c2", speaker="s2", subject="s3", place="kitchen",
                      t0=10, t1=25, turn=2, modality="THROUGHOUT")
    case.ingest_claim(claim_id="c3", speaker="s1", subject="s3", place="kitchen",
                      t0=12, t1=18, turn=3, modality="THROUGHOUT")

    found = {(r["a"], r["b"]) for r in case.find_corroboration()}
    assert found == {("c1", "c2"), ("c2", "c3")}, "s1 with itself (c1,c3) must not appear"


# -- the ranking function ----------------------------------------------------


def test_ranking_weights_self_contradiction_above_being_disputed():
    """Internal inconsistency is the stronger signal, so it weighs more.

    Same claim count, same gap count; one suspect contradicts themselves and
    the other is contradicted by someone else. The first must rank higher.
    """
    ranked = rank_suspects([
        {"suspect": "disputed", "claims": 3, "self_contradictions": 0,
         "other_contradictions": 1, "gaps": 0,
         "originated_ungrounded": 0, "carried_ungrounded": 0},
        {"suspect": "inconsistent", "claims": 3, "self_contradictions": 1,
         "other_contradictions": 0, "gaps": 0,
         "originated_ungrounded": 0, "carried_ungrounded": 0},
    ])
    assert [r["suspect"] for r in ranked] == ["inconsistent", "disputed"]
    assert ranked[0]["score"] > ranked[1]["score"]


def test_ranking_exposes_the_breakdown_not_just_a_total():
    """The UI shows how a score was reached, so every term is reported."""
    ranked = rank_suspects([
        {"suspect": "s1", "claims": 4, "self_contradictions": 1,
         "other_contradictions": 2, "gaps": 3,
         "originated_ungrounded": 1, "carried_ungrounded": 4},
    ])
    row = ranked[0]
    w = load_weights()
    assert row["breakdown"] == {
        "originated_ungrounded": 1 * w["originated_ungrounded"],
        "self_contradictions": 1 * w["self_contradictions"],
        "other_contradictions": 2 * w["other_contradictions"],
        "gaps": 3 * w["gaps"],
        "carried_ungrounded": 4 * w["carried_ungrounded"],
    }
    assert row["score"] == sum(row["breakdown"].values())
    assert set(row["breakdown"]) == set(SCORED_TERMS), "every term is reported"


def test_ranking_is_stable_for_equal_scores():
    """Ties break on suspect id, so the board never reorders between runs."""
    rows = [
        {"suspect": "s3", "claims": 1, "self_contradictions": 0,
         "other_contradictions": 0, "gaps": 0,
         "originated_ungrounded": 0, "carried_ungrounded": 0},
        {"suspect": "s1", "claims": 1, "self_contradictions": 0,
         "other_contradictions": 0, "gaps": 0,
         "originated_ungrounded": 0, "carried_ungrounded": 0},
        {"suspect": "s2", "claims": 1, "self_contradictions": 0,
         "other_contradictions": 0, "gaps": 0,
         "originated_ungrounded": 0, "carried_ungrounded": 0},
    ]
    assert [r["suspect"] for r in rank_suspects(rows)] == ["s1", "s2", "s3"]
    assert [r["suspect"] for r in rank_suspects(list(reversed(rows)))] == ["s1", "s2", "s3"]
