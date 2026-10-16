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

# Weights, all in one place.
#
# `self_contradictions` outweighs `other_contradictions` because the two are
# different kinds of finding. A suspect contradicted by *someone else* may
# simply have been misremembered by that someone: the pair tells you the two
# accounts disagree, not which one is wrong. A suspect whose own two claims
# cannot both hold needs no second witness — the inconsistency is internal and
# self-evident, so it is the stronger signal and weighs more.
#
# A gap is the weakest term: it means nothing accounted for a span, which is
# routine for anyone who was briefly alone.
W_SELF_CONTRADICTION = 5.0
W_OTHER_CONTRADICTION = 2.0
W_GAP = 1.0


def score_suspect(row: dict) -> tuple[float, dict[str, float]]:
    """Return `(score, breakdown)` for one Q8 row."""
    breakdown = {
        "self_contradictions": row["self_contradictions"] * W_SELF_CONTRADICTION,
        "other_contradictions": row["other_contradictions"] * W_OTHER_CONTRADICTION,
        "gaps": row["gaps"] * W_GAP,
    }
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
