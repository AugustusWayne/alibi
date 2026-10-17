"""The seven states a provenance chain can end in (spec 5.7).

Three name an origin — the chain resolved to an agent and we can say what that
agent's own memory did or did not hold. Four name a failure of the chain
itself, which is a different kind of finding and must not be read as an origin.

**What an origin state does and does not prove.** `ORIGIN_UNSUPPORTED`
identifies the origin *of the chain the referee can see*, not necessarily the
agent who made something up. `CHAIN_BROKEN` is genuinely ambiguous: the agent
may have had nothing to record, or may simply never have recorded what it was
told. Both are reported as named states and neither is reported as an origin.
Origin-identification accuracy is *measured* against ground truth (spec 8),
never asserted.
"""

from __future__ import annotations

ORIGIN_WITNESSED = "ORIGIN_WITNESSED"
"""The chain ends in someone whose own witnessed memory holds it."""

ORIGIN_UNSUPPORTED = "ORIGIN_UNSUPPORTED"
"""The chain ends in an agent with no witnessed memory supporting it."""

ORIGIN_CONTRADICTED = "ORIGIN_CONTRADICTED"
"""The chain ends in an agent whose own memory conflicts with what it passed on."""

CHAIN_BROKEN = "CHAIN_BROKEN"
"""The cited source record exists in no mind. Ambiguous; not an origin."""

CHAIN_TEMPORAL_VIOLATION = "CHAIN_TEMPORAL_VIOLATION"
"""A telling precedes the moment its source learned the thing told."""

CHAIN_TOO_DEEP = "CHAIN_TOO_DEEP"
"""The depth cap was reached before the chain resolved."""

CHAIN_CYCLE = "CHAIN_CYCLE"
"""The walk returned to an agent it had already visited."""

ALL_TERMINALS = (
    ORIGIN_WITNESSED,
    ORIGIN_UNSUPPORTED,
    ORIGIN_CONTRADICTED,
    CHAIN_BROKEN,
    CHAIN_TEMPORAL_VIOLATION,
    CHAIN_TOO_DEEP,
    CHAIN_CYCLE,
)

ORIGIN_TERMINALS = (ORIGIN_WITNESSED, ORIGIN_UNSUPPORTED, ORIGIN_CONTRADICTED)
"""The states that name an agent as the end of the chain."""

UNGROUNDED_ORIGINS = (ORIGIN_UNSUPPORTED, ORIGIN_CONTRADICTED)
"""Origin states where the agent's own memory did not back what it passed on.

`ORIGIN_WITNESSED` is excluded: a chain that ends in someone who actually saw
the thing is an honest chain, and carries no weight on the scoreboard.
"""

DEPTH_CAP = 5
"""Spec 5.7. A chain longer than this is reported, not followed further."""
