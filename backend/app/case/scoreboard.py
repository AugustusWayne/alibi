"""The ranking function. One place, so the weights cannot drift.

**What this ranks.** How much of what a suspect said their own memory does not
account for. It is a measure of grounding, not of guilt — a suspect can top
this board because they spent the evening alone, and an honest suspect who
repeats something they were told in good faith will carry the gap it leaves.
The ordering is a reading order for the detective, not an accusation.

The UI shows the breakdown, never only the total, so a reader can see which
term put a suspect where it did.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

# The weights live in `eval/weights.json`, not here. Two reasons: a frozen
# file can carry a written rationale per weight, and it makes a change to the
# ranking a visible diff in a data file rather than an edit buried in code
# that every eval number silently depends on.
#
# They were set from reasoning about what each signal can establish, and are
# deliberately not fitted to any seed's outcome — see the note in the file.
WEIGHTS_PATH = Path(__file__).resolve().parents[3] / "eval" / "weights.json"

SCORED_TERMS = (
    "originated_ungrounded",
    "self_contradictions",
    "other_contradictions",
    "gaps",
    "carried_ungrounded",
)
"""Every term the score is made of. A Q8 row missing one of these is a bug,
not a zero: it would mean the scoreboard silently stopped counting something."""


@lru_cache(maxsize=1)
def load_weights(path: Path | None = None) -> dict[str, float]:
    """Read the frozen weights.

    Raises if a term is missing rather than defaulting it to zero. A weight
    that quietly vanished would drop a whole signal out of the ranking while
    every score still looked plausible (PROJECT_RULES.md rule 8).
    """
    source = path or WEIGHTS_PATH
    data = json.loads(source.read_text())["weights"]
    missing = [term for term in SCORED_TERMS if term not in data]
    if missing:
        raise ValueError(f"{source} is missing weights for {missing}")
    return {term: float(data[term]["value"]) for term in SCORED_TERMS}


def score_suspect(row: dict) -> tuple[float, dict[str, float]]:
    """Return `(score, breakdown)` for one Q8 row.

    The breakdown is every term, including the zeros, so the UI can show how a
    score was reached rather than only what it came to.
    """
    weights = load_weights()
    breakdown = {term: row[term] * weights[term] for term in SCORED_TERMS}
    return sum(breakdown.values()), breakdown


def rank_suspects(rows: list[dict]) -> list[dict]:
    """Rank Q8 rows, highest unaccounted-for score first.

    Ties break on suspect id so the board is identical between runs — the
    whole system is deterministic, and a scoreboard that reshuffled on equal
    scores would make a demo look like it had changed its mind.
    """
    scored = []
    for row in rows:
        score, breakdown = score_suspect(row)
        scored.append({**row, "score": score, "breakdown": breakdown})
    return sorted(scored, key=lambda r: (-r["score"], r["suspect"]))
