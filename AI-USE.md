# AI assistance disclosure

This project was built with the coding assistant (the model vendor) as a coding assistant, by a
solo entrant, for the Graph Hacks: Context for AI Agents hackathon.

I reviewed every file in this repository. The log below records what was
generated with assistance, what I changed, and what I verified myself. My own
explanations of each subsystem, written in my own words, are in `docs/explain/`.

## Log

| Date (IST) | Milestone | What was generated with assistance | What I reviewed or changed myself |
|---|---|---|---|
| 2026-10-16 | M0 | `docker-compose.yml` (image pinned by tag + digest); FastAPI skeleton (`backend/app/{config,db,main}.py`); all nine spikes in `scripts/spikes.py`; the four xfail time-contract tests; Makefile rewrite (literal tabs, `.env` export, venv target); `requirements.txt` / `requirements-optional.txt`. the coding assistant also fixed its own bad fixture in spike 4 — the speaker was derived from the claim id, so it built two speakers instead of one; the assertion was left untouched and the fixture corrected. | **Pending my review.** To check: the pinned digest, the nine spike queries against the spec section each tests, and the two spec corrections recorded in `PROGRESS.md` (the `algo.SPpaths` node-parameter fix, and the fastmcp 4.x / starlette break). |

## Design and specification

The build specification (`FalkorDB Alibi Spec (1).md`, referred to throughout as
`ALIBI_SPEC.md`) and design brief (`DESIGN_BRIEF.md`)
were developed in conversation with the coding assistant before the hackathon's coding window
opened. All implementation code was written during the window.
