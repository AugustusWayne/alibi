"""The eval harness (spec section 8).

Runs the frozen seeds through the whole pipeline with scripted suspects and no
LLM anywhere, then scores the engine's verdicts against the generator's own
answer key. Three pieces, kept apart on purpose:

- `harness.py` drives one seed end to end and returns plain records.
- `metrics.py` is pure arithmetic over those records — no database, no graph,
  no Cypher, so every figure in the report is unit-testable without a server.
- `report.py` renders. Nothing in it computes.

**Nothing here tunes anything.** `eval/weights.json` is frozen with a written
rationale per weight and spec 8.4 forbids fitting it to a seed's outcome. An
unflattering number is published with analysis (8.5); it is not weighted away.
"""
