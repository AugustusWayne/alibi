"""The five verdict states, and what each one is allowed to mean.

**A verdict describes grounding, not intent** (project rules, rule 2). Every
string in this module is user-visible, so read these definitions as the contract for
what the UI is permitted to say:

- `SUPPORTED`     — the speaker's own witnessed memory accounts for the claim.
- `UNSUPPORTED`   — nothing in the speaker's memory was found that bears on it.
                    Nothing was found. That is all it means.
- `CONTRADICTED`  — the speaker's own witnessed memory places the subject
                    somewhere else at an overlapping time.
- `INDETERMINATE` — the evidence is partial or unresolvable; the uncovered
                    spans are recorded as the detective's open questions.
- `HEARSAY`       — the only support is secondhand, so the claim's grounding
                    depends on someone else's memory.

None of the five means a claim is false, and none of them is a judgement about
the speaker. A claim can be UNSUPPORTED because the witness blinked. The
ground-truth labels used for scoring live only in `backend/app/referee/` and
never reach the API or the UI.
"""

from __future__ import annotations

SUPPORTED = "SUPPORTED"
UNSUPPORTED = "UNSUPPORTED"
CONTRADICTED = "CONTRADICTED"
INDETERMINATE = "INDETERMINATE"
HEARSAY = "HEARSAY"

PENDING = "PENDING"
"""A claim that has been ingested but not yet audited. Not a verdict."""

ALL_VERDICTS = (SUPPORTED, UNSUPPORTED, CONTRADICTED, INDETERMINATE, HEARSAY)

# How a fact was acquired. Only `witnessed` can ground or refute a claim;
# `hearsay` defers the question to another mind; `inferred` does neither.
WITNESSED = "witnessed"
HEARSAY_SRC = "hearsay"
INFERRED = "inferred"

# Claim modality (spec 5.1).
THROUGHOUT = "THROUGHOUT"
AT_SOME_POINT = "AT_SOME_POINT"
