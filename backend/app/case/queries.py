"""Cypher for the case graph — the detective's file, public information only.

The case graph never holds a private fact. When an audit cites one it writes a
redacted `Evidence` shadow instead (spec 4.3), which is what lets
`SUPPORTED_BY` be a real walkable path without opening a window into a
suspect's whole memory.

Every temporal predicate below is the half-open contract from spec 4.0 with
strict inequalities, matching `audit/time_contract.py`. If you change one,
change both.
"""

# Public floor plan: a place and its name.
UPSERT_PLACE = """
MERGE (l:Place {id:$id})
ON CREATE SET l.name = $name
"""

# Public floor plan: a corridor, written in both directions so adjacency is
# symmetric without any query having to say so.
UPSERT_ADJACENCY = """
MATCH (a:Place {id:$a}), (b:Place {id:$b})
MERGE (a)-[r:ADJACENT_TO]->(b)
SET r.minutes = $minutes
MERGE (b)-[q:ADJACENT_TO]->(a)
SET q.minutes = $minutes
"""

# Build-time, once per world: the weighted shortest walk between two places
# over the public floor plan. The all-pairs result is stored as TRAVEL_TIME so
# the audit-time travel check needs no per-row procedure call.
#
# The MATCH prefix is required: algo.SPpaths takes bound node values, and
# passing an id string as sourceNode fails on FalkorDB v4.22.1 with
# "sourceNode and targetNode must be of type Node" (M0 spike 8).
SHORTEST_PATH = """
MATCH (a:Place {id:$a}), (b:Place {id:$b})
CALL algo.SPpaths({sourceNode: a, targetNode: b, relTypes: ['ADJACENT_TO'],
                   weightProp: 'minutes', relDirection: 'both'})
YIELD path, pathWeight
RETURN pathWeight AS weight, [n IN nodes(path) | n.id] AS route
"""

# Store one cell of the precomputed all-pairs travel matrix.
UPSERT_TRAVEL_TIME = """
MATCH (a:Place {id:$a}), (b:Place {id:$b})
MERGE (a)-[r:TRAVEL_TIME]->(b)
SET r.minutes = $minutes
"""

# Read one cell of the travel matrix, for the detective's check_travel tool.
TRAVEL_TIME_LOOKUP = """
MATCH (a:Place {id:$a})-[r:TRAVEL_TIME]->(b:Place {id:$b})
RETURN r.minutes AS minutes
"""

# Every place on the public floor plan.
ALL_PLACES = """
MATCH (l:Place)
RETURN l.id AS id, l.name AS name
ORDER BY l.id
"""

# A suspect the detective may interview.
UPSERT_SUSPECT = """
MERGE (s:Suspect {id:$id})
ON CREATE SET s.name = $name
"""

# The incident under investigation.
UPSERT_INCIDENT = """
MERGE (i:Incident {id:$id})
ON CREATE SET i.place = $place, i.t0 = $t0, i.t1 = $t1
"""

# Q4. Ingest a claim: who said it, who it is about, where, when, how strongly.
# The verdict starts PENDING — only the audit may set it.
INGEST_CLAIM = """
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

# A claim the speaker says they were told rather than witnessed.
LINK_RELAYED_FROM = """
MATCH (c:Claim {id:$id})
MERGE (r:Suspect {id:$relayed_from})
CREATE (c)-[:RELAYED_FROM]->(r)
"""

# Q5. Which claim pairs put the same person in two different places at once?
# Strict inequalities per the time contract; `pair_id` so the scoreboard can
# count distinct contradictions without relying on internal relationship ids.
EXCLUSIVE_PRESENCE = """
MATCH (a:Claim)-[:ABOUT]->(p:Suspect)<-[:ABOUT]-(b:Claim),
      (a)-[:AT]->(la:Place), (b)-[:AT]->(lb:Place)
WHERE a.id < b.id AND la.id <> lb.id
  AND a.t0 < b.t1 AND b.t0 < a.t1
MERGE (a)-[c:CONTRADICTS {kind:'exclusive_presence', pair_id: a.id + '|' + b.id}]->(b)
RETURN a.id AS a, b.id AS b
"""

# Q6, audit time. Which claim pairs are too far apart in space for the time
# between them? One query over the precomputed matrix, no procedure call per
# row. Impossible iff the slack is strictly less than the walk.
IMPOSSIBLE_TRAVEL = """
MATCH (a:Claim)-[:ABOUT]->(p:Suspect)<-[:ABOUT]-(b:Claim),
      (a)-[:AT]->(la:Place), (b)-[:AT]->(lb:Place),
      (la)-[tt:TRAVEL_TIME]->(lb)
WHERE a.id <> b.id AND la.id <> lb.id
  AND a.t1 <= b.t0
  AND (b.t0 - a.t1) < tt.minutes
MERGE (a)-[c:CONTRADICTS {kind:'impossible_travel', pair_id: a.id + '|' + b.id}]->(b)
SET c.gap = b.t0 - a.t1, c.needed = tt.minutes
RETURN a.id AS a, b.id AS b, (b.t0 - a.t1) AS gap, tt.minutes AS needed
"""

# Q7. Which claim pairs are two different speakers independently placing the
# same person in the same place at an overlapping time?
CORROBORATION = """
MATCH (a:Claim)-[:BY]->(sa:Suspect), (b:Claim)-[:BY]->(sb:Suspect),
      (a)-[:ABOUT]->(p:Suspect), (b)-[:ABOUT]->(p),
      (a)-[:AT]->(l:Place), (b)-[:AT]->(l)
WHERE a.id < b.id AND sa.id <> sb.id
  AND a.t0 < b.t1 AND b.t0 < a.t1
MERGE (a)-[c:CORROBORATES {pair_id: a.id + '|' + b.id}]->(b)
RETURN a.id AS a, b.id AS b
"""

# 5.6. Attach a redacted public shadow of a private fact that supports a claim,
# and record which slice of the claim it covers.
MATERIALIZE_SUPPORT = """
MATCH (c:Claim {id:$claim_id})
MERGE (e:Evidence {id:$evidence_id})
  ON CREATE SET e.fact_id = $fact_id, e.src = $src, e.t0 = $t0, e.t1 = $t1,
                e.place = $place, e.agent = $agent
MERGE (c)-[r:SUPPORTED_BY]->(e)
SET r.covers_t0 = $covers_t0, r.covers_t1 = $covers_t1
"""

# 5.6. Attach the shadow of a private fact that conflicts with a claim. A
# CONTRADICTED claim keeps both its conflicting and its supporting evidence —
# conflict beats support, but it does not erase it.
MATERIALIZE_CONFLICT = """
MATCH (c:Claim {id:$claim_id})
MERGE (e:Evidence {id:$evidence_id})
  ON CREATE SET e.fact_id = $fact_id, e.src = $src, e.t0 = $t0, e.t1 = $t1,
                e.place = $place, e.agent = $agent
MERGE (c)-[r:CONFLICTS_WITH]->(e)
RETURN e.id AS evidence_id
"""

# 5.6. A span of a claim that nothing in the speaker's memory accounts for.
MATERIALIZE_GAP = """
MATCH (c:Claim {id:$claim_id})
CREATE (g:Gap {t0:$g0, t1:$g1})
CREATE (c)-[:HAS_GAP]->(g)
"""

# 5.7. Record where a traced chain ended, and in what role. The referee's
# conclusion only — which agent, which terminal state — never the private
# facts it read to get there. Same privacy seam as the Evidence shadows.
MATERIALIZE_TRACE = """
MATCH (c:Claim {id:$claim_id})
MERGE (s:Suspect {id:$agent})
MERGE (c)-[r:TRACED_TO {role:$role}]->(s)
SET r.terminal = $terminal, r.ungrounded = $ungrounded, r.depth = $depth
"""

# The chain conclusions recorded for one claim — written only when the
# detective spends a polygraph on it, so an absence here means "not asked".
TRACES_FOR_CLAIM = """
MATCH (c:Claim {id:$claim_id})-[r:TRACED_TO]->(s:Suspect)
RETURN s.id AS agent, r.role AS role, r.terminal AS terminal,
       r.ungrounded AS ungrounded, r.depth AS depth
ORDER BY r.role, s.id
"""

# Every traced chain conclusion in the case, for the operator's board.
ALL_TRACES = """
MATCH (c:Claim)-[r:TRACED_TO]->(s:Suspect)
RETURN c.id AS claim_id, s.id AS agent, r.role AS role,
       r.terminal AS terminal, r.ungrounded AS ungrounded, r.depth AS depth
ORDER BY c.id, r.role, s.id
"""

# 5.6. Write the verdict back. The only statement in the system that sets it.
SET_VERDICT = """
MATCH (c:Claim {id:$claim_id})
SET c.verdict = $verdict, c.coverage = $coverage, c.uncovered = $uncovered
"""

# Read a claim back with its speaker, subject and place, for audit and display.
CLAIM_BY_ID = """
MATCH (c:Claim {id:$claim_id})-[:BY]->(s:Suspect),
      (c)-[:ABOUT]->(p:Suspect), (c)-[:AT]->(l:Place)
RETURN c.id AS id, s.id AS speaker, p.id AS subject, l.id AS place,
       c.t0 AS t0, c.t1 AS t1, c.turn AS turn, c.modality AS modality,
       c.verdict AS verdict, c.coverage AS coverage, c.uncovered AS uncovered
"""

# Every claim in the case, oldest turn first — what the audit iterates over.
ALL_CLAIMS = """
MATCH (c:Claim)-[:BY]->(s:Suspect),
      (c)-[:ABOUT]->(p:Suspect), (c)-[:AT]->(l:Place)
RETURN c.id AS id, s.id AS speaker, p.id AS subject, l.id AS place,
       c.t0 AS t0, c.t1 AS t1, c.turn AS turn, c.modality AS modality,
       c.verdict AS verdict, c.coverage AS coverage, c.uncovered AS uncovered
ORDER BY c.turn, c.id
"""

# The evidence and gaps behind one claim — the "every claim needs a path" walk.
CLAIM_EVIDENCE = """
MATCH (c:Claim {id:$claim_id})
OPTIONAL MATCH (c)-[s:SUPPORTED_BY]->(se:Evidence)
OPTIONAL MATCH (c)-[:CONFLICTS_WITH]->(ce:Evidence)
OPTIONAL MATCH (c)-[:HAS_GAP]->(g:Gap)
RETURN collect(DISTINCT se.id) AS supported_by,
       collect(DISTINCT ce.id) AS conflicts_with,
       collect(DISTINCT [g.t0, g.t1]) AS gaps
"""

# Q8. The scoreboard. CONTRADICTS is matched undirected, so without DISTINCT on
# pair_id every contradiction would be counted twice, once from each endpoint.
#
# The rule, stated once: **a contradiction counts once per suspect who made
# either claim.** Both speakers in a contradicting pair carry it.
#
# `originated_ungrounded` and `carried_ungrounded` come from the referee's
# provenance trace (5.7), materialized as TRACED_TO. They are counted by the
# traced claim's id, so one claim contributes at most one of each per suspect.
# The distinction is the whole point: a suspect the chain *ends* at is the
# origin of the ungrounded account as far as the referee can see, while a
# suspect that merely passed it on is a link. Separating them is what stops
# an honest repeater being scored like a source.
#
# `self_contradictions` is split out from `contradictions` because spec 5.12's
# anonymous `(c)-[x:CONTRADICTS]-(:Claim)` scores a suspect who contradicts
# themselves identically to one contradicted by someone else, and internal
# inconsistency is the stronger signal. Splitting it needs the other claim's
# speaker bound, which the spec query does not do. CASE inside
# collect(DISTINCT ...) was verified against v4.22.1 after the M0 gate; collect
# skips the nulls, so each branch counts only its own kind.
SCOREBOARD = """
MATCH (s:Suspect)
OPTIONAL MATCH (c:Claim)-[:BY]->(s)
OPTIONAL MATCH (c)-[x:CONTRADICTS]-(o:Claim)-[:BY]->(os:Suspect)
OPTIONAL MATCH (c)-[:HAS_GAP]->(g:Gap)
OPTIONAL MATCH (tc:Claim)-[t:TRACED_TO]->(s)
WITH s,
     collect(DISTINCT c.id) AS claim_ids,
     collect(DISTINCT CASE WHEN os.id  = s.id THEN x.pair_id END) AS self_ids,
     collect(DISTINCT CASE WHEN os.id <> s.id THEN x.pair_id END) AS other_ids,
     collect(DISTINCT id(g)) AS gap_ids,
     collect(DISTINCT CASE WHEN t.role = 'origin'  AND t.ungrounded = true
                           THEN tc.id END) AS originated_ids,
     collect(DISTINCT CASE WHEN t.role = 'carrier' AND t.ungrounded = true
                           THEN tc.id END) AS carried_ids
RETURN s.id AS suspect,
       size(claim_ids)     AS claims,
       size(self_ids)      AS self_contradictions,
       size(other_ids)     AS other_contradictions,
       size(gap_ids)       AS gaps,
       size(originated_ids) AS originated_ungrounded,
       size(carried_ids)    AS carried_ungrounded
ORDER BY originated_ungrounded DESC, self_contradictions DESC,
         other_contradictions DESC, gaps DESC, suspect
"""

# How each verdict is represented across the case, for the eval summary.
VERDICT_TALLY = """
MATCH (c:Claim)
RETURN c.verdict AS verdict, count(c) AS n
ORDER BY verdict
"""

# Every contradiction with its kind, for the detective's list_contradictions.
ALL_CONTRADICTIONS = """
MATCH (a:Claim)-[x:CONTRADICTS]->(b:Claim)
MATCH (a)-[:BY]->(sa:Suspect), (b)-[:BY]->(sb:Suspect)
MATCH (a)-[:ABOUT]->(p:Suspect)
RETURN x.pair_id AS pair_id, x.kind AS kind, a.id AS a, b.id AS b,
       sa.id AS speaker_a, sb.id AS speaker_b, p.id AS subject,
       x.gap AS gap, x.needed AS needed
ORDER BY x.pair_id
"""

# -- readers the case board needs --------------------------------------------
# These answer display questions the audit itself never asks. They read the
# public case graph only; nothing here can reach a mind or `world:{seed}`.

# Every suspect in the case file, with the name to print.
ALL_SUSPECTS = """
MATCH (s:Suspect)
RETURN s.id AS id, s.name AS name
ORDER BY s.id
"""

# Every corridor on the public floor plan, once per pair, with its walk in minutes.
ALL_ADJACENCY = """
MATCH (a:Place)-[r:ADJACENT_TO]->(b:Place)
WHERE a.id < b.id
RETURN a.id AS a, b.id AS b, r.minutes AS minutes
ORDER BY a.id, b.id
"""

# The incident under investigation: where it happened and over which window.
INCIDENT = """
MATCH (i:Incident)
RETURN i.id AS id, i.place AS place, i.t0 AS t0, i.t1 AS t1
ORDER BY i.id
"""

# Every supporting evidence shadow in the case, with the slice of the claim it covers.
ALL_SUPPORT_SHADOWS = """
MATCH (c:Claim)-[r:SUPPORTED_BY]->(e:Evidence)
RETURN c.id AS claim_id, e.id AS id, e.fact_id AS fact_id, e.src AS src,
       e.place AS place, e.agent AS agent, e.t0 AS t0, e.t1 AS t1,
       r.covers_t0 AS covers_t0, r.covers_t1 AS covers_t1
ORDER BY c.id, r.covers_t0, e.id
"""

# Every conflicting evidence shadow in the case.
ALL_CONFLICT_SHADOWS = """
MATCH (c:Claim)-[:CONFLICTS_WITH]->(e:Evidence)
RETURN c.id AS claim_id, e.id AS id, e.fact_id AS fact_id, e.src AS src,
       e.place AS place, e.agent AS agent, e.t0 AS t0, e.t1 AS t1
ORDER BY c.id, e.t0, e.id
"""

# Every span of a claim that nothing in its speaker's memory accounted for.
ALL_GAPS = """
MATCH (c:Claim)-[:HAS_GAP]->(g:Gap)
RETURN c.id AS claim_id, g.t0 AS t0, g.t1 AS t1
ORDER BY c.id, g.t0, g.t1
"""

# -- readers the detective's tools need --------------------------------------
# All over the public case graph. None of them can reach a mind, and none takes
# a graph name: the seed is bound when `CaseGraph` is constructed.

# Which spans of which claims did a suspect's own memory not account for?
# `$suspect` is optional — null asks it of every suspect at once. This is
# `list_gaps`, the tool that hands the detective spans worth asking about.
GAPS_BY_SPEAKER = """
MATCH (c:Claim)-[:HAS_GAP]->(g:Gap), (c)-[:BY]->(s:Suspect),
      (c)-[:ABOUT]->(p:Suspect), (c)-[:AT]->(l:Place)
WHERE $suspect IS NULL OR s.id = $suspect
RETURN s.id AS speaker, c.id AS claim_id, p.id AS subject, l.id AS place,
       g.t0 AS t0, g.t1 AS t1
ORDER BY s.id, g.t0, g.t1, c.id
"""

# Which spans of this one claim went unaccounted for?
GAPS_FOR_CLAIM = """
MATCH (c:Claim {id:$claim_id})-[:HAS_GAP]->(g:Gap)
RETURN g.t0 AS t0, g.t1 AS t1
ORDER BY g.t0, g.t1
"""

# Which redacted shadows support this one claim, and what do they cover of it?
SUPPORT_SHADOWS_FOR_CLAIM = """
MATCH (c:Claim {id:$claim_id})-[r:SUPPORTED_BY]->(e:Evidence)
RETURN e.id AS id, e.fact_id AS fact_id, e.src AS src, e.place AS place,
       e.agent AS agent, e.t0 AS t0, e.t1 AS t1,
       r.covers_t0 AS covers_t0, r.covers_t1 AS covers_t1
ORDER BY r.covers_t0, e.id
"""

# Which redacted shadows conflict with this one claim?
CONFLICT_SHADOWS_FOR_CLAIM = """
MATCH (c:Claim {id:$claim_id})-[:CONFLICTS_WITH]->(e:Evidence)
RETURN e.id AS id, e.fact_id AS fact_id, e.src AS src, e.place AS place,
       e.agent AS agent, e.t0 AS t0, e.t1 AS t1
ORDER BY e.t0, e.id
"""

# What is the latest turn recorded in the case? A follow-up interview's claims
# are numbered after it, so turn order stays the order things were said in.
LATEST_TURN = """
MATCH (c:Claim)
RETURN max(c.turn) AS turn
"""
