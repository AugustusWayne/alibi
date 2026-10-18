# Progress

The handoff between sessions; it survives context compaction when chat does
not. Update it at the end of every session, before stopping. Keep it under 80
lines — delete detail that no longer matters.

## Current state

- **M4 is committed and tagged `m4`**, on `wip/m4-detective-loop-a2e276`:
  the detective's loop, the LLM replay cache, the FastAPI routes with SSE.
  **Last verified** 2026-10-18: `make verify` → ruff clean, **201 passed**
  (131 before M4).
- **All history was rewritten on 2026-10-18 to remove the assistant's vendor
  name**, so every hash below is new. Branches, all five, and tags m0–m6 were
  moved together; `main` has not been pushed and now differs from
  `origin/main` by its whole history. Pre-rewrite tips are kept locally under
  `refs/pre-debrand/*` and in `~/alibi-backup-20261018-132036/all-refs.bundle`.
- **All six gates are tagged**: m0 `1268a23`, m1 `542cfde`, m2 `08c06e7`,
  m4 `42742e8`, m5 `e9f6863`, m6 `00377b1`. m0 and m1 were cut
  retrospectively on 2026-10-18, which their annotations say; they had never
  existed as refs before that, despite earlier notes here claiming otherwise.
- Neither M5 nor M4 has had a show-me-the-raw-output gate review, unlike M2
  and M6. Both reviews are open.
- FalkorDB `v4.22.1`, `falkordb 1.8.0`, Python 3.12.1, host port **6380**.

## What M4 is

`agents/llm_cache.py`: SQLite replay cache keyed by `(seed, agent,
prompt_hash)` plus the hard per-case call cap — the only path to a model.
`agents/loop.py`: the loop driving M2's seven tools, with the
intent-vocabulary guard; `agents/intent_vocabulary.json` holds the frozen
list. `api/{runner,routes}.py`: case routes and the SSE stream.
`scripts/run_detective.py`: record a case, then replay it. 68 new tests in
`test_{llm_cache,loop,api}.py`. Call cap 24. **No model-vendor SDK is pinned,
imported or named anywhere, and no model id is either**: the transport is a
plain callable resolved at runtime from `ALIBI_COMPLETER`
(`package.module:factory`), the model id comes from `ALIBI_DETECTIVE_MODEL`,
and both raise rather than defaulting. One new dependency, `httpx`, for the
test client.

**The loop has never made a real model call.** No API credential and no
transport are configured in this environment, confirmed independently by the
M6 session. All 201 passing
tests exercise the cached and scripted-transport paths only; `--live` is
untested against the API. **Spec 8.3's three-arm comparison therefore cannot
be claimed at all yet** — not arm C, and not the LLM-calls-per-case column.

What *was* demonstrated, on 7777 with a scripted plan (`run_detective.py`
labels every pass as such so its output cannot be read as a model's): 6 turns
and 6 API calls recorded, then pass two rebuilt the same world and replayed
with no transport configured — 6 cache hits, **0 API calls**, identical tool
calls and accusation. That is the loop, the budget, the events and the cache;
it is not evidence about a model's judgement.

## What M6 is, and its numbers (detail in eval/results.json)

24 frozen seeds (`eval/seeds.json`, rule-generated as 10000+37k, never
rewritten); `backend/app/eval/`; spec 8.1 labels + `PlanTruth` in
`referee/ground_truth.py`. No LLM. Falsehood detection 100% precision / 70.5%
recall over 3086 claims, zero false accusations; the 13 misses are all
falsehoods relayed secondhand with no contradicting witnessed account. Origin
ID 12/12, chain root 498/498. Gap precision is a structural null
(0.00%/0.55%) under scripted-only worlds. Weights frozen, never read by eval.

## Decisions made (do not re-litigate)

- **`TRACED_TO` is materialized only for claims the detective polygraphed**,
  and **the eval materializes nothing** — it scores from in-memory `Chain`s.
- **A seed's graphs are dropped before a run as well as after.**
  `CREATE_PRESENCE` and `ingest_claim` append, so generating into an inherited
  `case:{seed}` doubles the world and every count is wrong by a plausible
  factor. It happened on the first 7777 run: 252 claims, not 126.
- **The answer key takes hearsay in `(t0, id)` order, as the referee does.**
- **The budget counts distinct claims, not calls.** **A suspect id in a tool
  is not a mind selector.** **An interview repeating known testimony ingests
  nothing.**
- **The cap counts attempts, not cache misses**, or a replayed run could
  outlive its recording. `api_calls` is separate and is the cost figure.
- **Nothing outside the loop may call a detective tool.** The scoreboard route
  and the demo script both first read Q8 through `DetectiveTools`; both were
  wrong. A tool call is charged to the detective's spec-8.3 cost column, and
  the surface closes when the case is accused — so a board refreshing a panel
  would be billed to the detective and would 500 on a closed case. Both now
  call `rank_suspects(case.scoreboard_rows())`.
- **A zero-length or inverted claim window raises.** **Standing check:
  wherever the engine takes a ratio over a span, ask what an empty span does.**
- **The culprit's relayed fabrication cites a real `inferred` fact**, or the
  three ORIGIN states are unreachable from a generated world.
- **`Gap` nodes go to the partial-support row only**; hearsay support is
  `SUPPORTED_BY` with `src='hearsay'`; `plan_world` is pure data and
  `generate` writes it, cross-checking Floyd-Warshall against `algo.SPpaths`.
- **M1's open finding is resolved by structure, not tuning**: the
  origin/carrier split ranks culprit `p4` above honest repeater `p2` on 7777.
- **The board is the 8-bit direction**; strip rows hold a suspect's claims
  about themselves, an unresolved trail shows no origin chip.
- **The intent vocabulary is a frozen data file**, `agents/intent_vocabulary.
  json`, not a Python constant — defining a word so nothing can publish it is
  not what rule 2 forbids, and the `eval/weights.json` convention applies.
  Ruled on by the M6 session, which wrote the guard test. **That guard now
  scans every shipped code and data file**, not only `*.py`, with exactly two
  named exceptions: `referee/` and the vocabulary file. Markdown is excluded
  on purpose — the spec and the rules have to quote the words to state them.

## Known issues

- A bare `pytest` dials 6379 and hits another project's redis. Use `make test`;
  run the scripts with `FALKOR_PORT=6380`. `make up` fails in a worktree when
  another checkout's container is up. `make demo` fails: no `record_demo.py`.

## Open for your ruling (M4)

1. **A free-text rationale is the one model-written string this system
   publishes.** A structured one would need no guard at all, but spec 7
   writes `accuse(suspect, rationale)` and M2 built it that way.
2. **The route design is mine** — spec 3 says only "SSE stream of events".
   One case per seed, because the graphs are keyed by seed.
3. **The call cap is 24 and counts cache hits**, and `DELETE /cases/{seed}`
   drops the seed's graphs. Both are my defaults, not the spec's.

## Next action

The M4 gate review, and the live arm, which has never reached the API. M3
stays cut by decision (the detective is the only LLM agent); the gap-precision
null is an argument for reopening it later, not a default, and reopening needs
a deliberate decision with the operator. Spec 8.3's three-arm comparison now
has the loop it needed and is not started.
