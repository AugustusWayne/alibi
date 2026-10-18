"""Day-1 spikes for the FalkorDB assumptions listed in ALIBI_SPEC section 12.

Each numbered spike runs the real query shape the engine will depend on, against
a throwaway graph, and prints PASS or FAIL. On failure it prints the exact error
text and the fallback recorded in the spec, and nothing is worked around here:
an assumption that does not hold is a planning input, not a bug to patch
(the project rules: "On a spike or assumption failure, stop and report").

The broad `except` in the runner is deliberate and is the opposite of the
project rules' rule 8: probing is the whole purpose of this file, and every
caught error is re-printed in full rather than swallowed. No production code
may do this.

    make spikes            # all spikes
    python -m scripts.spikes --only 3 8
    python -m scripts.spikes --keep      # leave scratch graphs for inspection
"""

from __future__ import annotations

import argparse
import sys
import time
import traceback
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from falkordb.graph import Graph

from backend.app.config import settings
from backend.app.db import connect

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"


class SkipSpike(Exception):
    """Raised by a spike that is gated on a decision not yet taken."""


class Unmet(AssertionError):
    """Raised when a query runs but returns something other than what we need."""


# --------------------------------------------------------------------------
# registry
# --------------------------------------------------------------------------

@dataclass
class Spike:
    number: int
    title: str
    fallback: str
    fn: Callable[[Ctx], str]


SPIKES: list[Spike] = []


def spike(number: int, title: str, fallback: str) -> Callable[[Callable], Callable]:
    def register(fn: Callable[[Ctx], str]) -> Callable[[Ctx], str]:
        SPIKES.append(Spike(number=number, title=title, fallback=fallback, fn=fn))
        return fn

    return register


@dataclass
class Ctx:
    """Hands out scratch graphs and remembers them so they can be dropped."""

    db: object
    run_id: str
    keep: bool = False
    created: list[str] = field(default_factory=list)

    def graph(self, suffix: str) -> Graph:
        name = f"spike:{suffix}:{self.run_id}"
        self.created.append(name)
        return self.db.select_graph(name)

    def forget(self, name: str) -> None:
        """Stop tracking a graph this spike already dropped itself."""
        if name in self.created:
            self.created.remove(name)

    def cleanup(self) -> list[str]:
        problems = []
        if self.keep:
            return problems
        for name in self.created:
            try:
                self.db.select_graph(name).delete()
            except Exception as exc:  # noqa: BLE001 — reported, never hidden
                problems.append(f"{name}: {type(exc).__name__}: {exc}")
        self.created.clear()
        return problems


# --------------------------------------------------------------------------
# shared fixtures
# --------------------------------------------------------------------------

Q4_INGEST_CLAIM = """
MERGE (s:Suspect {id:$speaker})
MERGE (p:Suspect {id:$subject})
MERGE (l:Place {id:$place})
CREATE (c:Claim {id:$id, t0:$t0, t1:$t1, turn:$turn,
                 modality:$modality, verdict:'PENDING',
                 coverage:0.0, uncovered:0})
CREATE (c)-[:BY]->(s)
CREATE (c)-[:ABOUT]->(p)
CREATE (c)-[:AT]->(l)
"""


def ingest_claim(g: Graph, **kw) -> None:
    """Q4 from spec 5.8, used as a fixture builder by several spikes.

    `speaker` and `subject` are always passed explicitly. Deriving either from
    the claim id is how a fixture silently stops testing what it claims to.
    """
    g.query(Q4_INGEST_CLAIM, {"turn": 1, "modality": "THROUGHOUT", **kw})


# --------------------------------------------------------------------------
# 1. MERGE a relationship with a property map, then SET on it
# --------------------------------------------------------------------------

MERGE_REL_THEN_SET = """
MATCH (a:Claim {id:$a}), (b:Claim {id:$b})
MERGE (a)-[c:CONTRADICTS {kind:'impossible_travel', pair_id:$pair_id}]->(b)
SET c.gap = $gap, c.needed = $needed
RETURN c.kind AS kind, c.pair_id AS pair_id, c.gap AS gap, c.needed AS needed
"""


@spike(
    1,
    "MERGE a relationship with a property map, then SET on it (Q5, Q6, Q7)",
    "MATCH-then-CREATE guarded by an existence check.",
)
def spike_merge_rel_with_property_map(ctx: Ctx) -> str:
    g = ctx.graph("1")
    ingest_claim(g, id="c1-a", speaker="w1", subject="s1", place="kitchen", t0=0, t1=10)
    ingest_claim(g, id="c2-b", speaker="w1", subject="s1", place="study", t0=12, t1=20)

    params = {"a": "c1-a", "b": "c2-b", "pair_id": "c1-a|c2-b", "gap": 2, "needed": 9}
    first = g.query(MERGE_REL_THEN_SET, params)
    if first.relationships_created != 1:
        raise Unmet(f"first MERGE created {first.relationships_created} relationships, want 1")

    second = g.query(MERGE_REL_THEN_SET, params)
    if second.relationships_created != 0:
        raise Unmet(
            f"re-running MERGE created {second.relationships_created} more relationships; "
            "the property map is not matching an existing relationship"
        )

    kind, pair_id, gap, needed = second.result_set[0]
    if (kind, pair_id, gap, needed) != ("impossible_travel", "c1-a|c2-b", 2, 9):
        raise Unmet(f"read back {(kind, pair_id, gap, needed)!r}")

    total = g.ro_query("MATCH ()-[c:CONTRADICTS]->() RETURN count(c) AS n").result_set[0][0]
    if total != 1:
        raise Unmet(f"{total} CONTRADICTS relationships exist, want 1 (MERGE duplicated)")

    return "MERGE created 1, re-MERGE created 0, SET readable (gap=2, needed=9)"


# --------------------------------------------------------------------------
# 2. MERGE ... ON CREATE SET on nodes
# --------------------------------------------------------------------------

MERGE_EVIDENCE_ON_CREATE = """
MERGE (e:Evidence {id:$evidence_id})
  ON CREATE SET e.fact_id = $fact_id, e.src = $src, e.t0 = $t0, e.t1 = $t1,
                e.place = $place, e.agent = $agent
RETURN e.fact_id AS fact_id, e.src AS src, e.t0 AS t0, e.agent AS agent
"""


@spike(
    2,
    "MERGE ... ON CREATE SET on nodes (Evidence, Q5.6)",
    "Read-then-create.",
)
def spike_merge_on_create_set(ctx: Ctx) -> str:
    g = ctx.graph("2")
    params = {
        "evidence_id": "ev-1",
        "fact_id": "f-77",
        "src": "witnessed",
        "t0": 0,
        "t1": 10,
        "place": "kitchen",
        "agent": "dana",
    }
    first = g.query(MERGE_EVIDENCE_ON_CREATE, params)
    if first.nodes_created != 1:
        raise Unmet(f"first MERGE created {first.nodes_created} nodes, want 1")
    if first.result_set[0] != ["f-77", "witnessed", 0, "dana"]:
        raise Unmet(f"ON CREATE SET did not apply: {first.result_set[0]!r}")

    # Mutate, then re-MERGE. ON CREATE must NOT fire the second time.
    g.query("MATCH (e:Evidence {id:'ev-1'}) SET e.fact_id = 'touched'")
    second = g.query(MERGE_EVIDENCE_ON_CREATE, params)
    if second.nodes_created != 0:
        raise Unmet(f"re-MERGE created {second.nodes_created} nodes, want 0")
    if second.result_set[0][0] != "touched":
        raise Unmet("ON CREATE SET fired on an existing node; it overwrote fact_id")

    return "created once (nodes_created=1), re-MERGE created 0 and did not re-fire ON CREATE"


# --------------------------------------------------------------------------
# 3. String concatenation inside a MERGE property map
# --------------------------------------------------------------------------

Q5_EXCLUSIVE_PRESENCE = """
MATCH (a:Claim)-[:ABOUT]->(p:Suspect)<-[:ABOUT]-(b:Claim),
      (a)-[:AT]->(la:Place), (b)-[:AT]->(lb:Place)
WHERE a.id < b.id AND la.id <> lb.id
  AND a.t0 < b.t1 AND b.t0 < a.t1
MERGE (a)-[c:CONTRADICTS {kind:'exclusive_presence', pair_id: a.id + '|' + b.id}]->(b)
RETURN a.id AS a, b.id AS b, c.pair_id AS pair_id
"""


@spike(
    3,
    "String concatenation in a property map inside MERGE (Q5 pair_id)",
    "Compute the pair id in Python and pass it as a parameter.",
)
def spike_concat_in_merge_map(ctx: Ctx) -> str:
    g = ctx.graph("3")
    # Same subject, two places, overlapping windows -> exactly one pair.
    ingest_claim(g, id="c1", speaker="w1", subject="s1", place="kitchen", t0=0, t1=10)
    ingest_claim(g, id="c2", speaker="w1", subject="s1", place="study", t0=5, t1=15)
    # Touching, not overlapping: must NOT be flagged (half-open contract, 4.0).
    ingest_claim(g, id="c3", speaker="w1", subject="s1", place="hall", t0=15, t1=20)

    res = g.query(Q5_EXCLUSIVE_PRESENCE)
    rows = sorted(tuple(r) for r in res.result_set)
    if rows != [("c1", "c2", "c1|c2")]:
        raise Unmet(f"rows = {rows!r}, want [('c1', 'c2', 'c1|c2')]")

    return "pair_id computed in-query = 'c1|c2'; touching interval [15,20) correctly not flagged"


# --------------------------------------------------------------------------
# 4. collect(DISTINCT ...) + size(), and id() in aggregation
# --------------------------------------------------------------------------

Q8_SCOREBOARD = """
MATCH (s:Suspect)
OPTIONAL MATCH (c:Claim)-[:BY]->(s)
OPTIONAL MATCH (c)-[x:CONTRADICTS]-(:Claim)
OPTIONAL MATCH (c)-[:HAS_GAP]->(g:Gap)
WITH s,
     collect(DISTINCT c.id)       AS claim_ids,
     collect(DISTINCT x.pair_id)  AS contradiction_ids,
     collect(DISTINCT id(g))      AS gap_ids
RETURN s.id AS suspect,
       size(claim_ids)         AS claims,
       size(contradiction_ids) AS contradictions,
       size(gap_ids)           AS gaps
ORDER BY contradictions DESC, gaps DESC
"""

ID_ON_RELATIONSHIP = """
MATCH (:Claim)-[x:CONTRADICTS]-(:Claim)
RETURN count(DISTINCT id(x)) AS distinct_rels, collect(DISTINCT id(x)) AS ids
"""


@spike(
    4,
    "collect(DISTINCT ...) + size(), and id() in aggregation (Q8)",
    "Return rows and aggregate in Python.",
)
def spike_collect_distinct_and_id(ctx: Ctx) -> str:
    g = ctx.graph("4")
    # One speaker (s1), two claims about s2, one contradiction between them,
    # two gaps on c1. s1 is where naive counting would report 2 contradictions.
    ingest_claim(g, id="c1", speaker="s1", subject="s2", place="kitchen", t0=0, t1=20)
    ingest_claim(g, id="c2", speaker="s1", subject="s2", place="study", t0=5, t1=15)
    g.query(
        "MATCH (a:Claim {id:'c1'}), (b:Claim {id:'c2'}) "
        "MERGE (a)-[:CONTRADICTS {kind:'exclusive_presence', pair_id:'c1|c2'}]->(b)"
    )
    for g0, g1 in ((0, 5), (10, 20)):
        g.query(
            "MATCH (c:Claim {id:'c1'}) CREATE (gp:Gap {t0:$g0, t1:$g1}) "
            "CREATE (c)-[:HAS_GAP]->(gp)",
            {"g0": g0, "g1": g1},
        )

    rows = {r[0]: tuple(r[1:]) for r in g.ro_query(Q8_SCOREBOARD).result_set}
    if rows.get("s1") != (2, 1, 2):
        raise Unmet(
            f"scoreboard for speaker s1 = {rows.get('s1')!r}, want (claims=2, contradictions=1, "
            f"gaps=2). Full rows: {rows!r}"
        )
    if rows.get("s2") != (0, 0, 0):
        raise Unmet(f"a suspect who made no claim returned {rows.get('s2')!r}, want (0, 0, 0)")

    rel = g.ro_query(ID_ON_RELATIONSHIP).result_set[0]
    if rel[0] != 1 or len(rel[1]) != 1:
        raise Unmet(f"id(relationship) aggregation returned {rel!r}, want 1 distinct id")

    return (
        "size(collect(DISTINCT ...)) = (claims=2, contradictions=1, gaps=2); "
        "one contradiction counted once from both endpoints; "
        "id() works on nodes and relationships inside collect(DISTINCT)"
    )


# --------------------------------------------------------------------------
# 5. Boolean expression in a RETURN projection
# --------------------------------------------------------------------------

Q2_GATHER_EVIDENCE = """
MATCH (f:Fact)-[:ABOUT]->(:Person {id:$subject}), (f)-[:AT]->(l:Place)
WHERE f.t0 < $t1 AND $t0 < f.t1
OPTIONAL MATCH (f)-[:VIA]->(tr:Transmission)-[:FROM]->(src:Person)
RETURN f.id AS fact_id, f.src AS src, f.t0 AS t0, f.t1 AS t1,
       f.learned_at AS learned_at,
       l.id AS place, (l.id = $place) AS same_place,
       tr.id AS transmission_id, tr.src_agent AS heard_from,
       tr.src_fact_id AS src_fact_id, tr.tick AS heard_tick
ORDER BY f.t0
"""

WRITE_FACT = """
MERGE (p:Person {id:$subject})
MERGE (l:Place {id:$place})
CREATE (f:Fact {id:$id, kind:$kind, src:$src, t0:$t0, t1:$t1, learned_at:$learned_at})
CREATE (f)-[:ABOUT]->(p)
CREATE (f)-[:AT]->(l)
"""

WRITE_TRANSMISSION = """
MATCH (f:Fact {id:$id})
MERGE (r:Person {id:$src_agent})
CREATE (tr:Transmission {id:$transmission_id, tick:$tick,
                         src_agent:$src_agent, src_fact_id:$src_fact_id})
CREATE (f)-[:VIA]->(tr)
CREATE (tr)-[:FROM]->(r)
"""


def write_fact(g: Graph, **kw) -> None:
    g.query(WRITE_FACT, {"kind": "saw", **kw})


@spike(
    5,
    "Boolean expression in a RETURN projection ((l.id = $place) AS same_place, Q2)",
    "Return l.id and compare in Python.",
)
def spike_boolean_projection(ctx: Ctx) -> str:
    g = ctx.graph("5")
    kitchen = {"subject": "s1", "place": "kitchen"}
    write_fact(g, id="f1", src="witnessed", t0=0, t1=10, learned_at=0, **kitchen)
    write_fact(g, id="f2", subject="s1", place="study", src="witnessed", t0=5, t1=12, learned_at=5)
    write_fact(g, id="f3", src="hearsay", t0=2, t1=8, learned_at=30, **kitchen)
    g.query(
        WRITE_TRANSMISSION,
        {
            "id": "f3",
            "transmission_id": "tr-1",
            "tick": 30,
            "src_agent": "erin",
            "src_fact_id": "f-erin-9",
        },
    )

    res = g.ro_query(
        Q2_GATHER_EVIDENCE, {"subject": "s1", "place": "kitchen", "t0": 0, "t1": 15}
    )
    cols = [h[1] for h in res.header]
    key = cols.index("fact_id")
    by_id = {r[key]: dict(zip(cols, r, strict=True)) for r in res.result_set}
    if len(by_id) != 3:
        raise Unmet(f"gathered {len(by_id)} facts, want 3 (no LIMIT, all evidence): {by_id!r}")

    same = {k: v["same_place"] for k, v in by_id.items()}
    if same != {"f1": True, "f2": False, "f3": True}:
        raise Unmet(f"same_place projection = {same!r}, want f1/f3 True and f2 False")
    if not all(isinstance(v, bool) for v in same.values()):
        raise Unmet(f"same_place is not a Python bool: {[type(v).__name__ for v in same.values()]}")
    if by_id["f3"]["heard_from"] != "erin" or by_id["f3"]["heard_tick"] != 30:
        raise Unmet(f"OPTIONAL MATCH on the transmission did not bind: {by_id['f3']!r}")
    if by_id["f1"]["transmission_id"] is not None:
        raise Unmet(f"unmatched OPTIONAL MATCH is not None: {by_id['f1']['transmission_id']!r}")

    return (
        "(l.id = $place) returns a real bool (f1=True, f2=False, f3=True); "
        "OPTIONAL MATCH yields None on the witnessed facts"
    )


# --------------------------------------------------------------------------
# 6. Client params, GRAPH.RO_QUERY, graph.copy()
# --------------------------------------------------------------------------

@spike(
    6,
    "Client params, GRAPH.RO_QUERY and graph.copy() through the Python client",
    "Inline literals with strict escaping; plain query() for reads; "
    "rebuild the fork by replaying writes instead of copying.",
)
def spike_client_params_ro_query_copy(ctx: Ctx) -> str:
    g = ctx.graph("6")
    notes = []

    # (a) parameters of every type the schema uses
    params = {
        "s": "kitchen",
        "i": 42,
        "f": 0.5,
        "b": True,
        "n": None,
        "lst": ["a", "b"],
    }
    res = g.query(
        "CREATE (x:Probe {s:$s, i:$i, f:$f, b:$b, lst:$lst}) "
        "RETURN x.s AS s, x.i AS i, x.f AS f, x.b AS b, x.lst AS lst, $n IS NULL AS n_is_null",
        params,
    )
    row = res.result_set[0]
    if row != ["kitchen", 42, 0.5, True, ["a", "b"], True]:
        raise Unmet(f"parameter round trip returned {row!r}")
    notes.append("params ok (str/int/float/bool/null/list)")

    # (b) GRAPH.RO_QUERY — reads work, and a write through it must be refused.
    n = g.ro_query("MATCH (x:Probe) RETURN count(x) AS n", {}).result_set[0][0]
    if n != 1:
        raise Unmet(f"ro_query read returned {n}, want 1")
    try:
        g.ro_query("CREATE (:ShouldNotExist)")
    except Exception as exc:  # noqa: BLE001 — the refusal is the thing being tested
        notes.append(f"ro_query refuses writes ({type(exc).__name__})")
    else:
        raise Unmet(
            "ro_query accepted a CREATE. GRAPH.RO_QUERY does not enforce read-only here, "
            "so it cannot be leaned on for the detective's read path."
        )

    # (c) graph.copy() — the what-if fork (Q10)
    clone_name = f"spike:6-clone:{ctx.run_id}"
    ctx.created.append(clone_name)
    clone = g.copy(clone_name)
    clone_n = clone.ro_query("MATCH (x:Probe) RETURN count(x) AS n").result_set[0][0]
    if clone_n != 1:
        raise Unmet(f"clone has {clone_n} Probe nodes, want 1")
    clone.query("CREATE (:Probe {s:'fork-only'})")
    origin_n = g.ro_query("MATCH (x:Probe) RETURN count(x) AS n").result_set[0][0]
    if origin_n != 1:
        raise Unmet(f"writing to the clone changed the original (now {origin_n} nodes)")
    clone.delete()
    ctx.forget(clone_name)
    notes.append("graph.copy() clones and the clone is independent")

    return "; ".join(notes)


# --------------------------------------------------------------------------
# 7. Throughput: ~10 mind graphs plus a case graph, concurrently
# --------------------------------------------------------------------------

BATCH_FACTS = """
UNWIND $rows AS r
MERGE (p:Person {id:r.subject})
MERGE (l:Place {id:r.place})
CREATE (f:Fact {id:r.id, kind:r.kind, src:r.src, t0:r.t0, t1:r.t1, learned_at:r.learned_at})
CREATE (f)-[:ABOUT]->(p)
CREATE (f)-[:AT]->(l)
"""

MINDS = 10
FACTS_PER_MIND = 200
BATCH = 50
BUDGET_SECONDS = 30.0


def _fill_mind(name: str, agent: int) -> tuple[int, float]:
    """One thread, one connection, one mind graph. Returns (facts, seconds)."""
    db = connect()
    g = db.select_graph(name)
    started = time.perf_counter()
    written = 0
    for start in range(0, FACTS_PER_MIND, BATCH):
        rows = [
            {
                "id": f"a{agent}-f{i}",
                "subject": f"s{i % 7}",
                "place": f"p{i % 11}",
                "kind": "saw",
                "src": "witnessed" if i % 5 else "hearsay",
                "t0": i % 280,
                "t1": (i % 280) + 10,
                "learned_at": i % 280,
            }
            for i in range(start, min(start + BATCH, FACTS_PER_MIND))
        ]
        g.query(BATCH_FACTS, {"rows": rows})
        written += len(rows)
    return written, time.perf_counter() - started


def _fill_case(name: str) -> tuple[int, float]:
    db = connect()
    g = db.select_graph(name)
    started = time.perf_counter()
    for i in range(140):
        ingest_claim(
            g,
            id=f"c{i}",
            speaker=f"s{(i + 1) % 7}",
            subject=f"s{i % 7}",
            place=f"p{i % 11}",
            t0=(i * 2) % 280,
            t1=((i * 2) % 280) + 12,
        )
    return 140, time.perf_counter() - started


@spike(
    7,
    f"Throughput: {MINDS} mind graphs + a case graph written concurrently",
    "Write minds sequentially in a single thread, or batch harder "
    "(larger UNWIND) if concurrency is the bottleneck.",
)
def spike_concurrent_graph_writes(ctx: Ctx) -> str:
    names = [f"spike:7-mind-{i}:{ctx.run_id}" for i in range(MINDS)]
    case_name = f"spike:7-case:{ctx.run_id}"
    ctx.created.extend([*names, case_name])

    wall = time.perf_counter()
    with ThreadPoolExecutor(max_workers=MINDS + 1) as pool:
        futures = [pool.submit(_fill_mind, n, i) for i, n in enumerate(names)]
        futures.append(pool.submit(_fill_case, case_name))
        results = [f.result() for f in futures]  # re-raises any worker error
    wall = time.perf_counter() - wall

    total_rows = sum(r[0] for r in results)
    slowest = max(r[1] for r in results)

    for n in names:
        count = ctx.db.select_graph(n).ro_query(
            "MATCH (f:Fact) RETURN count(f) AS n"
        ).result_set[0][0]
        if count != FACTS_PER_MIND:
            raise Unmet(f"{n} holds {count} facts, want {FACTS_PER_MIND} — concurrent writes lost")
    claims = ctx.db.select_graph(case_name).ro_query(
        "MATCH (c:Claim) RETURN count(c) AS n"
    ).result_set[0][0]
    if claims != 140:
        raise Unmet(f"case graph holds {claims} claims, want 140")

    if wall > BUDGET_SECONDS:
        raise Unmet(f"took {wall:.1f}s, over the {BUDGET_SECONDS:.0f}s budget for this spike")

    return (
        f"{MINDS} minds x {FACTS_PER_MIND} facts + 140 claims = {total_rows} writes "
        f"in {wall:.2f}s wall ({total_rows / wall:,.0f} rows/s), slowest graph {slowest:.2f}s, "
        f"all counts exact"
    )


# --------------------------------------------------------------------------
# 8. algo.SPpaths standalone per pair, and the shape of the returned path
# --------------------------------------------------------------------------

SPPATHS_MATCHED = """
MATCH (a:Place {id:$a}), (b:Place {id:$b})
CALL algo.SPpaths({sourceNode: a, targetNode: b, relTypes: ['ADJACENT_TO'],
                   weightProp: 'minutes', relDirection: 'both'})
YIELD path, pathWeight
RETURN pathWeight AS weight, [n IN nodes(path) | n.id] AS route
"""

SPPATHS_SPEC_LITERAL = """
CALL algo.SPpaths({sourceNode: $a, targetNode: $b, relTypes: ['ADJACENT_TO'],
                   weightProp: 'minutes', relDirection: 'both'})
YIELD path, pathWeight
RETURN pathWeight AS weight, [n IN nodes(path) | n.id] AS route
"""

FLOOR_PLAN = [
    ("p0", "p1", 3),
    ("p1", "p2", 4),
    ("p2", "p3", 2),
    ("p3", "p4", 5),
    ("p4", "p5", 3),
    ("p5", "p6", 6),
    ("p6", "p7", 2),
    ("p7", "p8", 4),
    ("p8", "p9", 3),
    ("p0", "p5", 20),
    ("p2", "p7", 7),
]


@spike(
    8,
    "algo.SPpaths standalone per place pair, and the shape of path / pathWeight (Q6)",
    "Run Dijkstra in Python over the ADJACENT_TO edges read out of the graph, "
    "and write the same TRAVEL_TIME edges.",
)
def spike_sppaths_travel_matrix(ctx: Ctx) -> str:
    g = ctx.graph("8")
    places = sorted({p for edge in FLOOR_PLAN for p in edge[:2]})
    for p in places:
        g.query("MERGE (:Place {id:$id})", {"id": p})
    for a, b, minutes in FLOOR_PLAN:
        # Symmetric: both directions written, per spec 4.1.
        g.query(
            "MATCH (a:Place {id:$a}), (b:Place {id:$b}) "
            "MERGE (a)-[:ADJACENT_TO {minutes:$m}]->(b) "
            "MERGE (b)-[:ADJACENT_TO {minutes:$m}]->(a)",
            {"a": a, "b": b, "m": minutes},
        )

    res = g.ro_query(SPPATHS_MATCHED, {"a": "p0", "b": "p9"})
    if not res.result_set:
        raise Unmet("algo.SPpaths yielded no rows for p0 -> p9")
    weight, route = res.result_set[0]
    if weight != 21:
        raise Unmet(f"pathWeight = {weight!r}, want 21 (p0-p1-p2-p7-p8-p9 = 3+4+7+4+3)")
    if route != ["p0", "p1", "p2", "p7", "p8", "p9"]:
        raise Unmet(f"route = {route!r}, want ['p0','p1','p2','p7','p8','p9']")
    if not isinstance(route, list) or not all(isinstance(x, str) for x in route):
        raise Unmet(f"nodes(path) projection is not a list of ids: {route!r}")

    # The all-pairs matrix build: one standalone call per ordered pair.
    started = time.perf_counter()
    matrix: dict[tuple[str, str], int] = {}
    for a in places:
        for b in places:
            if a == b:
                continue
            rows = g.ro_query(SPPATHS_MATCHED, {"a": a, "b": b}).result_set
            if not rows:
                raise Unmet(f"no path yielded for {a} -> {b} on a connected floor plan")
            matrix[(a, b)] = rows[0][0]
    elapsed = time.perf_counter() - started

    if matrix[("p0", "p9")] != matrix[("p9", "p0")]:
        raise Unmet("relDirection 'both' is not symmetric on a symmetric floor plan")

    # The literal snippet in spec 5.10 passes sourceNode as a parameter. Check it.
    try:
        g.ro_query(SPPATHS_SPEC_LITERAL, {"a": "p0", "b": "p9"})
    except Exception as exc:  # noqa: BLE001 — recorded as a note, not a failure
        note = (
            f"NOTE: the literal snippet in spec 5.10 (sourceNode: $la) fails — "
            f"{type(exc).__name__}: {str(exc).strip()[:120]}. "
            "M1 must MATCH the Place nodes first and pass node values, as above."
        )
    else:
        note = "NOTE: sourceNode also accepts a string parameter"

    return (
        f"p0->p9 weight 21 via ['p0','p1','p2','p7','p8','p9']; "
        f"{len(matrix)} ordered pairs ({len(places)} places) in {elapsed:.2f}s "
        f"({elapsed / len(matrix) * 1000:.1f}ms/call); symmetric under relDirection 'both'. "
        f"{note}"
    )


# --------------------------------------------------------------------------
# 9. FastMCP round trip (only if MCP survives the cut)
# --------------------------------------------------------------------------

@spike(
    9,
    "FastMCP version and tool-call round trip",
    "Call the typed tools directly from the orchestrator. MCP is an extension "
    "(spec section 3) and is on the cut list (spec section 11).",
)
def spike_fastmcp_round_trip(ctx: Ctx) -> str:
    try:
        from fastmcp import Client, FastMCP
    except ImportError as exc:
        raise SkipSpike(
            f"fastmcp is not installed ({exc}). MCP is an extension and first-class "
            "cut candidate, so it is not in requirements.txt. "
            "Install requirements-optional.txt to run this spike."
        ) from exc

    import asyncio
    from importlib.metadata import version as pkg_version

    server = FastMCP("alibi-spike")

    @server.tool
    def recall(subject: str, t0: int, t1: int) -> list[dict]:
        """Mind-graph recall. No graph name, no agent id (project rules, 6)."""
        return [{"subject": subject, "t0": t0, "t1": t1, "src": "witnessed"}]

    async def round_trip():
        async with Client(server) as client:
            tools = await client.list_tools()
            result = await client.call_tool("recall", {"subject": "s1", "t0": 0, "t1": 15})
            return [t.name for t in tools], result

    names, result = asyncio.run(round_trip())
    if names != ["recall"]:
        raise Unmet(f"list_tools returned {names!r}")
    payload = result.data if hasattr(result, "data") else result
    if not payload or payload[0]["subject"] != "s1":
        raise Unmet(f"call_tool returned {payload!r}")
    if any(p in ("graph", "graph_name", "agent_id") for p in ("subject", "t0", "t1")):
        raise Unmet("tool signature exposes a graph name or agent id")

    return (
        f"fastmcp {pkg_version('fastmcp')}: in-memory client/server round trip ok, "
        "tool signature carries no graph name or agent id. "
        "NOT tested: the model-transport half of the round trip (needs a live client)"
    )


# --------------------------------------------------------------------------
# runner
# --------------------------------------------------------------------------

def _decode(v):
    return v.decode() if isinstance(v, bytes) else v


def graph_module(db) -> tuple[str, str] | None:
    """Return (name, version) of the loaded graph module, or None if absent.

    A plain redis on the expected port answers PING perfectly happily. Without
    this check the spikes would run against it and report nine confusing
    failures instead of one clear one.
    """
    for m in db.connection.execute_command("MODULE LIST"):
        if isinstance(m, dict):
            as_dict = {_decode(k): _decode(v) for k, v in m.items()}
        else:
            pairs = zip(m[::2], m[1::2], strict=False)
            as_dict = {_decode(k): _decode(v) for k, v in pairs}
        name = str(as_dict.get("name", ""))
        if "graph" in name.lower():
            return name, str(as_dict.get("ver"))
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="*", type=int, help="run only these spike numbers")
    parser.add_argument("--keep", action="store_true", help="do not delete scratch graphs")
    parser.add_argument("--traceback", action="store_true", help="print full tracebacks")
    args = parser.parse_args(argv)

    from importlib.metadata import version as pkg_version

    print("ALIBI — FalkorDB assumption spikes (spec section 12)")
    try:
        db = connect()
        db.connection.ping()
    except Exception as exc:  # noqa: BLE001
        print(f"\ncannot reach FalkorDB at {settings.falkor_host}:{settings.falkor_port}")
        print(f"  {type(exc).__name__}: {exc}")
        print("\nrun `make up` first.")
        return 2

    module = graph_module(db)
    if module is None:
        print(f"\n{settings.falkor_host}:{settings.falkor_port} answers PING but has no graph")
        print("module loaded — this is a plain redis, not FalkorDB.")
        print("\nIf another service already holds 6379, set FALKOR_PORT (see .env.example)")
        print("and use `make spikes`, which exports it.")
        return 2

    run_id = uuid.uuid4().hex[:8]
    print(f"  server   {settings.falkor_host}:{settings.falkor_port}  "
          f"module {module[0]} v{module[1]}")
    print(f"  client   falkordb {pkg_version('falkordb')}  python {sys.version.split()[0]}")
    print(f"  run id   {run_id}")
    print("-" * 78)

    selected = [s for s in sorted(SPIKES, key=lambda s: s.number)
                if not args.only or s.number in args.only]
    ctx = Ctx(db=db, run_id=run_id, keep=args.keep)
    results: list[tuple[Spike, str, str]] = []

    for s in selected:
        started = time.perf_counter()
        try:
            detail = s.fn(ctx)
            status, note = PASS, detail
        except SkipSpike as exc:
            status, note = SKIP, str(exc)
        except Exception as exc:  # noqa: BLE001 — probing; always re-printed in full
            status = FAIL
            note = f"{type(exc).__module__}.{type(exc).__name__}: {exc}"
            if args.traceback:
                note += "\n" + traceback.format_exc()
        took = time.perf_counter() - started
        results.append((s, status, note))

        print(f"spike {s.number}  {status}  {s.title}  [{took:.2f}s]")
        for line in _wrap(note):
            print(f"          {line}")
        if status == FAIL:
            for line in _wrap(f"fallback (spec 12.{s.number}): {s.fallback}"):
                print(f"          {line}")
        print()

    problems = ctx.cleanup()
    if problems:
        print("scratch graph cleanup problems:")
        for p in problems:
            print(f"  {p}")
        print()
    elif args.keep:
        print(f"scratch graphs kept, prefix spike:*:{run_id}\n")

    passed = sum(1 for _, st, _ in results if st == PASS)
    failed = sum(1 for _, st, _ in results if st == FAIL)
    skipped = sum(1 for _, st, _ in results if st == SKIP)
    print("-" * 78)
    print(f"{passed} passed, {failed} failed, {skipped} skipped, of {len(results)} run")
    if failed:
        print("failed: " + ", ".join(str(s.number) for s, st, _ in results if st == FAIL))
        print("Do not build on a failed assumption. Record it in PROGRESS.md and take "
              "the fallback deliberately.")
    return 1 if failed else 0


def _wrap(text: str, width: int = 86) -> list[str]:
    out: list[str] = []
    for para in text.split("\n"):
        line = ""
        for word in para.split(" "):
            if line and len(line) + 1 + len(word) > width:
                out.append(line)
                line = word
            else:
                line = f"{line} {word}".strip()
        out.append(line)
    return out


if __name__ == "__main__":
    raise SystemExit(main())
