# Progress

This file is the handoff between sessions. It survives context compaction when
chat does not. the coding assistant: update it at the end of every session, before you stop.
Keep it under 80 lines — delete detail that no longer matters.

## Current state

- **Milestone:** M0 — spikes and infrastructure
- **Gate not yet passed.**
- **Last verified by:** (nothing yet)

## Spike results (spec section 12)

| # | Assumption | Result | Note / fallback taken |
|---|---|---|---|
| 1 | MERGE rel with property map, then SET | — | |
| 2 | MERGE ... ON CREATE SET on nodes | — | |
| 3 | String concat in MERGE property map | — | |
| 4 | collect(DISTINCT) + size(), id(rel) | — | |
| 5 | Boolean expression in RETURN projection | — | |
| 6 | Client params, GRAPH.RO_QUERY, graph.copy() | — | |
| 7 | ~10 mind graphs + case graph concurrently | — | |
| 8 | algo.SPpaths standalone per pair, path shape | — | |
| 9 | FastMCP round trip (only if MCP survives) | — | |

## Decisions made

- Backend is Python 3.12 + FastAPI. Frontend React + TS + Vite, no Tailwind.
- (record every decision that a later session would otherwise re-litigate)

## Known issues

- (none yet)

## Next action

Run `make up` then `make spikes`. Record every result above, including failures,
with the exact error text. Stop at the gate and report.
