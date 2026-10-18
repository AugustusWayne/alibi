"""Cypher for the ground-truth world graph. Referee only.

`world:{seed}` is what actually happened. No agent and no detective reads it;
it exists so the referee can score the audit against the truth, and so the
`PlantedFabrication` records make ground-truth scoring possible without guessing.

**Only the generator creates provenance** (project rules, rule 5). Every write
here belongs to the generator. The audit engine imports nothing from this
module.
"""

# A room on the floor plan.
UPSERT_PLACE = """
MERGE (l:Place {id:$id})
ON CREATE SET l.name = $name
"""

# A person, and what the generator made them: honest, culprit or accomplice.
UPSERT_PERSON = """
MERGE (p:Person {id:$id})
ON CREATE SET p.name = $name, p.role = $role
"""

# A corridor between two rooms, written both ways so adjacency is symmetric.
UPSERT_ADJACENCY = """
MATCH (a:Place {id:$a}), (b:Place {id:$b})
MERGE (a)-[r:ADJACENT_TO]->(b)
SET r.minutes = $minutes
MERGE (b)-[q:ADJACENT_TO]->(a)
SET q.minutes = $minutes
"""

# One true segment of someone's evening: where they really were, when.
CREATE_PRESENCE = """
CREATE (:Presence {person:$person, place:$place, t0:$t0, t1:$t1})
"""

# The incident: where and when.
UPSERT_INCIDENT = """
MERGE (i:Incident {id:$id})
ON CREATE SET i.place = $place, i.t0 = $t0, i.t1 = $t1
"""

# The generator's record of what it instructed an agent to fabricate. This is
# what makes ground-truth scoring possible without inferring intent.
CREATE_PLANTED_FABRICATION = """
CREATE (:PlantedFabrication {claim_key:$claim_key, by_person:$by_person, reason:$reason,
                             pathology:$pathology, src_fact_id:$src_fact_id})
"""

# Who was really where, for the referee's scoring and the oracle.
ALL_PRESENCES = """
MATCH (pr:Presence)
RETURN pr.person AS person, pr.place AS place, pr.t0 AS t0, pr.t1 AS t1
ORDER BY pr.person, pr.t0
"""

# Everyone in the world and what role the generator gave them.
ALL_PEOPLE = """
MATCH (p:Person)
RETURN p.id AS id, p.name AS name, p.role AS role
ORDER BY p.id
"""

# Every fabrication the generator planted.
ALL_PLANTED_FABRICATIONS = """
MATCH (f:PlantedFabrication)
RETURN f.claim_key AS claim_key, f.by_person AS by_person, f.reason AS reason,
       f.pathology AS pathology, f.src_fact_id AS src_fact_id
ORDER BY f.claim_key
"""

# Counts, for the reproducibility test and the generator's own report.
WORLD_COUNTS = """
MATCH (p:Person) WITH count(p) AS people
MATCH (l:Place) WITH people, count(l) AS places
MATCH (pr:Presence) WITH people, places, count(pr) AS presences
MATCH (f:PlantedFabrication)
RETURN people, places, presences, count(f) AS fabrications
"""
