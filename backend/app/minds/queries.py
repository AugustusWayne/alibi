"""Cypher for a private mind graph. One constant per graph question.

Every query here runs inside exactly one `mind:{seed}:{agent}` graph. None of
them takes a graph name or an agent id as a parameter — the graph is chosen by
`MindAccess` before the query is ever seen (project rules, rule 6).
`src_agent` on a Transmission is data about who spoke, not a selector for
whose mind to read.
"""

# Q1. Write a fact into this mind: who it is about, where, and when it was learned.
WRITE_FACT = """
MERGE (p:Person {id:$subject})
MERGE (l:Place {id:$place})
CREATE (f:Fact {id:$id, kind:$kind, src:$src, t0:$t0, t1:$t1, learned_at:$learned_at})
CREATE (f)-[:ABOUT]->(p)
CREATE (f)-[:AT]->(l)
"""

# Q1b. Record that a fact in this mind arrived by hearsay, and from whom.
WRITE_TRANSMISSION = """
MATCH (f:Fact {id:$id})
MERGE (r:Person {id:$src_agent})
CREATE (tr:Transmission {id:$transmission_id, tick:$tick,
                         src_agent:$src_agent, src_fact_id:$src_fact_id})
CREATE (f)-[:VIA]->(tr)
CREATE (tr)-[:FROM]->(r)
"""

# Q1c. Record that this mind inferred a fact from another fact it already held.
WRITE_DERIVATION = """
MATCH (f:Fact {id:$id}), (src:Fact {id:$from_fact_id})
CREATE (f)-[:DERIVED_FROM]->(src)
"""

# Name a Place this mind knows about, so recall can report place names.
UPSERT_PLACE = """
MERGE (l:Place {id:$id})
ON CREATE SET l.name = $name
"""

# Name a Person this mind knows about.
UPSERT_PERSON = """
MERGE (p:Person {id:$id})
ON CREATE SET p.name = $name
"""

# Q2. Every fact in this mind that overlaps a claim window and is about its
# subject — same-place (potential support) and different-place (potential
# conflict) together, in one pass, with no LIMIT. The decision happens
# afterwards in Python over the whole set, so that one supporting memory can
# never mask a conflicting one by being read first.
GATHER_EVIDENCE = """
MATCH (f:Fact)-[:ABOUT]->(:Person {id:$subject}), (f)-[:AT]->(l:Place)
WHERE f.t0 < $t1 AND $t0 < f.t1
OPTIONAL MATCH (f)-[:VIA]->(tr:Transmission)-[:FROM]->(src:Person)
RETURN f.id AS fact_id, f.src AS src, f.t0 AS t0, f.t1 AS t1,
       f.learned_at AS learned_at,
       l.id AS place, (l.id = $place) AS same_place,
       tr.id AS transmission_id, tr.src_agent AS heard_from,
       tr.src_fact_id AS src_fact_id, tr.tick AS heard_tick
ORDER BY f.t0, f.id
"""

# What this mind remembers, for the suspect's own `recall` tool. Filters are
# optional and applied by null-checking the parameter, so one query serves
# every call shape without string building.
RECALL = """
MATCH (f:Fact)-[:ABOUT]->(p:Person), (f)-[:AT]->(l:Place)
WHERE ($subject IS NULL OR p.id = $subject)
  AND ($place   IS NULL OR l.id = $place)
  AND ($t0 IS NULL OR $t1 IS NULL OR (f.t0 < $t1 AND $t0 < f.t1))
OPTIONAL MATCH (f)-[:VIA]->(tr:Transmission)-[:FROM]->(src:Person)
RETURN f.id AS fact_id, f.kind AS kind, f.src AS src,
       f.t0 AS t0, f.t1 AS t1, f.learned_at AS learned_at,
       p.id AS subject, l.id AS place,
       tr.src_agent AS heard_from, tr.src_fact_id AS src_fact_id,
       tr.tick AS heard_tick
ORDER BY f.t0, f.id
"""

# Does this mind hold a given fact id? The referee's chain walk needs this to
# tell CHAIN_BROKEN (source never recorded it) from ORIGIN_UNSUPPORTED.
FACT_BY_ID = """
MATCH (f:Fact {id:$fact_id})
RETURN f.id AS fact_id, f.src AS src, f.t0 AS t0, f.t1 AS t1,
       f.learned_at AS learned_at
"""

# How many facts this mind holds. Isolation tests assert one mind's writes
# never appear in another's count.
COUNT_FACTS = """
MATCH (f:Fact)
RETURN count(f) AS facts
"""
