# Driving an AI coding assistant on Alibi — a playbook

Hour 0 was Oct 15, 00:01 IST. This playbook was written at hour 14.4.

---

## 1. The operating model

The assistant is very good at producing code and bad at knowing when it is done.
**You supply "done."** That is the whole job.

So the unit of work is not a task, it is a **gate**: a command whose output you
read with your own eyes. Every session ends at a gate that either passes visibly
or does not. "I've implemented the audit engine" is not a gate. `make verify`
printing `VERIFY OK` after 31 passing tests is a gate.

Three things follow from the hackathon rules, and they shape everything:

- You must be able to explain the code → the workflow has to produce
  understanding as a byproduct. Hence the explain-back ritual (section 5).
- Fully AI-generated projects may be rejected → `AI-USE.md` is honest and written
  as you go, and `docs/explain/` is in your own words.
- FalkorDB must be load-bearing → no milestone is done if its graph work is
  mocked.

And one thing follows from how the tool works:

- **Chat messages do not survive context compaction. Files do.** Over 80 hours
  The assistant will compact many times. Anything you need to still be true at hour
  70 goes in the project rules, `PROGRESS.md` or a spec — never in a chat message.

---

## 2. Before you start (20 minutes, do it now)

```bash
mkdir alibi && cd alibi && git init
# drop in: ALIBI_SPEC.md, DESIGN_BRIEF.md, BUILD_PLAYBOOK.md
# from bootstrap/: the project rules, PROGRESS.md, AI-USE.md, Makefile
mkdir -p docs/design docs/explain
# copy the six artboard .dc.html files into docs/design/
git add -A && git commit -m "spec, design brief, rules, bootstrap"
```

Commit before the assistant touches anything. You want a clean point to roll back to.

The project rules file is deliberately short. It is loaded into every session, so it is
precious context — if it were 400 lines it would get skimmed. It states the rules
and points at the specs for detail. Resist the urge to grow it; add to
`PROGRESS.md` instead.

---

## 3. Session discipline

**One milestone per session.** Start a fresh session for each. Reasons: context
stays clean, the specs get read at full fidelity, and a session that goes wrong is
cheap to abandon.

Every session follows the same shape:

1. The assistant reads the project rules, then `PROGRESS.md`, then **only the spec
   sections that milestone needs**. Reading the whole 722-line spec every session
   wastes the context you need for code.
2. It states the plan in a few lines. You read it. If it is building more than the
   milestone, say so now — this is the cheapest moment to catch over-scoping.
3. It writes tests first where the milestone says so, then implements.
4. It runs `make verify` and pastes the output.
5. It updates `PROGRESS.md` and `AI-USE.md`, then stops.
6. You do the explain-back ritual.

**Never let a session roll into the next milestone.** The gate is the point.

---

## 4. The prompts

Copy these. The precision is doing work — each one names what to read, what to
build, and what the gate is.

### M0 — spikes and infrastructure

> Read the project rules, then `ALIBI_SPEC.md` in full. This is the only session where
> you read all of it.
>
> Implement M0 only: `docker-compose.yml` with a **pinned** falkordb image tag, a
> Python 3.12 FastAPI skeleton using the official `falkordb` client, the Makefile,
> and `scripts/spikes.py` that runs each numbered spike from spec section 12
> against a scratch graph and prints `PASS` or `FAIL` per spike with the exact
> error text on failure. Also scaffold `backend/tests/test_time_contract.py` with
> the four boundary cases from spec 4.0, marked xfail with a reason — they should
> fail until M1.
>
> Then run `make up` and `make spikes`, paste the complete output, fill in the
> spike table in `PROGRESS.md` including failures with their error text, and stop.
> Do not start M1. If a spike fails, do not invent a workaround — report it with
> the fallback options from section 12.

**Gate:** you have read nine PASS/FAIL lines and the spike table is filled in.

### M1 — world and audit engine (the important one)

> Read the project rules and `PROGRESS.md`. Read **only** sections 4 and 5 of
> `ALIBI_SPEC.md`.
>
> Implement M1: the deterministic world generator, the mind writer, and the audit
> engine with all five verdict states, plus scripted suspects as test fixtures.
> **No LLM calls at all in this milestone.**
>
> Write the tests first:
> - `test_time_contract.py` — the four boundary cases from 4.0, now un-xfailed
> - `test_coverage.py` — all eleven cases from the table in 5.4
> - `test_audit.py` — one test per verdict, plus the conflict-beats-support case
>   and the partial-is-not-full case from 5.5
> - `test_world.py` — same seed gives an identical world; every route is
>   travel-feasible
>
> Then implement until they pass. Show me `make verify` output. Then stop.

**Gate:** `VERIFY OK` with every test visible, and you can point at the test that
proves conflict beats support.

### M2 — provenance

> Read the project rules and `PROGRESS.md`. Read only sections 4.2 and 5.7 of
> `ALIBI_SPEC.md`.
>
> Implement Transmission nodes with `learned_at`, the cross-graph provenance trace
> with all seven terminal states, and the temporal consistency check.
>
> Tests: a planted innocent-repeater chain traced to its origin and checked
> against ground truth; a planted temporal violation detected as
> `CHAIN_TEMPORAL_VIOLATION`; a planted broken chain reported as `CHAIN_BROKEN`
> and **not** as an origin. Show `make verify`. Stop.

**Gate:** the trace names the right origin on a world where you know the answer.

### M3 — LLM suspects behind the cache

> Read the project rules and `PROGRESS.md`. Read only section 7 of `ALIBI_SPEC.md`.
>
> Add LLM-driven suspects behind the cache wrapper, keyed by
> `(seed, agent, prompt_hash)` in SQLite, with the per-case call cap enforced in
> code. Keep `--scripted` working; it stays the default for tests.
>
> Gate: run one full case twice and show me that the second run makes zero API
> calls and produces byte-identical output. Stop.

### M4 — detective loop

> Read the project rules and `PROGRESS.md`. Read only sections 5.9–5.12 and 7 of
> `ALIBI_SPEC.md`.
>
> Implement the detective's typed tools, including `list_gaps`, and materialize
> Q5–Q8 on a live case. The graph computes the checks; the model only chooses what
> to ask. Gate: the detective solves one seeded world end to end, and the
> transcript shows it asking about a specific gap. Stop.

### M5 — the case board (separate session, do not mix with backend work)

> Read the project rules and `DESIGN_BRIEF.md` in full. **Do not read
> `ALIBI_SPEC.md`** — you do not need it.
>
> `docs/design/` holds six reference artboards as HTML. These are the intended
> rendering, token for token. Read `Recorder.dc.html` first; it is the target for
> the case board.
>
> Build the case board: React + TS + Vite, `tokens.css` holding the custom
> properties from brief section 3, one `Channel` component and one `ClaimBar`.
> `ClaimBar` owns all five fills and nothing else does. Time maps to percentage in
> a single `tickToPercent` helper.
>
> Before you tell me a component is done, go through brief section 7 item by item
> and tell me it passes each one.

**The artboards are the leverage here.** They are literal HTML with real hex
values, so the assistant has a reference implementation rather than a description.
This is the single best defence against the UI drifting back to the default look.

### M6 — evaluation

> Read the project rules and `PROGRESS.md`. Read only section 8 of `ALIBI_SPEC.md`.
>
> Build the eval harness. **Commit `eval/seeds.json` before any tuning** and tell
> me when you have. Primary metric is audit precision/recall per claim with the
> full confusion matrix; case accuracy is secondary and carries a Wilson interval.
> Report the generator's rejection rate. Run all arms on identical worlds.

---

## 5. The explain-back ritual (do not skip this)

After each gate passes, two steps:

1. Ask the assistant: *"Explain this milestone to me as if I'm reviewing your PR.
   What each module does, why the decision table is ordered that way, and where
   the parts you're least sure about are."*
2. **Then you** write 5–10 lines in your own words into
   `docs/explain/m<N>.md`. Not copy-paste. Your words.

If you cannot write those lines, you do not understand that subsystem — and you
have just found that out at hour 20 instead of in front of a judge. Go back and
dig in now; it is never cheaper than at this moment.

This single ritual does four jobs: satisfies "you must be able to explain the
code", catches misunderstandings early, drafts your README, and writes your video
script.

---

## 6. Failure modes, and what each one actually means

| What you see | What is actually happening | Do this |
|---|---|---|
| "All tests pass" with no output shown | It may not have run them | Make it paste raw `make verify` output. Output or it did not happen. |
| A test was edited in the same change as the fix | It weakened the test to go green | Revert the test, keep the fix, re-run. Project rules rule 7 forbids this. |
| A query wrapped in `try/except` returning `[]` | Silently degrading to empty results, so the audit looks fine and finds nothing | Make it raise. Spike the query properly. Rule 8. |
| Verdict logic is an `if/elif` chain with early returns | v1's precedence bug is back: one supporting fact masks a contradicting one | Point at spec 5.5. Must gather all evidence, then decide. |
| Any model call near a verdict | It took the easy path | Rule 1. Delete it. |
| The UI has rounded corners, shadows, or Inter | Context compacted and the default look came back | New session, re-read `DESIGN_BRIEF.md` section 7, fix against the artboards. |
| Many files created, nothing runs | Over-scaffolding | `git reset --hard` to the last tag, re-prompt with a narrower scope. |
| Answers get vaguer, it forgets decisions | Context compacted | Stop. New session. Read the project rules + `PROGRESS.md` + one spec section. |
| A spike failed but it kept building | It did not treat the gate as a gate | Roll back to the gate. Decide the fallback yourself, record it in `PROGRESS.md`. |
| Benchmark numbers appear implausibly fast | LLM calls stubbed or mocked | Check the cache DB actually has rows and the call counter is non-zero. |
| Coverage above 100%, or a gap that is negative | Unmerged intervals being summed | The bug I already hit. `test_coverage.py` case 6 catches it. |

---

## 7. High-leverage tests worth asking for by name

These are cheap and each one closes a whole class of bug. Ask for them
explicitly; they are not all in the spec.

- **Coverage property test** (Hypothesis, ~10 lines): for any random set of
  intervals, `covered + sum(gap lengths) == claim duration`. This is the invariant
  that the overlapping-intervals bug violated. Highest value test in the repo.
- **Partition test:** no claim pair is ever flagged as both `exclusive_presence`
  and `impossible_travel`. The two checks must cover disjoint cases.
- **Audit idempotence:** running the audit twice on the same claim yields the same
  verdict and does not duplicate `SUPPORTED_BY` edges. `MERGE` should guarantee
  this; assert it.
- **Isolation test:** a fact that exists only in agent B's graph is unreachable
  through agent A's tool surface, and no public tool signature accepts a graph
  name. This is also your Track 02 evidence — make it a named, passing test.
- **Determinism test:** hash the generated world structure; the same seed must
  produce the same hash.
- **Transmission consistency:** every generated transmission satisfies
  `source.learned_at <= tick`.

---

## 8. The adversarial review pattern

The spec says high-stakes work should be checked by something that did not produce
it. Concretely, once after M1 and once after M2:

Open a **fresh** assistant session. Give it only the relevant spec section and
the audit engine source — not the tests, not the conversation. Ask:

> Here is a specification and an implementation. Find inputs where this
> implementation produces a verdict the specification does not call for. Do not
> fix anything; list concrete failing cases with the inputs.

A reviewer that has not seen the tests cannot be reassured by them. This costs ten
minutes and has a real chance of finding the one bug that would have cost you the
track.

---

## 9. Context management, concretely

- One milestone per session. Never two.
- Name the spec sections to read. Never "read the spec."
- When answers start getting vague or it re-asks something settled, that is
  compaction. Stop mid-task if you must; a fresh session that re-reads
  `PROGRESS.md` is faster than fighting a degraded one.
- `PROGRESS.md` under 80 lines. Delete stale detail. It is a working state file,
  not a journal.
- Keep backend and frontend in **separate sessions**. Mixing them means the design
  brief gets compacted out during engine work, and the UI drifts.

---

## 10. Re-baselined schedule (wall clock, IST)

You are 14.4 hours in with no code. Shifted and compressed:

| By | Milestone |
|---|---|
| Oct 15, 20:00 | M0 gate — spikes all run and recorded |
| Oct 16, 12:00 | M1 gate — audit engine, five verdicts, tests green |
| Oct 16, 22:00 | M2 gate — provenance trace working |
| Oct 17, 08:00 | M3 gate — LLM suspects, deterministic replay |
| Oct 17, 16:00 | M4 gate — detective solves a world end to end |
| Oct 18, 04:00 | M5 — case board matching the artboards |
| Oct 18, 10:00 | M6 — benchmark run, numbers in hand |
| **Oct 18, 12:00** | **Backup demo video recorded.** Submittable from here. |
| Oct 18, 14:00 | Feature freeze |
| Oct 18, 20:00 | Submitted. Deadline is 23:59; keep the buffer. |

**Assume MCP is cut as of now.** It is cosmetic for Track 01, adds integration
risk, and section 5.9 of the spec already has it on the cut list. If M4 lands
early you can add it back.

The backup video at Oct 18 12:00 is not optional. A complete, submittable video
before the final polish is the cheapest insurance in this plan.

---

## 11. What you do while it works

There is real wall-clock waiting — cache warming, benchmark runs, docker pulls.
Spend it on:

- `docs/explain/` entries while the milestone is fresh
- the README's graph-model section (required by the rules, and you have the schema)
- rehearsing the 90-second video out loud against the script in spec section 16
- the blog post for the side prize: "grounded is not the same as true" is the
  strongest angle you have, and it writes itself from `docs/explain/`

Do not spend it starting the next milestone in a second session. Two sessions
writing to the same repo will produce a merge you do not have time for.

---

## 12. The two things to remember

1. **The gate is the unit of work.** Not the task. You supply "done", and done
   means output you have read.
2. **The project rules file is your only persistent instruction channel.** Anything you want
   to still be true at hour 70 belongs in a file, not in a message.
