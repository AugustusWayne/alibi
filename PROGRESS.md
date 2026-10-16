# Progress

The handoff between sessions; it survives context compaction when chat does
not. Update it at the end of every session, before stopping. Keep it under 80
lines — delete detail that no longer matters.

## Current state

- **Milestone:** M1 — world generator, mind writer, audit engine. **Gate passed.**
- **Last verified by:** 2026-10-16, `make verify` → ruff clean, **61 passed**, `VERIFY OK`.
- Zero LLM calls in M1. No xfail, no skip, no mocked graph in the suite.
- FalkorDB `v4.22.1`, `falkordb 1.8.0`, Python 3.12.1, host port **6380**. Next: M2.

## What M1 built

`audit/` — `time_contract`, `coverage` (5.4 verbatim, merges before summing),
`verdicts`, `decide` (the 5.5 table), `engine` (gather → decide → materialize).
`minds/` — Q1 writes, Q2 gather, recall; `MindAccess` binds one mind at
construction, so a suspect cannot express a request for another's memory.
`case/` — Q4–Q8, 5.6 materialization, SPpaths matrix, `scoreboard.py` (the one
ranking function). `world/` — `plan_world` (pure data) + `generate` (writes
world/minds/case). `agents/scripted.py` — `ScriptedSuspect` +
`FabricationPolicy`, no LLM.

All Cypher is in `**/queries.py`: 42 named constants, each with a one-line
comment. No `LIMIT` in any query. The deception vocabulary appears nowhere
outside `referee/` (which does not exist yet).

Seed 7777 (11 places, 7 people, 146 facts, 42 transmissions) gives **SUPPORTED
95, HEARSAY 23, INDETERMINATE 6, CONTRADICTED 1** over 125 claims, with 6
exclusive-presence and 4 impossible-travel pairs. The innocent-repeater moment
is asserted by a test: `p2 says p4 at hall [102,122) heard from p4` → `HEARSAY`.

## Two findings M2 must know

1. **The scoreboard's top row is not an accusation, and here it is often not the
   culprit.** On seed 7777 the honest repeater `p2` outscores the culprit `p4`
   (16.0 vs 15.0): repeating the fabrication in good faith genuinely leaves `p2`
   with testimony its own memory cannot account for. Correct for a grounding
   measure, and **not** to be fixed by retuning weights — that is the rigged
   benchmark spec 8.4 warns against. Telling "carries a contradiction" from
   "originated it" is what the provenance trace (5.7) is for, and this is now the
   strongest argument for building it. The ranking docstring says so; keep it.
2. **`UNSUPPORTED` does not arise in a generated world**, since every scripted
   claim derives from some memory. It is demonstrated against a hand-built graph
   in `test_audit.py` and is reachable in the engine. LLM suspects (M3) would
   produce it naturally; if M3 is cut, the eval should say so rather than imply
   the state is dead.

## Decisions made (do not re-litigate)

- **`Gap` nodes go to the partial-support row only** (5.5 literal). An
  `UNSUPPORTED` claim records `uncovered` but gets no `Gap` nodes — it is already
  its own signal, so Q8's gaps mean "holes in claims that had some backing".
- **Hearsay support is materialized as `SUPPORTED_BY`** with `src='hearsay'` on
  the Evidence shadow, carrying `heard_from` and the transmission tick. That
  keeps a HEARSAY verdict walkable without the case graph holding a fact.
- **`plan_world` is pure data, `generate` writes it**, so determinism is provable
  by diffing two plans. `generate` cross-checks its own Floyd-Warshall matrix
  against the graph's `algo.SPpaths` matrix and raises on disagreement.
- **The claim cap samples the evening evenly, it does not truncate it.** Taking
  the earliest N dropped the back half of every suspect's evening and was
  silently losing the innocent-repeater claim. `testify(window=…)` is never
  capped — an interview about a span deserves every claim bearing on it.
- Q8 splits `self_contradictions` / `other_contradictions`, weighted 5.0 / 2.0 /
  1.0 (gaps). The fixture M0 recorded is now a test.

## Known issues

- A bare `pytest` dials 6379 and hits another project's redis. Use `make test`;
  `conftest.py` fails with that instruction rather than skipping.
- `scripts/{seed,run_case,run_eval,record_demo}.py` do not exist; `make eval`
  and `make demo` fail until M4/M5.
- This branch was fast-forwarded onto M0's branch (tag `m0`) at the start of M1.

## Next action

Start M2 (case graph API + detective tools, spec 5.7 and section 7). Read
`PROJECT_RULES.md` and this file, then only the spec sections M2 needs. The provenance
trace is the priority — see finding 1.
