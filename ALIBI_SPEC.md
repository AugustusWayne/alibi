# ALIBI — Every claim needs a path

Build spec **v2** for **Graph Hacks: Context for AI Agents** (FalkorDB x WeMakeDevs).
Window: **Oct 15 12:01 AM IST → Oct 18 11:59 PM IST**. Solo entry.
Tracks to name at submission: **Track 02 Agent Memory and Coordination** (primary), **Track 01 Agents That Act on Connected Data** (secondary).

> Working name and setting are placeholders. The world is theme-neutral (Person, Place, Fact). Skin it after the design research.

---

## 0. What changed from v1, and why

v1 had an audit engine that could have returned wrong verdicts — the one thing this project promises not to do. Eight changes:

| # | Change | Reason |
|---|---|---|
| 1 | Five verdict states; **intent moved out of the verdict** into referee-only ground-truth labels | A missing memory is not proof of lying. The graph can prove a claim is ungrounded; it cannot prove intent. |
| 2 | **Coverage semantics** with claim modality, and uncovered spans materialized as `Gap` nodes | Interval overlap is not interval coverage. A 12-minute hole in an alibi is the strongest lead in the system, not a rounding error. |
| 3 | **Transmission nodes** with stable IDs, `learned_at` on facts, and temporal chain checks | "X told me" needs a checkable provenance record, and a source must have known the thing before passing it on. |
| 4 | `SUPPORTED_BY` / `CONFLICTS_WITH` edges materialized by the audit | Makes "every claim needs a path" literally true in the graph instead of a slogan. |
| 5 | **Aggregate all evidence, then decide.** No `LIMIT 1`, no first-match precedence | v1 returned `supported` if any supporting fact existed, even alongside a contradicting one. Worst bug in v1. |
| 6 | Oracle solves from **ground truth**, seeds frozen before tuning, rejection rate reported | v1's oracle used the same graph reasoning as the detective, so world selection favored the graph detective. |
| 7 | **Server-bound memory isolation** with a test that proves it | Separate graphs are not a boundary if any tool can name any graph. |
| 8 | **Audit precision/recall per claim is the headline metric**; case accuracy is secondary with a Wilson CI | 20 cases gives roughly ±20pp — too wide to support a claim. ~2000 claims gives tight intervals and measures the actual contribution. |

Also: half-open intervals throughout; precomputed travel matrix for the bulk audit with live `algo.SPpaths` for the demo; scripted suspects built before LLM suspects; a second non-mystery fixture; a backup demo video at hour 80.

---

## 1. Thesis

Multi-agent systems have a trust problem: agents pass claims to each other, and nothing checks whether a claim is grounded in what the speaker could actually know.

**Alibi gives every agent a private memory graph in FalkorDB and audits every claim against it.** A claim is only as good as its support path. No path means the claim is ungrounded. A path that dead-ends in another agent's ungrounded claim is a rumor, and the graph traces it back to where it started.

The test world is a mystery: several suspect agents with private minds, one or more of whom fabricate, and a detective agent that must find the culprit using only what the suspects say. The detective uses graph tools; the graph computes the checks, the LLM asks the questions. The mystery is the testbed. The reusable product is the **Epistemic Audit**: `audit(agent, claim) -> verdict + support path + gaps`.

### The claim we make, and the claim we do not

**We claim:** the graph can decide, deterministically and inspectably, whether an agent's statement is grounded in that agent's own memory, where the support came from, and what part of the statement nothing accounts for.

**We do not claim:** that an ungrounded statement is a lie. Intent is unknowable from memory alone — an agent may have forgotten, never observed, or been misinformed. In this project intent is knowable only because we generated the world, and ground truth is used **solely for scoring**, never fed to the detective and never part of a verdict.

That distinction is the strongest thing in the project. Lead with it. It is also the blog post for the side prize.

### Differentiators (say these in the README and the video)
1. **Isolated minds, one graph each.** Per-agent graphs in one FalkorDB instance, with access bound server-side so an agent physically cannot query another's memory.
2. **Audit by path, not by LLM judge.** Verdicts come from Cypher plus a deterministic decision table. No model grades another model.
3. **Gaps as leads.** Partial support is reported as the exact uncovered spans, and the detective interrogates them: *"Nobody saw you for the first twelve minutes. Where were you?"*
4. **Origin vs repetition.** Hearsay chains are traced across minds through stable transmission records to the origin of the ungrounded claim, so an honest agent who repeated something false is told apart from whoever started it.
5. **Physics, not vibes.** Alibi feasibility is checked with weighted shortest paths over the floor-plan graph: "kitchen until 21:05, study at 21:10, but the walk is 9 minutes."
6. **A measured result.** Audit precision and recall over thousands of claims, plus a detective comparison. Report whatever the numbers are.

### Design rule
A belief-graph paper on the card game Hanabi found graphs added little when pasted into a prompt, but helped substantially when they **gated the agent's choices** with a computed shortlist. Different task, so treat it as a design hint, not proof. Here: the graph computes the checks and the shortlist; the LLM chooses what to ask and how to explain it.

---

## 2. Hackathon requirements (do not lose points here)

- FalkorDB is the primary database and central to the product. Remove it and nothing works. Audit, coverage, contradiction, travel and provenance queries all run in FalkorDB.
- Data is **synthetic** (procedurally generated worlds). Nothing private or scraped.
- Main coding starts after Oct 15 12:01 AM IST.
- AI coding assistants must be **disclosed**: keep `AI-USE.md` from commit one, updated every session.
- You must be able to explain the graph model, queries and architecture. Read every query before it merges.
- Submission needs: public repo; README with setup **and graph data model**; the Cypher queries/algorithms the product depends on; demo video; live deployment **or** full local setup; the track(s) entered.

---

## 3. Architecture

```
 Web UI (React + TypeScript + Vite, D3 canvas/SVG)
        ^  SSE stream of events
        |
 FastAPI orchestrator (Python 3.12)
   |- Simulation engine ... world generator, event log, frozen seeds
   |- Mind writer ......... world events -> per-agent facts + transmissions
   |- MindAccess .......... the ONLY path to a mind graph; agent id bound server-side
   |- Audit engine ........ evidence gather -> coverage -> decision table -> materialize
   |- Agent runtime ....... scripted or LLM suspects + detective (model client)
   |- Referee ............. provenance trace, ground-truth scoring (no LLM)
   |- Eval harness ........ frozen seeds x detective variants
   |- LLM cache ........... SQLite keyed by (seed, agent, prompt hash)
        |
 FalkorDB (Docker, falkordb/falkordb)
   graphs:  world:{seed}            ground truth (referee only)
            mind:{seed}:{agent}     one per suspect, private
            case:{seed}             detective's case file (public info only)
```

**Stack.** Python 3.12 + FastAPI + official `falkordb` client; model client (small model for suspects, larger for the detective, hard per-case call cap in code); React + TypeScript + Vite + D3; Docker Compose; SQLite for the LLM replay cache and eval metadata only, never for graph state.

Direct typed tool calls first. MCP (FastMCP) is an extension, added only once the core tools work.

> **Open decision, reversible until hour 8:** backend language. Python wins on simulation, interval merging, evaluation and statistics, and the frontend is TypeScript regardless. There is an official Node client if you would rather be in one language end to end — say so before M1 starts, not at hour 20.

---

## 4. Graph model

### 4.0 Time contract (write this down once; test the boundaries)

- Tick = integer minutes since 18:00, range 0 to 300.
- **All intervals are half-open `[t0, t1)`.** Presence over `[t0, t1)` means present from `t0` up to but not including `t1`.
- Two intervals overlap iff `a.t0 < b.t1 AND b.t0 < a.t1`. Note the **strict** inequalities. v1 used inclusive comparisons and would report adjacent intervals as overlapping.
- **Travel rule.** A claim of presence at A over `[a.t0, a.t1)` followed by presence at B over `[b.t0, b.t1)` is feasible iff `a.t1 + travel(A,B) <= b.t0`. So it is **impossible** iff `b.t0 - a.t1 < travel(A,B)`.
- Claims at different places whose intervals overlap are not a travel problem, they are a two-places-at-once problem. The exclusive-presence check and the travel check therefore partition the cases cleanly, and a test asserts no claim pair is flagged by both.
- Required boundary tests: a journey with exactly enough time (feasible), a journey one tick short (impossible), two intervals touching at a point (not overlapping), two intervals overlapping by one tick (overlapping).

### 4.1 `world:{seed}` (ground truth, referee only)
| Element | Properties |
|---|---|
| `(:Place)` | id, name |
| `(:Person)` | id, name, role (`honest` / `culprit` / `accomplice`) |
| `(:Place)-[:ADJACENT_TO {minutes}]->(:Place)` | symmetric: write both directions |
| `(:Presence)` | person, place, t0, t1 — true route segments |
| `(:Incident)` | id, place, t0, t1 |
| `(:PlantedFabrication)` | claim_key, by_person, reason — the generator's record of what it instructed an agent to fabricate |

`PlantedFabrication` is what makes deception labels possible without guessing. It is referee-only and never leaves the scoring path.

### 4.2 `mind:{seed}:{agent}` (private; the agent recalls only from here)
| Element | Properties |
|---|---|
| `(:Person)`, `(:Place)` | id, name |
| `(:Fact)` | id, kind (`saw`/`did`/`found`/`heard`), **src** (`witnessed`/`hearsay`/`inferred`), t0, t1, **learned_at** |
| `(:Fact)-[:ABOUT]->(:Person)` | who the fact is about |
| `(:Fact)-[:AT]->(:Place)` | where |
| `(:Fact)-[:VIA]->(:Transmission)` | hearsay only: the transfer that produced this fact |
| `(:Fact)-[:DERIVED_FROM]->(:Fact)` | inferred facts only |
| `(:Transmission)` | id, tick, **src_agent**, **src_fact_id** |
| `(:Transmission)-[:FROM]->(:Person)` | who spoke |

**`learned_at` matters.** A fact *about* 21:00 may have been *learned* at 21:30. Witnessed facts have `learned_at = t0`. Hearsay facts have `learned_at =` the transmission tick. Without this field the chain temporal check is impossible.

**Cross-graph references are soft, by design.** `Transmission.src_fact_id` points at a fact in *another* graph. FalkorDB graphs are isolated, so there is no edge across them — that isolation is the architecture, not a limitation. The referee resolves these references by switching graphs, which is exactly why only the referee can trace a chain.

### 4.3 `case:{seed}` (detective's file; public information only)
| Element | Properties |
|---|---|
| `(:Place)` | id, name |
| `(:Place)-[:ADJACENT_TO {minutes}]->(:Place)` | public floor plan (for display and the live demo path) |
| `(:Place)-[:TRAVEL_TIME {minutes}]->(:Place)` | all-pairs matrix, precomputed once per world (see Q6) |
| `(:Suspect)` | id, name |
| `(:Claim)` | id, t0, t1, turn, **modality**, **verdict**, coverage, uncovered |
| `(:Claim)-[:BY]->(:Suspect)` | speaker |
| `(:Claim)-[:ABOUT]->(:Suspect)` | subject |
| `(:Claim)-[:AT]->(:Place)` | claimed location |
| `(:Claim)-[:RELAYED_FROM]->(:Suspect)` | the speaker says they were told this |
| `(:Claim)-[:SUPPORTED_BY {covers_t0, covers_t1}]->(:Evidence)` | materialized by the audit |
| `(:Claim)-[:CONFLICTS_WITH]->(:Evidence)` | materialized by the audit |
| `(:Claim)-[:HAS_GAP]->(:Gap)` | uncovered spans |
| `(:Gap)` | t0, t1 |
| `(:Evidence)` | id, fact_id, src, t0, t1, place, agent — a public shadow of a private fact, created only when an audit cites it |
| `(:Claim)-[:CONTRADICTS {kind, pair_id, gap, needed}]->(:Claim)` | kind = `exclusive_presence` / `impossible_travel` |
| `(:Claim)-[:CORROBORATES {pair_id}]->(:Claim)` | different speakers, same subject/place/overlapping time |
| `(:Suspect)-[:AGREES_WITH {n}]->(:Suspect)` | derived from corroboration (stretch) |
| `(:Incident)` | id, place, t0, t1 |

**`Evidence` nodes are the privacy seam.** The case graph must stay public-information-only, but the audit must be inspectable. So when an audit cites a private fact, it creates a redacted public shadow of it in the case graph. The detective sees that a claim is supported by an observation at a place and time; it does not get a window into the suspect's whole mind. This is what makes `SUPPORTED_BY` a real path without leaking memory.

**Rules for the coding assistant:** one relationship type per traversal purpose; keep claims short (<= 15 ticks); reference relationship aliases in any query that counts edges (known FalkorDB limitation: an unreferenced relationship is only existence-checked); never store arrays as properties without spiking it first.

---

## 5. The audit engine (build this first)

This is the technical contribution. If it is not trustworthy, nothing else matters.

### 5.1 Claim modality

Every claim carries a modality, set by the suspect's structured `testify` call:

| Modality | Meaning | Support rule |
|---|---|---|
| `THROUGHOUT` | "I was in the kitchen the whole time 21:00–21:15" | Witnessed support must **cover** the whole claimed interval |
| `AT_SOME_POINT` | "I was in the kitchen at some point in that window" | Any witnessed overlap suffices |

Default is `THROUGHOUT` for alibi claims, which is the interesting case. Uncovered spans become `Gap` nodes and are the detective's best questions.

### 5.2 Q1. Write a fact into a mind

```cypher
MERGE (p:Person {id:$subject})
MERGE (l:Place {id:$place})
CREATE (f:Fact {id:$id, kind:$kind, src:$src, t0:$t0, t1:$t1, learned_at:$learned_at})
CREATE (f)-[:ABOUT]->(p)
CREATE (f)-[:AT]->(l)
```

Hearsay additionally creates the transmission record:
```cypher
MATCH (f:Fact {id:$id})
MERGE (r:Person {id:$src_agent})
CREATE (tr:Transmission {id:$transmission_id, tick:$tick,
                         src_agent:$src_agent, src_fact_id:$src_fact_id})
CREATE (f)-[:VIA]->(tr)
CREATE (tr)-[:FROM]->(r)
```

### 5.3 Q2. Gather **all** evidence for a claim (one query, no `LIMIT`)

Run inside the speaker's mind graph. Returns every temporally overlapping fact about the subject — both same-place (potential support) and different-place (potential conflict). The decision happens afterwards, in Python, over the whole set.

```cypher
MATCH (f:Fact)-[:ABOUT]->(:Person {id:$subject}), (f)-[:AT]->(l:Place)
WHERE f.t0 < $t1 AND $t0 < f.t1
OPTIONAL MATCH (f)-[:VIA]->(tr:Transmission)-[:FROM]->(src:Person)
RETURN f.id AS fact_id, f.src AS src, f.t0 AS t0, f.t1 AS t1,
       f.learned_at AS learned_at,
       l.id AS place, (l.id = $place) AS same_place,
       tr.id AS transmission_id, tr.src_agent AS heard_from,
       tr.src_fact_id AS src_fact_id, tr.tick AS heard_tick
ORDER BY f.t0
```

This single query replaces v1's Q2a/Q2b/Q2c. Those used `LIMIT 1`, which picked an arbitrary fact when several matched, and ran in a precedence order that let one supporting fact mask a contradicting one.

### 5.4 Coverage computation (Python, ~15 lines, deterministic)

```python
def coverage(claim_t0, claim_t1, intervals):
    """intervals: witnessed, same-place facts overlapping the claim window.
    Returns (covered_minutes, gaps) with gaps as half-open spans.
    Intervals may overlap each other, so they MUST be merged before summing."""
    spans = sorted((max(a, claim_t0), min(b, claim_t1)) for a, b in intervals)
    spans = [(a, b) for a, b in spans if a < b]        # drop empty / out-of-window
    merged = []
    for a, b in spans:
        if merged and a <= merged[-1][1]:              # touching or overlapping
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    gaps, cursor = [], claim_t0
    for a, b in merged:
        if a > cursor:
            gaps.append((cursor, a))
        cursor = b
    if cursor < claim_t1:
        gaps.append((cursor, claim_t1))
    return sum(b - a for a, b in merged), gaps
```

**Merge before summing.** Two witnessed facts covering 21:00–21:10 and 21:05–21:15 cover 15 minutes, not 20. Summing unmerged spans can push coverage above the claim length and silently promote a partially-supported claim to `SUPPORTED` — the exact class of bug this rewrite exists to remove.

`tests/test_coverage.py` must cover all eleven cases, which are verified to pass against the function above:

| Case | Claim | Witnessed spans | covered | gaps |
|---|---|---|---|---|
| full | [0,15) | (0,15) | 15 | — |
| partial tail | [0,15) | (12,15) | 3 | (0,12) |
| union to full | [0,15) | (0,8),(8,15) | 15 | — |
| middle gap | [0,15) | (0,5),(10,15) | 10 | (5,10) |
| no evidence | [0,15) | — | 0 | (0,15) |
| **overlapping** | [0,15) | (0,10),(5,15) | **15** | — |
| fact overruns claim | [5,10) | (0,20) | 5 | — |
| two gaps | [0,20) | (5,10) | 5 | (0,5),(10,20) |
| unsorted input | [0,15) | (10,15),(0,5) | 10 | (5,10) |
| touching spans | [0,15) | (0,7),(7,15) | 15 | — |
| entirely outside | [0,15) | (20,25) | 0 | (0,15) |

Interval union is awkward in the OpenCypher subset and trivial here. The decision stays deterministic code — this is arithmetic, not judgement — and the **result is written back into the graph**, so the graph remains the system of record.

### 5.5 The decision table (the only place a verdict is produced)

Evaluated over the **complete** evidence set, in this order. There is no first-match shortcut.

| Condition | Verdict |
|---|---|
| A witnessed fact places the subject at a **different** place, overlapping the claim | `CONTRADICTED` |
| No overlapping facts at all | `UNSUPPORTED` |
| Witnessed same-place coverage satisfies the modality | `SUPPORTED` |
| Witnessed same-place support exists but is **partial** (THROUGHOUT only) | `INDETERMINATE` + `Gap` nodes |
| No witnessed support, but hearsay support exists | `HEARSAY` + provenance chain |
| Anything else (ambiguous or unresolvable evidence) | `INDETERMINATE` |

Two rules that follow, and that v1 got wrong:
- **Conflict beats support.** A claim with both a supporting and a conflicting witnessed memory is `CONTRADICTED`, and **both** evidence sets are retained on the claim. v1 returned `supported` and hid the conflict.
- **Partial is not full.** A THROUGHOUT claim with 3 of 15 minutes witnessed is `INDETERMINATE` with a 12-minute `Gap`, never `SUPPORTED`.

Verdicts describe **grounding, not intent.** None of these five states means "lie".

### 5.6 Materialize the audit into the case graph

```cypher
MATCH (c:Claim {id:$claim_id})
MERGE (e:Evidence {id:$evidence_id})
  ON CREATE SET e.fact_id = $fact_id, e.src = $src, e.t0 = $t0, e.t1 = $t1,
                e.place = $place, e.agent = $agent
MERGE (c)-[r:SUPPORTED_BY]->(e)
SET r.covers_t0 = $covers_t0, r.covers_t1 = $covers_t1
```

```cypher
MATCH (c:Claim {id:$claim_id})
CREATE (g:Gap {t0:$g0, t1:$g1})
CREATE (c)-[:HAS_GAP]->(g)
```

```cypher
MATCH (c:Claim {id:$claim_id})
SET c.verdict = $verdict, c.coverage = $coverage, c.uncovered = $uncovered
```

After this, "every claim needs a path" is literally true: select any claim in the UI and walk `SUPPORTED_BY` to the evidence that grounds it, or `HAS_GAP` to what nothing accounts for.

### 5.7 Q3. Provenance trace (crosses graphs, referee only)

Hearsay verdicts get a chain. The referee starts in the speaker's mind, reads the `Transmission` that produced the supporting fact, follows `src_agent` + `src_fact_id` into that agent's graph, and audits the same claim there. Repeat.

Per hop, record: agent, fact id, transmission id, tick, verdict. Terminate on:

| Terminal state | Meaning |
|---|---|
| `ORIGIN_WITNESSED` | the chain ends in someone who actually saw it — honest chain |
| `ORIGIN_UNSUPPORTED` | the chain ends in an agent with no supporting memory — origin of the ungrounded claim |
| `ORIGIN_CONTRADICTED` | the chain ends in an agent whose own memory conflicts with what they passed on |
| `CHAIN_BROKEN` | the referenced source fact does not exist — the source never recorded it |
| `CHAIN_TEMPORAL_VIOLATION` | a transmission precedes the moment its source learned the fact |
| `CHAIN_TOO_DEEP` | depth cap of 5 reached |
| `CHAIN_CYCLE` | visited set hit |

**Temporal consistency check.** At each hop, assert `source_fact.learned_at <= transmission.tick`. A violation means the speaker named a source who could not yet have known — a checkable lie about provenance, and a genuinely novel finding this schema makes possible.

**Honesty about what the chain proves.** `ORIGIN_UNSUPPORTED` identifies the origin **of the chain we can see**, not necessarily the fabricator. `CHAIN_BROKEN` is ambiguous: the intermediate agent may have fabricated, or may simply never have recorded what they were told. Both outcomes are reported as named states, and **origin-identification accuracy is measured against ground truth** (section 8) rather than asserted.

### 5.8 Q4. Ingest a claim

```cypher
MERGE (s:Suspect {id:$speaker})
MERGE (p:Suspect {id:$subject})
MERGE (l:Place {id:$place})
CREATE (c:Claim {id:$id, t0:$t0, t1:$t1, turn:$turn,
                 modality:$modality, verdict:'PENDING',
                 coverage:0.0, uncovered:0})
CREATE (c)-[:BY]->(s)
CREATE (c)-[:ABOUT]->(p)
CREATE (c)-[:AT]->(l)
```

### 5.9 Q5. Exclusive-presence contradictions

```cypher
MATCH (a:Claim)-[:ABOUT]->(p:Suspect)<-[:ABOUT]-(b:Claim),
      (a)-[:AT]->(la:Place), (b)-[:AT]->(lb:Place)
WHERE a.id < b.id AND la.id <> lb.id
  AND a.t0 < b.t1 AND b.t0 < a.t1
MERGE (a)-[c:CONTRADICTS {kind:'exclusive_presence', pair_id: a.id + '|' + b.id}]->(b)
RETURN a.id AS a, b.id AS b
```

Strict inequalities, per the time contract. `pair_id` exists so the scoreboard can count distinct contradictions without relying on internal relationship ids.

### 5.10 Q6. Impossible travel

**Two uses of weighted shortest path, both real.**

*Build time, once per world:* compute the all-pairs travel matrix with `algo.SPpaths` over the floor plan (10–12 places, so at most ~144 one-off calls) and store it as `TRAVEL_TIME` edges in the case graph.

```cypher
MATCH (la:Place {id:$a}), (lb:Place {id:$b})
CALL algo.SPpaths({sourceNode: la, targetNode: lb, relTypes: ['ADJACENT_TO'],
                   weightProp: 'minutes', relDirection: 'both'})
YIELD path, pathWeight
RETURN pathWeight, [n IN nodes(path) | n.id] AS route
```

> **Corrected at M0 (spike 8).** This snippet originally passed `sourceNode: $la`
> as a string parameter, which FalkorDB v4.22.1 rejects with
> `sourceNode and targetNode must be of type Node`. The `MATCH` prefix above is
> required: `algo.SPpaths` takes bound node values, not ids. Verified working
> form: `SPPATHS_MATCHED` in `scripts/spikes.py`.

*Audit time:* a single query with no per-row procedure call.

```cypher
MATCH (a:Claim)-[:ABOUT]->(p:Suspect)<-[:ABOUT]-(b:Claim),
      (a)-[:AT]->(la:Place), (b)-[:AT]->(lb:Place),
      (la)-[tt:TRAVEL_TIME]->(lb)
WHERE a.id <> b.id AND la.id <> lb.id
  AND a.t1 <= b.t0
  AND (b.t0 - a.t1) < tt.minutes
MERGE (a)-[c:CONTRADICTS {kind:'impossible_travel', pair_id: a.id + '|' + b.id}]->(b)
SET c.gap = b.t0 - a.t1, c.needed = tt.minutes
RETURN a.id AS a, b.id AS b, (b.t0 - a.t1) AS gap, tt.minutes AS needed
```

This removes v1's biggest schedule risk — calling a procedure once per matched row, which is unverified — while keeping `algo.SPpaths` genuinely load-bearing. For the demo, call it live on the flagged pair and **render the actual route on the floor plan**. Showing the corridor-by-corridor path beats showing a number.

### 5.11 Q7. Corroboration

```cypher
MATCH (a:Claim)-[:BY]->(sa:Suspect), (b:Claim)-[:BY]->(sb:Suspect),
      (a)-[:ABOUT]->(p:Suspect), (b)-[:ABOUT]->(p),
      (a)-[:AT]->(l:Place), (b)-[:AT]->(l)
WHERE a.id < b.id AND sa.id <> sb.id
  AND a.t0 < b.t1 AND b.t0 < a.t1
MERGE (a)-[c:CORROBORATES {pair_id: a.id + '|' + b.id}]->(b)
RETURN a.id AS a, b.id AS b
```

### 5.12 Q8. Suspect scoreboard (no double counting)

```cypher
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
```

`CONTRADICTS` is undirected in the match, so without `DISTINCT` on `pair_id` each contradiction is counted from both endpoints. Define the rule once in a docstring — **a contradiction counts once per suspect who made either claim** — and unit-test the aggregation against a hand-built graph with known answers.

Weights for the ranking live in **one** Python function, and the UI shows the breakdown rather than only the total.

### 5.13 Q9. Coalitions (stretch; first on the cut list)

```cypher
CALL algo.labelPropagation({nodeLabels:['Suspect'], relationshipTypes:['AGREES_WITH']})
YIELD node, communityId
RETURN communityId, collect(node.id) AS members
```
CDLP processes nodes in random order, so run it 3 times and keep only stable groupings.

### 5.14 Q10. What-if fork (stretch)

```python
fork = case_graph.copy(f"case:{seed}:whatif")
fork.query("MATCH (c:Claim)-[:BY]->(:Suspect {id:$s}) DELETE c", {"s": suspect_id})
# rerun Q5-Q8 on the fork, diff the scoreboard, then delete the fork
```

### Algorithms used
| Algorithm | Role | Priority |
|---|---|---|
| Multi-graph isolation | private minds, case file, ground truth | must |
| `algo.SPpaths` (weighted) | travel matrix + live demo route | must |
| Variable-length paths, named paths | provenance and support traversal | must |
| `algo.labelPropagation` | alibi rings | could |
| `algo.betweenness` | hearsay brokers | could |
| `GRAPH.COPY` | counterfactual fork | could |

---

## 6. Memory isolation (application-enforced, and tested)

Separate graphs are not a boundary if any caller can name any graph.

```python
class MindAccess:
    """The only way to reach a mind graph. Agent identity is bound at construction
    by the orchestrator, never passed in by the caller."""
    def __init__(self, db, seed: str, agent_id: str):
        self._graph = db.select_graph(f"mind:{seed}:{agent_id}")
        self._agent_id = agent_id

    def recall(self, subject=None, place=None, t_range=None): ...
```

Rules:
- **No tool exposed to any agent accepts a graph name, an agent id, or anything resolving to one.** A suspect's `recall` tool has no parameter that could select another mind.
- Only the referee may construct a `MindAccess` for an agent other than itself, and only the referee runs the provenance trace.
- `tests/test_isolation.py` must assert: (a) a fact existing only in B's graph is unreachable through A's tool surface; (b) no public tool signature accepts a graph name; (c) the trace is reachable only via the referee.

Describe this in the README as **application-enforced isolation, not a security boundary** — one process, shared credentials. Overclaiming here would be the same error the project exists to criticise. A passing isolation test is a concrete, demo-able artifact for Track 02's "separate memory per tenant/agent" bullet.

---

## 7. Agents

### Suspects — scripted first, LLM second

**Build scripted suspects first.** They answer deterministically from `recall`, with a configurable fabrication policy. This makes the whole audit engine testable with zero LLM calls, zero cost and zero flakiness, and it stays in the repo as `--scripted` mode for CI and as insurance.

**Then add LLM suspects, and keep them.** A world where only the detective is a model is a single-agent system with a scripted environment, and Track 02 is about multi-agent memory and coordination. LLM suspects also produce *real* accidental fabrication — claims with no backing memory, arising from the model rather than injected by us — which is precisely the phenomenon the audit engine exists to detect. Injected fake lies would prove nothing.

Determinism is handled by the **LLM cache**, not by removing the models: every call is keyed by `(seed, agent, prompt_hash)` in SQLite. The first run costs money and varies; every run after that — the demo and the entire benchmark — replays bit-identically. Interviews are sequential and on demand, so only suspects actually interviewed cost anything.

- Tools: `recall(subject?, place?, t_range?)` over its own mind only; `testify(claims[])` with each claim structured as `{subject, place, t0, t1, modality, relayed_from?}`.
- Honest suspects answer from recall. The culprit and any accomplice have a persona permitting specific fabrications, each recorded as a `PlantedFabrication` in the world graph.
- Structured claims mean no NLU is needed to audit.

### Detective (larger model)

Typed tools, backed by the case graph: `interview(suspect, question)`, `list_contradictions()`, `list_gaps(suspect?)`, `check_travel(place_a, place_b)`, `rank_suspects()`, `polygraph(suspect, claim_id)` (budget: 2), `accuse(suspect, rationale)`.

`polygraph` is the only door into a mind, and it returns a **verdict plus evidence shadows and gaps** — never raw memory, never a ground-truth label, never the word "lie".

`list_gaps` is the sleeper tool: it hands the detective the exact unaccounted-for spans to interrogate.

### Referee (no LLM)

Audit, provenance trace, ground-truth scoring. Never let an LLM compute a verdict. Models write testimony and ask questions; Cypher and the decision table decide.

---

## 8. Evaluation

### 8.1 Ground-truth labels (referee only, scoring only)

Computed from `world:{seed}` and `PlantedFabrication`, never shown to the detective:

| Label | Meaning |
|---|---|
| `TRUE_CLAIM` | matches world ground truth |
| `DELIBERATE_FABRICATION` | the generator instructed this agent to assert this falsehood |
| `RELAYED_FALSEHOOD` | false, and the speaker's support traces to a false origin |
| `HONEST_ERROR` | false, speaker had no contrary memory and was not instructed to fabricate (includes model hallucination) |

The split between `DELIBERATE_FABRICATION` and `HONEST_ERROR` is the measurement that justifies the whole thesis: it shows how often an ungrounded verdict corresponds to actual deception, which is the number nobody can produce in a real deployment.

### 8.2 Primary metric — audit quality per claim

20 seeds × 7 suspects × 10–20 claims gives roughly **1,400–2,800 labelled claims**, so these intervals are tight:

- **Grounding detection:** precision/recall for identifying ungrounded claims (`UNSUPPORTED` ∪ `CONTRADICTED`) against the labels above.
- **Falsehood detection:** precision/recall for identifying false claims, reported separately. The gap between these two numbers *is* the "grounded ≠ true" result.
- **Full confusion matrix** of the five verdicts against the four labels.
- **Origin identification:** when a chain terminates `ORIGIN_UNSUPPORTED`, how often is that agent the actual fabricator? Report `CHAIN_BROKEN` and `CHAIN_TEMPORAL_VIOLATION` rates alongside.
- **Gap precision:** when the audit reports a gap, how often does the subject's true route place them elsewhere during it?

### 8.3 Secondary metric — detective comparison

Over the same frozen seeds, identical testimony:
- **A. Transcript detective** — full transcript in context, no graph tools.
- **B. Retrieval detective** (optional, first to cut) — keyword/vector retrieval over testimony.
- **C. Alibi detective** — graph tools, gaps and shortlist.

Report culprit accuracy **with a Wilson 95% confidence interval**, plus LLM calls and tokens per case. State plainly in the README that 20 cases gives roughly ±20 percentage points and that this arm is **directional, not conclusive**. If the cache makes it cheap, push to 40–50 seeds; report whatever N you actually ran.

### 8.4 Avoiding a rigged benchmark

v1's oracle solved worlds using the same graph reasoning the detective uses, so worlds were implicitly selected for solvability-by-graph-reasoning — which favours arm C. Fixes:

1. **The oracle solves from ground truth**, not from graph inference. It knows the culprit because the generator chose them; it only checks that the *evidence set is sufficient in principle* (the culprit is distinguishable from the testimony that will exist). That is a fair difficulty filter, not a thumb on the scale.
2. **Report the rejection rate.** How many generated worlds were discarded, and why.
3. **Freeze evaluation seeds before any tuning**, committed in `eval/seeds.json`. Develop on a disjoint seed set.
4. **All arms run on identical worlds and identical testimony.**
5. **Never tune on evaluation seeds.** If you look at them, say so.

### 8.5 Do not promise a win

The README states a reproducible evaluation, not a predicted outcome. If the graph detective loses, publish that with analysis of where it struggles — a credible negative result beats an unreproducible win, and judges can tell the difference.

---

## 9. Proving it is a reusable layer, not a game

The "it's just a mystery game" objection is the biggest positioning risk, and a documented API alone will not answer it. Ship a **second fixture in a different domain**, running the same engine with no mystery concepts:

`fixtures/handoff/` — a two-agent support escalation. Agent A tells Agent B "the customer already verified their email." B asserts it onward. B's memory contains only the hearsay; A has no witnessed support. The audit returns `HEARSAY` on B's claim, the trace terminates `ORIGIN_UNSUPPORTED` at A, and B is visibly not the origin.

About 30 lines of fixture data, one page in the README, and the "just a game" objection is dead. If time runs short, ship a README section mapping the schema onto a generic agent system instead — but the fixture is worth the hour.

---

## 10. World generator (deterministic per seed)

- 7 suspects, 10–12 places on a connected floor plan with integer `minutes` edges, ticks 0–300.
- Routes respect travel times. Co-located suspects witness each other with a ~10% miss probability, so natural gaps exist.
- One incident (place, window). The culprit is present during it. An optional accomplice falsely corroborates.
- Hearsay: pairs meet and exchange 1–2 facts, each creating a `Transmission` with correct `tick` and `learned_at`. Honest suspects pass on witnessed facts. The culprit passes on one fabrication, which becomes hearsay in an honest suspect's mind — this produces the innocent-repeater demo moment.
- **Provenance integrity rule:** only the generator creates provenance. The audit engine reads and materializes what it proved, and **never manufactures a link to make an answer look grounded**. Put this in `PROJECT_RULES.md`.
- **Invariant tests:** identical world per seed; every route travel-feasible; every transmission temporally consistent (`source.learned_at <= tick`); the oracle (ground-truth based, section 8.4) finds the evidence sufficient. Rejected worlds are counted and reported.

---

## 11. 96-hour plan (IST), with slack

Hour 0 = Oct 15, 12:01 AM IST.

| Hours | Milestone | Acceptance gate |
|---|---|---|
| 0–8 | **M0 Spikes + infrastructure** | `docker compose up` works; every spike in section 12 passes or has a written fallback; isolation test skeleton runs. **Stop and replan if client or algorithm assumptions fail.** |
| 8–24 | **M1 World + audit engine + scripted suspects** | Deterministic world; all five verdicts unit-tested; coverage and gaps correct on boundary cases; aggregate-then-decide verified against a hand-built graph. Zero LLM calls needed. |
| 24–40 | **M2 Provenance** | Transmission records written; cross-graph trace returns a full chain; the planted innocent-repeater is traced to origin and checked against ground truth; temporal violation detected on a planted case. |
| 40–52 | **M3 LLM suspects behind the cache** | A full case replays bit-identically from cache; per-case call cap enforced. |
| 52–64 | **M4 Detective loop** | Q5–Q8 materialize live; detective solves a seeded world end to end using gaps and contradictions. |
| 60–78 | **M5 Case board UI** (overlaps M4/M6 — most interruptible work) | The three demo moments render; design system applied. |
| 64–80 | **M6 Evaluation** (harness skeleton lands early, full run late) | Harness runs frozen seeds, writes a results page with audit precision/recall and the confusion matrix. |
| **~80** | **Backup demo video recorded** | **A complete, submittable video exists from here on, whatever breaks later.** |
| 80–86 | Full benchmark run, README, `AI-USE.md`, handoff fixture | — |
| **86** | **Feature freeze** (Oct 18, ~2:00 PM IST) | — |
| 86–92 | Final video, clean-clone setup test, submit by ~8:00 PM IST | Deadline is 11:59 PM IST. Keep the buffer. |

M0 gets eight hours, not three: seven unverified assumptions cannot be cleared in three. The audit engine precedes every agent, because a trustworthy engine makes the mystery a demo and an untrustworthy one makes the whole premise collapse.

**Cut lines, in order:** coalitions (Q9) → betweenness → what-if fork (Q10) → baseline B → MCP (call tools directly) → handoff fixture (downgrade to a README section).

**Never cut:** coverage-aware audit with gaps, provenance trace, impossible-travel check, case board, demo video, the isolation test.

---

## 12. Day-1 spikes

Verified in the FalkorDB docs: variable-length syntax `[:TYPE*min..max]`, named paths, `algo.SPpaths` signature (`weightProp`, `relDirection:"both"`, yields `path` and `pathWeight`), `algo.labelPropagation`, `algo.betweenness`, `GRAPH.COPY`, `OPTIONAL MATCH`, DELETE removing a node's relationships, and the relationship-uniqueness limitation.

**Not verified. Test in `scripts/spikes.py` before building on them:**

1. `MERGE` of a relationship with a property map, then `SET` on it (Q5, Q6, Q7). Fallback: `MATCH`-then-`CREATE` guarded by an existence check.
2. `MERGE ... ON CREATE SET` on nodes (Evidence). Fallback: read-then-create.
3. String concatenation in a property map inside `MERGE` (`pair_id: a.id + '|' + b.id`). Fallback: compute the pair id in Python and pass it as a parameter.
4. `collect(DISTINCT ...)` + `size()` and `id(relationship)` in aggregation (Q8). Fallback: return rows and aggregate in Python.
5. Boolean expression in a `RETURN` projection (`(l.id = $place) AS same_place` in Q2). Fallback: return `l.id` and compare in Python.
6. Client `params` for parameterized queries, `GRAPH.RO_QUERY` via the Python client, and `graph.copy()`.
7. Throughput of writing ~10 mind graphs plus a case graph concurrently. Measure once.
8. `algo.SPpaths` called standalone per place pair for the travel matrix, and the shape of the returned `path`/`route`.
9. FastMCP version and tool-call round trip with the model client (only if MCP survives the cut).

Note that v1's riskiest spike — calling `algo.SPpaths` once per row after a multi-row `MATCH` — is **no longer on the critical path**, because the travel matrix is precomputed. If it happens to work, nothing changes; if it does not, nothing breaks.

---

## 13. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Audit returns a wrong verdict on stage | Aggregate-then-decide; boundary tests on the time contract; unit tests per verdict against hand-built graphs; the engine ships before any agent |
| "Unsupported" read as "lying" by a judge | Say the distinction out loud in the video and README; it is a feature, and it is measured |
| Looks like "just a game" | The handoff fixture, the documented `audit()` API, and the per-claim benchmark |
| FalkorDB assumption fails | Eight-hour M0, every spike has a written fallback, travel matrix removes the worst one |
| LLM role-play unreliable or expensive | Scripted suspects first and always available; cache every call; per-case cap; demo from replay |
| Benchmark too small to support a claim | Audit precision/recall over ~2000 claims is the headline; case accuracy carries a stated CI |
| World generator yields trivial or unsolvable cases | Ground-truth oracle, rejection rate reported, difficulty knobs |
| Time sink on the UI | One excellent case board beats four mediocre views; UI deliberately overlaps other milestones as interruptible work |
| Catastrophic late break | Backup video at hour 80; freeze at 86; submit at 92 |
| "Graph is decoration" objection | Every audit, coverage, contradiction, travel and provenance operation is Cypher or a FalkorDB algorithm; list them in the README with line references |
| Overclaiming | Hedge novelty with "to our knowledge"; report real numbers including bad ones; state application-enforced isolation, not security |

---

## 14. Related work and honest positioning

- **Social-deduction benchmarks** with LLM agents exist (Hoodwinked, WOLF, MafiaScope, WhodunitBench). They use free-text memory with model-based judging or probing. Alibi differs by auditing claims structurally against private per-agent graphs, with graph algorithms for feasibility and provenance, and by separating grounding from truth from intent.
- **Belief-graph theory-of-mind research** exists, including graph-gated action selection on Hanabi. Alibi applies "graph computes, LLM chooses" to multi-agent honesty.
- **Graphiti / Zep, Mem0, Cognee** are memory layers FalkorDB already integrates. Alibi is not a memory library; it is an audit layer and testbed over per-agent graph memory.
- I did not find a project combining these, but a few searches are not proof. Write **"to our knowledge"** in the README.

### Positioning for judges

Not "we made an AI murder mystery." The product is **an epistemic audit layer for multi-agent systems that traces claims through private memory, evidence and inter-agent transmission.** The mystery is the demonstration environment.

Three demo moments:
1. **The impossible alibi** — weighted shortest path proves the claimed journey does not fit, with the route drawn on the floor plan.
2. **The innocent repeater** — an honest suspect repeats something false; the trace walks across private graphs to the origin.
3. **The measurement** — audit precision and recall over thousands of claims, plus the grounded-vs-true gap.

---

## 15. Repo layout and rules for the coding assistant

```
alibi/
  PROJECT_RULES.md               # the rules below
  AI-USE.md               # disclosure log, updated every session
  README.md               # setup, graph model, queries, results, tracks
  docker-compose.yml
  backend/app/
    world/                # generator, oracle, invariants
    minds/                # MindAccess, mind writer, transmissions
    case/                 # case graph, ingest
    audit/                # evidence gather, coverage, decision table, materialize
    referee/              # provenance trace, ground-truth scoring
    agents/               # scripted + LLM suspects, detective, llm cache
    eval/                 # harness, frozen seeds, metrics
    api/                  # FastAPI routes, SSE
  backend/tests/          # test_time_contract, test_coverage, test_audit,
                          # test_isolation, test_provenance, test_aggregation, test_world
  fixtures/handoff/       # the non-mystery reusability fixture
  frontend/
  scripts/                # spikes, seed, run_case, run_eval, record_demo
  docs/                   # design references, brief, schema diagrams
```

**PROJECT_RULES.md block**
- All Cypher lives in `backend/app/**/queries.py` as named constants with a one-line comment stating the graph question it answers. No inline Cypher in routes.
- Verdicts, coverage, contradictions and scores are computed by Cypher plus deterministic Python. **Never by an LLM.**
- A verdict describes grounding, not intent. No code path may label a claim a lie. Deception labels exist only in `referee/` and only for scoring.
- Gather all evidence, then decide. No `LIMIT 1` in any audit query. No first-match precedence.
- All intervals are half-open `[t0, t1)`. Overlap uses strict inequalities. Boundary tests must stay green.
- Only the generator creates provenance. The audit materializes only what it proved. Never manufacture a link to make an answer look grounded.
- No tool exposed to an agent may accept a graph name or an agent id. Only the referee may read a mind other than the caller's.
- Every LLM call goes through the cache wrapper and the per-case cap.
- Test first for audit, time contract, aggregation and world-generator logic.
- Small commits. Tag `m0`...`m6` at milestones. Append to `AI-USE.md` every session.

**Kickoff prompt for the coding assistant**
> Read `ALIBI_SPEC.md` fully, then implement **milestone M0 only**: a docker-compose with `falkordb/falkordb`, a Python 3.12 FastAPI skeleton using the official `falkordb` client, and `scripts/spikes.py` running each numbered spike from section 12 against a scratch graph, printing PASS/FAIL with the exact error text for failures. Also scaffold `backend/tests/test_time_contract.py` with the four boundary cases from section 4.0, which should fail until M1. Do not start M1 until I confirm the spike results.

---

## 16. Submission checklist

- [ ] Public repo with README: setup, **graph data model**, the queries and algorithms, results, limitations
- [ ] Demo video, ~90 s, recorded from cached replay (backup recorded at hour 80)
- [ ] Live deployment, or complete local setup verified from a clean clone
- [ ] Tracks named: **Track 02** (primary) and **Track 01** (secondary)
- [ ] `AI-USE.md` disclosure complete and honest
- [ ] Data statement: synthetic, procedurally generated
- [ ] Isolation test passing and referenced in the README
- [ ] Frozen eval seeds committed; rejection rate reported; CIs stated
- [ ] Blog post (side prize): "grounded is not the same as true" plus the benchmark
- [ ] **Re-check the Rules tab on the event page on Oct 18** for any update

**Demo script (~90 s)**

```
0:00  "Every claim needs a path." The problem in one sentence.
0:10  Seven suspects, seven private graphs. Nobody can read anyone else's.
0:20  Detective interviews; claims stream into the case board.
0:32  A claim audits INDETERMINATE -- 12 minutes nobody accounts for.
      The detective asks about exactly those 12 minutes.
0:45  Contradiction: an impossible walk, with the route drawn on the floor plan.
1:00  Polygraph: no supporting path in the speaker's own memory.
      Say out loud: "ungrounded, not necessarily a lie."
1:10  Provenance: an honest suspect repeated something false -- walk the chain
      across private graphs to its origin.
1:22  Accusation, then the ground-truth reveal.
1:30  The numbers: audit precision and recall, and the grounded-vs-true gap.
```
