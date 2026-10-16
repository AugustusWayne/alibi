# Alibi — rules for this repo

Read `PROGRESS.md` next. Read only the section of `ALIBI_SPEC.md` the current
milestone needs. Do not read the whole spec unless you are starting M0.

## What this is

An epistemic audit layer for multi-agent systems, on FalkorDB. Each agent has a
private memory graph. Every claim an agent makes is audited structurally against
that agent's own memory: is it grounded, partly grounded, contradicted,
secondhand, or unaccounted for. A detective agent investigates using graph tools.
The mystery is the testbed; the audit engine is the product.

Specs: `ALIBI_SPEC.md` (build spec), `DESIGN_BRIEF.md` (all frontend work).

## Hard rules — these are not preferences

1. **No LLM in the verdict path.** Verdicts, coverage, contradictions and scores
   are computed by Cypher plus deterministic Python. A model never classifies a
   claim. If a task seems to need an LLM judge, stop and say so.
2. **A verdict describes grounding, not intent.** No code path, comment, log line,
   API field or UI string may call a claim a lie. `UNSUPPORTED` means nothing was
   found. Deception labels exist only in `backend/app/referee/` and only for
   scoring. The words "lie", "liar", "lying", "deception" never appear in the UI.
3. **Gather all evidence, then decide.** No `LIMIT 1` in any audit query. No
   if/elif chain that returns on first match. See spec 5.5 for the decision table.
4. **All intervals are half-open `[t0, t1)`.** Overlap uses strict inequalities.
   See spec 4.0. The boundary tests must stay green.
5. **Only the world generator creates provenance.** The audit materializes only
   what it proved. Never invent a link to make an answer look grounded.
6. **No tool exposed to an agent accepts a graph name or an agent id.** Only the
   referee may read a mind other than the caller's own.
7. **Never weaken a test to make it pass.** If a test fails, the code is wrong, or
   the test encodes a misunderstanding — say which and ask. Editing a test and the
   code it tests in the same change is forbidden.
8. **Never wrap a failing query in try/except that returns empty.** A broken query
   must raise loudly.
9. **Every LLM call goes through the cache wrapper and the per-case cap.**
10. **Frontend: `DESIGN_BRIEF.md` section 7 is a forbidden list, not advice.**
    Check your work against it before saying a component is done. No Tailwind, no
    component library, no rounded corners, no shadows, no Inter.

## Workflow rules

- **Cypher lives in `backend/app/**/queries.py`** as named constants, each with a
  one-line comment stating the graph question it answers. No inline Cypher in
  routes or services.
- **One milestone per session.** Do not start the next milestone. When the gate
  passes, update `PROGRESS.md` and `AI-USE.md` and stop.
- **A gate passes only with visible output.** Paste the real command output. Never
  report a test suite as passing without showing it.
- **`make verify` must pass before you claim a milestone is done.**
- **On a spike or assumption failure, stop and report.** Do not invent a
  workaround, do not mock the dependency, do not proceed to the next milestone.
  Print the exact error text and the fallback options from spec section 12.
- **Small commits.** Tag `m0`...`m6` at each gate. Before any risky refactor,
  branch.
- **Append to `AI-USE.md` every session.** What you generated, what changed.
- **Do not create files outside the milestone's scope.** If you think the repo
  needs a new module, say why first.

## Commands

```
make up        # falkordb in docker, pinned tag
make spikes    # run the FalkorDB assumption spikes, PASS/FAIL each
make test      # pytest, backend
make verify    # lint + test + invariants. the gate.
make eval      # benchmark over frozen seeds
```
