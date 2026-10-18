# Progress

The handoff between sessions; it survives context compaction when chat does
not. Update it at the end of every session, before stopping. Keep it under 80
lines — delete detail that no longer matters.

## Current state

- **M6 gate closed**, tagged `m6`: the harness runs the 24 frozen seeds and the
  numbers below were reviewed and signed off.
- **Tags that exist are `m2`, `m5`, `m6`.** `m0` and `m1` have never existed as
  refs in this repo, despite what earlier notes here claimed. Candidates, if
  they get cut: `ca13855` ("M0: infrastructure and the nine FalkorDB assumption
  spikes") and `b23a03f` ("M1 gate: PROGRESS.md and AI-USE.md").
- **Last verified:** 2026-10-18, `make verify` → ruff clean, **131 passed**.
- **M5 is committed and tagged `m5`** (`3e1f452` on `adoring-wright`): the case
  board, `scripts/dump_case.py` and `docs/design/directions/`. It did **not**
  go through a gate review — no show-me-the-raw-output pass, unlike M2 and M6 —
  and that review is still open.
- FalkorDB `v4.22.1`, `falkordb 1.8.0`, Python 3.12.1, host port **6380**.

## What M6 is

eval/seeds.json: 24 frozen seeds (10000+37k), rule-generated, never
rewritten. backend/app/eval/: harness.py, metrics.py, report.py, seeds.py.
referee/ground_truth.py gained spec 8.1 labels + PlanTruth. No LLM.

## M6 numbers (full detail: eval/results.json, this session's chat log)

Falsehood detection: 100% precision, 70.5% recall, 24 seeds / 3086 claims,
scripted, no LLM. Zero false accusations. The 13 misses are specifically
falsehoods relayed secondhand with no contradicting witnessed account — not
a general miss rate. Origin ID 12/12, chain root 498/498. Gap precision is
a structural null (0.00%/0.55%) under scripted-only worlds — see next
action. Weights frozen, untouched, never read by eval.

## Decisions made (do not re-litigate)

- **`TRACED_TO` is materialized only for claims the detective polygraphed**, and
  **the eval materializes nothing either** — it scores from `Chain` objects in
  memory, so a run cannot put the referee's conclusions into a case graph.
- **A seed's graphs are dropped before a run as well as after.**
  `CREATE_PRESENCE` and `ingest_claim` append, so generating into an inherited
  `case:{seed}` silently doubles the world and every count is wrong by a
  plausible factor. It happened on the first 7777 run: 252 claims, not 126.
- **The answer key takes hearsay in `(t0, id)` order, as the referee does.** A
  claim can rest on several secondhand memories with different true origins and
  `trace_claim` walks the first; any other order named the root of a chain the
  referee did not follow and manufactured 9 disagreements out of two right
  answers (seen on 10074).
- **The budget counts distinct claims, not calls.** **A suspect id in a tool is
  not a mind selector.** **An interview repeating known testimony ingests
  nothing.**
- **A zero-length or inverted claim window raises.** **Standing check: wherever
  the engine takes a ratio over a span, ask what an empty span does.**
- **The culprit's relayed fabrication cites a real `inferred` fact**, or the
  three ORIGIN states would be unreachable from a generated world.
- **`Gap` nodes go to the partial-support row only.** **Hearsay support is
  `SUPPORTED_BY`** with `src='hearsay'`. **`plan_world` is pure data, `generate`
  writes it**, cross-checking Floyd-Warshall against `algo.SPpaths`.
- **M1's open finding is resolved by structure, not tuning**: the origin/carrier
  split ranks culprit `p4` above honest repeater `p2` on seed 7777. The weights
  were frozen before that run and none has changed since (8.4).
- **The board is the 8-bit direction**; strip rows hold a suspect's claims about
  themselves, an unresolved trail shows no origin chip.

## Known issues

- A bare `pytest` dials 6379 and hits another project's redis. Use `make test`;
  run the scripts with `FALKOR_PORT=6380`.
- `make up` fails in a worktree when another checkout's container is up — same
  container name, different compose project. Nothing to fix.
- `hypothesis==6.140.3` would not resolve from a sandboxed pip in a fresh
  worktree; installs normally with unrestricted network.
- `scripts/{seed,record_demo}.py` do not exist; `make demo` fails until M5.

## Next action

M4 (detective loop + API routes) — M3 stays cut by decision (suspects
remain scripted; the detective is the only LLM agent). The gap-precision
null result above is an argument for reopening M3 later, not a default:
reopening it needs a deliberate decision in chat with the operator, same as
the original cut. Spec 8.3's three-arm comparison needs M4 and isn't started.
