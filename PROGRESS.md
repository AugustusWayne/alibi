# Progress

This file is the handoff between sessions. It survives context compaction when
chat does not. the coding assistant: update it at the end of every session, before you stop.
Keep it under 80 lines — delete detail that no longer matters.

## Current state

- **Milestone:** M0 — spikes and infrastructure. **Gate passed.**
- **Last verified by:** 2026-10-16, `make up` + `make spikes` (9/9 PASS) + `make verify` (VERIFY OK).
- FalkorDB `v4.22.1` (module graph v42201), client `falkordb 1.8.0`, Python 3.12.1.
- Next: M1. Nothing in M1 is blocked by a spike.

## Spike results (spec section 12)

All nine run against FalkorDB v4.22.1. **No fallback was taken — every assumption holds.**

| # | Assumption | Result | Note / fallback taken |
|---|---|---|---|
| 1 | MERGE rel with property map, then SET | **PASS** | MERGE created 1, re-MERGE 0, SET readable. No duplicate rel. |
| 2 | MERGE ... ON CREATE SET on nodes | **PASS** | Created once; ON CREATE did not re-fire and did not overwrite a mutated field. |
| 3 | String concat in MERGE property map | **PASS** | `a.id + '\|' + b.id` = `c1\|c2` in-query. No Python fallback needed. |
| 4 | collect(DISTINCT) + size(), id(rel) | **PASS** | Q8 verbatim: (claims=2, contradictions=1, gaps=2). Contradiction counted once from both endpoints. `id()` works on nodes *and* relationships inside `collect(DISTINCT)`. |
| 5 | Boolean expression in RETURN projection | **PASS** | `(l.id = $place)` returns a real Python `bool`; unmatched OPTIONAL MATCH yields `None`. |
| 6 | Client params, GRAPH.RO_QUERY, graph.copy() | **PASS** | params ok for str/int/float/bool/null/list; `ro_query` **refuses writes** (ResponseError) so it is a real read path; `copy()` clones and the clone is independent. |
| 7 | ~10 mind graphs + case graph concurrently | **PASS** | 10 minds x 200 facts + 140 claims = 2140 writes in 0.10s wall (~20k rows/s), 11 threads, 11 connections, all counts exact. Throughput is not a risk. |
| 8 | algo.SPpaths standalone per pair, path shape | **PASS** | p0→p9 weight 21 via `['p0','p1','p2','p7','p8','p9']`; 90 ordered pairs in 0.04s (0.5ms/call); symmetric under `relDirection:'both'`. **See spec correction below.** |
| 9 | FastMCP round trip | **PASS** | fastmcp 3.4.0 in-memory client/server round trip. **Version-sensitive, see below.** the model vendor-SDK half NOT tested (needs an API key; M3). |

### Two findings that change what M1/M3 must write

1. **Spec 5.10's `algo.SPpaths` snippet does not run as written.** `sourceNode: $la`
   with a string parameter fails: `sourceNode and targetNode must be of type Node`.
   M1 must `MATCH (a:Place {id:$a}), (b:Place {id:$b})` first and pass the bound
   node values. Working form is in `scripts/spikes.py:SPPATHS_MATCHED`. This does
   not affect the design — the travel matrix is still precomputed once per world.
2. **fastmcp 4.x breaks FastAPI.** It pulls `mcp` 2.x → `starlette` 1.8.0, while
   `fastapi` 0.120.4 requires `starlette<0.50`; importing the app then dies with
   `TypeError: Router.__init__() got an unexpected keyword argument 'on_startup'`.
   `fastmcp==3.4.0` + `starlette<0.50` coexist. Pinned in `requirements-optional.txt`.
   MCP is still an extension and still on the cut list.

## Decisions made

- Backend is Python 3.12 + FastAPI. Frontend React + TS + Vite, no Tailwind.
- **Image pinned by tag AND digest** in `docker-compose.yml`:
  `falkordb/falkordb:v4.22.1@sha256:b0bdcac2cbaff989e77cb0610439b7a9289e86de033ccbbd4368b66fb680ae7a`.
  Bumping it means re-running `make spikes` and re-recording this table.
- **Host port is configurable, default 6379.** This machine already runs another
  project's redis on 6379, so a gitignored `.env` publishes FalkorDB on **6380**
  (`.env.example` is committed). The Makefile `-include .env` + `export` so docker
  compose and the Python client can never disagree about the port.
- **Makefile uses literal tabs, not `.RECIPEPREFIX`.** macOS ships GNU Make 3.81,
  where `.RECIPEPREFIX` is a hard syntax error. The original file said to do this.
- MCP left out of `requirements.txt`; it is an extension, in `requirements-optional.txt`.

## Known issues

- `make spikes` run *without* `make` (so without the exported `FALKOR_PORT`) would
  dial 6379 and reach the other project's plain redis. `scripts/spikes.py` now
  preflights for the graph module and exits 2 with instructions rather than
  reporting nine confusing failures. Same hazard applies to any future script.
- `backend/tests/test_time_contract.py` is 4 xfail(strict=True). M1 implements
  `backend/app/audit/time_contract.py` and **deletes the markers** — strict means
  the suite goes red the moment they pass, so they cannot be silently left on.

## Next action

Start M1 (world generator + audit engine + scripted suspects). Read `PROJECT_RULES.md`
and `PROGRESS.md`, then **only** sections 4 and 5 of the spec. Write the tests
first. No LLM calls in M1.

## Naming discrepancy to settle

`PROJECT_RULES.md` and `BUILD_PLAYBOOK.md` both reference `ALIBI_SPEC.md`, but the file
on disk is `FalkorDB Alibi Spec (1).md`. Left alone this session — renaming your
spec is your call. Worth fixing before the repo goes public.
