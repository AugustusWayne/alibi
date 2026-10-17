# Progress

The handoff between sessions; it survives context compaction when chat does
not. Update it at the end of every session, before stopping. Keep it under 80
lines — delete detail that no longer matters.

## Current state

- **M2 gate passed** (tag `m2`): the trace names the right origin on seed 7777,
  and the detective's typed tools are in. M0/M1 at `m0`/`m1`.
- **Last verified:** 2026-10-17, `make verify` → ruff clean, **100 passed**,
  `VERIFY OK`.
- **The case board (M5's first view), `scripts/dump_case.py`,
  `docs/design/directions/` and the doc rewordings are still uncommitted, by
  request.** The m2 commits deliberately leave them in the working tree. The
  board is built in the 8-bit direction through claim inspection and renders
  the whole case from its fixture; no API dependency.
- FalkorDB `v4.22.1`, `falkordb 1.8.0`, Python 3.12.1, host port **6380**.
- All Cypher is in `**/queries.py`, one comment per constant; no `LIMIT` in any
  query; the deception vocabulary appears nowhere outside `referee/`.

## What M2 is

`referee/` — `terminals.py` (the seven states of 5.7), `provenance.py` (the
cross-graph walk and the `learned_at <= tick` check), `ground_truth.py` (the
only reader of `world:{seed}`), `queries.py`. Q8 gained
`originated_ungrounded` / `carried_ungrounded`; the five weights live in a
frozen `eval/weights.json`, each with a rationale.

`agents/detective.py` — the seven tools of spec 7 (`interview`,
`list_contradictions`, `list_gaps`, `check_travel`, `rank_suspects`,
`polygraph`, `accuse`) over the public case graph, with the polygraph budget of
two per case. This pulls the playbook's M4 *tool surface* forward, because the
`TRACED_TO` ruling below needs `polygraph` to exist. The LLM detective **loop**
is still M4 and there are no API routes yet; neither is part of M2's gate ("the
trace names the right origin on a world where you know the answer").

**M1's open finding is resolved by structure, not tuning.** Repeating a
fabrication in good faith genuinely leaves unaccounted-for testimony, so M1
ranked the honest repeater `p2` above the culprit `p4`. The origin/carrier split
fixes it: on the operator's full view of seed 7777 the board reads `p4` 27.5
over `p2` 20.5 (the 23.0/16.5 in the old note here predates a later run and is
stale). The weights were frozen before that first run and none has changed
since; they must never be fitted to a seed's outcome (spec 8.4).

**`UNSUPPORTED` still never arises from a generated world**, since every
scripted claim derives from some memory. It is demonstrated against a
hand-built graph in `test_audit.py`; if M3 is cut, the eval must say so.

## Decisions made (do not re-litigate)

- **`TRACED_TO` is materialized only for claims the detective polygraphed.**
  Implemented 2026-10-17. `trace_all_hearsay` writes nothing;
  `Referee.materialize_chain` is called by `polygraph` and by nothing else in
  the application, so a chain conclusion exists exactly where a polygraph was
  spent and Q8's origin/carrier columns stay at zero until one is. The fix was
  timing, not location — the edges stay in the case graph, so Q8 still
  aggregates in Cypher and the privacy seam holds. Measured on seed 7777: 0
  `TRACED_TO` after auditing all 126 claims; polygraphing `p2-c10` reveals
  `ORIGIN_CONTRADICTED` at `p4` and moves `p4` from third to first (27.0).
  **The operator's board is exempt and opts in explicitly** (one visible loop
  in `dump_case.py`): the operator may see everything, only the agent is
  rationed. The fixture is byte-identical before and after this change.
- **The budget counts distinct claims, not calls.** A repeat polygraph opens no
  mind — that conclusion is in the case graph by then — so charging for it
  would measure call discipline, not information.
- **A suspect id in a detective tool is not a mind selector.** Roster and seed
  are bound at construction; `polygraph` reads the claim's public `BY` edge and
  refuses a suspect who did not make the claim (rule 6).
- **An interview repeating known testimony ingests nothing**, or the
  detective's own repetition would inflate the board against the speaker.
- **A zero-length or inverted claim window raises**, at `ingest_claim` and in
  `decide`: `[t, t)` made `covered >= duration` collapse to `0 >= 0` and return
  SUPPORTED over zero examined minutes. **Standing check: wherever the engine
  takes a ratio over a span, ask what an empty span does.**
- **The culprit's relayed fabrication cites a real `inferred` fact.** Citing a
  fact existing nowhere can only yield `CHAIN_BROKEN`, which 5.7 says is not an
  origin, so the three ORIGIN states were unreachable from a generated world.
- **`Gap` nodes go to the partial-support row only**; `UNSUPPORTED` records
  `uncovered` only. **Hearsay support is `SUPPORTED_BY`** with `src='hearsay'`.
- **`plan_world` is pure data, `generate` writes it**, cross-checking its own
  Floyd-Warshall matrix against `algo.SPpaths`. **The claim cap samples the
  evening evenly**; `testify(window=…)` is never capped.
- **The board is the 8-bit direction** (ruled 2026-10-17; brief amended, thesis
  and semantics kept, rule 10 unchanged). **Strip rows hold a suspect's claims
  about themselves**, `RE: <name>` what others said about the subject. **An
  unresolved trail shows no origin chip** (`CHAIN_BROKEN` → `???`, temporal
  violation → the cited agent dashed). **An INDETERMINATE bar's fill comes from
  its gaps**, and ink stops at the playhead.

## Known issues

- A bare `pytest` dials 6379 and hits another project's redis. Use `make test`;
  run `scripts/dump_case.py` with `FALKOR_PORT=6380`.
- `make up` fails in a git worktree when another checkout's container is
  already up — same container name, different compose project. The running
  container serves every checkout; nothing to fix.
- `scripts/{seed,run_case,run_eval,record_demo}.py` do not exist; `make eval`
  and `make demo` fail until M4/M5.
- The board's fixture is the operator's full trace view, so a board driven by a
  *detective's* case graph will show no trail until a polygraph is spent. That
  is the intended demo and it is not built yet.

## Next action

M3, or M4's loop: the model that chooses which gap to ask about and when to
spend the two polygraphs, plus the API routes the board will read. The tools,
the budget and the Q5–Q8 materialization they drive are done.
