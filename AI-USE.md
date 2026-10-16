# AI assistance disclosure

This project was built with the coding assistant (the model vendor) as a coding assistant, by a
solo entrant, for the Graph Hacks: Context for AI Agents hackathon.

I reviewed every file in this repository. The log below records what was
generated with assistance, what I changed, and what I verified myself. My own
explanations of each subsystem, written in my own words, are in `docs/explain/`.

## Log

| Date (IST) | Milestone | What was generated with assistance | What I reviewed or changed myself |
|---|---|---|---|
| 2026-10-16 | M0 | `docker-compose.yml` (image pinned by tag + digest); FastAPI skeleton (`backend/app/{config,db,main}.py`); all nine spikes in `scripts/spikes.py`; the four xfail time-contract tests; Makefile rewrite (literal tabs, `.env` export, venv target); `requirements.txt` / `requirements-optional.txt`. the coding assistant also fixed its own bad fixture in spike 4 — the speaker was derived from the claim id, so it built two speakers instead of one; the assertion was left untouched and the fixture corrected. | **Pending my review.** To check: the pinned digest, the nine spike queries against the spec section each tests, and the two spec corrections recorded in `PROGRESS.md` (the `algo.SPpaths` node-parameter fix, and the fastmcp 4.x / starlette break). After the gate, on review feedback: renamed the spec file to `ALIBI_SPEC.md`, patched the 5.10 snippet in place, and verified the `self_contradictions` split for Q8 against the running server before writing it down. |
| 2026-10-16 | M1 | `backend/app/audit/{time_contract,coverage,verdicts,decide,engine}.py`; `minds/{queries,access}.py`; `case/{queries,graph,scoreboard}.py`; `world/{queries,generator}.py`; `agents/scripted.py`; the five test files `test_{coverage,audit,aggregation,world}.py` + `conftest.py`, written before the code they test. the coding assistant found and fixed two defects in its own generator by probing a generated world rather than trusting the green suite: the scripted claim cap took the *earliest* N claims, so every suspect lost the back half of their evening and the innocent-repeater claim — the whole reason `HEARSAY` exists — was being silently dropped; and `testify()` had no way to scope an answer to a time window. Both were fixed test-first. the coding assistant also removed the four `xfail(strict=True)` markers in a commit of its own, with no code change, so the diff shows no test assertion was edited alongside the code it tests. | **Pending my review.** To check: the decision table in `audit/decide.py` against the spec 5.5 table row by row; the `Gap`-nodes-on-partial-support-only reading of 5.5, recorded in `PROGRESS.md`; the Q8 weights in `case/scoreboard.py` (mine to set, not the coding assistant's); and finding 1 in `PROGRESS.md` — the honest repeater outscoring the culprit on seed 7777. the coding assistant flagged that as correct behaviour for a grounding measure and declined to retune the weights to put the culprit on top, citing spec 8.4 — that call needs my sign-off either way. |

## Design and specification

The build specification (`ALIBI_SPEC.md`) and design brief (`DESIGN_BRIEF.md`)
were developed in conversation with the coding assistant before the hackathon's coding window
opened. All implementation code was written during the window.
