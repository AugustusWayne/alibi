"""Cypher for the referee. Reads a mind other than the caller's own.

This is the only module permitted to do that (PROJECT_RULES.md rule 6). Nothing here
is reachable from a tool exposed to an agent: the referee is not an agent, it
is the scoring and provenance authority that stands outside the case.

`Transmission.src_fact_id` points at a fact in *another* graph. FalkorDB graphs
are isolated, so there is no edge to follow — the referee resolves the
reference by switching graphs, which is precisely why only it can trace a
chain. Each query below therefore runs against one mind at a time.
"""

# One fact in this mind, with the transmission that produced it if it was
# hearsay. This is a single chain step: the fact's own grounding plus the
# pointer into the next agent's graph.
FACT_WITH_PROVENANCE = """
MATCH (f:Fact {id:$fact_id})
OPTIONAL MATCH (f)-[:VIA]->(tr:Transmission)-[:FROM]->(speaker:Person)
OPTIONAL MATCH (f)-[:ABOUT]->(subject:Person)
OPTIONAL MATCH (f)-[:AT]->(place:Place)
RETURN f.id AS fact_id, f.src AS src, f.kind AS kind,
       f.t0 AS t0, f.t1 AS t1, f.learned_at AS learned_at,
       subject.id AS subject, place.id AS place,
       tr.id AS transmission_id, tr.tick AS tick,
       tr.src_agent AS src_agent, tr.src_fact_id AS src_fact_id
"""

# Every hearsay fact in this mind that bears on a claim window, with its
# transmission. The entry points for tracing a HEARSAY verdict: no LIMIT,
# because a claim may rest on several secondhand memories and the referee
# must see all of them before reporting which chain it followed.
HEARSAY_SUPPORT_FOR_CLAIM = """
MATCH (f:Fact)-[:ABOUT]->(:Person {id:$subject}), (f)-[:AT]->(l:Place {id:$place})
WHERE f.src = 'hearsay' AND f.t0 < $t1 AND $t0 < f.t1
MATCH (f)-[:VIA]->(tr:Transmission)
RETURN f.id AS fact_id, f.t0 AS t0, f.t1 AS t1, f.learned_at AS learned_at,
       tr.id AS transmission_id, tr.tick AS tick,
       tr.src_agent AS src_agent, tr.src_fact_id AS src_fact_id
ORDER BY f.t0, f.id
"""
