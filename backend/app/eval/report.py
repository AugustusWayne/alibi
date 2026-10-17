"""Rendering. Nothing in this module computes a figure.

Every number printed here comes from `metrics.py`. The split exists so the
report can be read as a layout and trusted not to be doing arithmetic of its
own on the way to the terminal.

**The matrix is printed raw.** Counts, complete rows, no normalisation and no
rounding, with row and column totals so the reader can add it up. A summary of
a confusion matrix is not a confusion matrix, and spec 8.5's point — that a
credible negative result beats an unreproducible win — only holds if the raw
counts are on the page.
"""

from __future__ import annotations

from backend.app.audit.verdicts import ALL_VERDICTS, HEARSAY, INDETERMINATE
from backend.app.eval import metrics as m
from backend.app.referee.ground_truth import ALL_LABELS

_SHORT_LABEL = {
    "TRUE_CLAIM": "TRUE",
    "DELIBERATE_FABRICATION": "DELIB",
    "RELAYED_FALSEHOOD": "RELAY",
    "HONEST_ERROR": "HONEST",
}


def _pct(x: float | None) -> str:
    return "     n/a" if x is None else f"{100 * x:7.2f}%"


def confusion_table(c: m.Confusion) -> str:
    """The raw matrix: five verdict rows, four label columns, with totals."""
    head = f"{'verdict':<15}" + "".join(f"{_SHORT_LABEL[lab]:>8}" for lab in ALL_LABELS)
    lines = [
        head + f"{'| total':>10}",
        "-" * len(head + f"{'| total':>10}"),
    ]
    for verdict in ALL_VERDICTS:
        row = f"{verdict:<15}" + "".join(
            f"{c.cells[(verdict, lab)]:>8}" for lab in ALL_LABELS
        )
        lines.append(row + f"{'|':>3}{c.row_total(verdict):>7}")
    lines.append("-" * len(lines[0]))
    totals = f"{'total':<15}" + "".join(f"{c.column_total(lab):>8}" for lab in ALL_LABELS)
    lines.append(totals + f"{'|':>3}{c.total:>7}")
    return "\n".join(lines)


def pr_block(pr: m.PR) -> str:
    return "\n".join(
        [
            f"  {pr.question}",
            f"    predicted positive : {pr.predicted_positive}",
            f"    actual positive    : {pr.actual_positive}",
            f"    tp {pr.tp:>6}   fp {pr.fp:>6}   fn {pr.fn:>6}   tn {pr.tn:>6}",
            f"    precision {_pct(pr.precision)}   recall {_pct(pr.recall)}"
            f"   f1 {_pct(pr.f1)}",
        ]
    )


def origin_block(o: m.OriginAccuracy) -> str:
    lines = [
        "  origin identification (subset: ground truth names an originating agent)",
        f"    claims in subset          : {o.subset}",
        f"    chains that reached an origin state : {o.resolved}",
        f"    named the right agent     : {o.correct}",
        f"    named the wrong agent     : {o.misnamed}",
        f"    did not resolve to an origin : {o.unresolved}",
        f"    accuracy over resolved    : {_pct(o.accuracy_over_resolved)}",
        f"    accuracy over whole subset: {_pct(o.accuracy_over_subset)}",
        "",
        f"  chain outcomes over all {o.chains_total} chains traced in the run",
        f"    CHAIN_BROKEN              : {o.chain_broken}"
        f"  ({_pct(o.chain_broken_rate).strip()})",
        f"    CHAIN_TEMPORAL_VIOLATION  : {o.chain_temporal_violation}"
        f"  ({_pct(o.temporal_violation_rate).strip()})",
        "    reported beside the accuracy, never inside it: spec 5.7 calls",
        "    CHAIN_BROKEN ambiguous and not an origin, so scoring it as a miss",
        "    would claim the chain was wrong where it could not tell.",
        "",
        "    every terminal state seen:",
    ]
    for state, n in sorted(o.terminals.items()):
        lines.append(f"      {state:<28} {n:>6}")
    return "\n".join(lines)


def gap_block(g: m.GapPrecision) -> str:
    return "\n".join(
        [
            "  gap precision (every materialized Gap, against the subject's true route)",
            f"    gaps reported             : {g.total}",
            f"    subject truly elsewhere   : {g.elsewhere}",
            f"    subject in transit, at no place : {g.in_transit}",
            f"    subject at the claimed place    : {g.at_claimed_place}",
            f"    strict (elsewhere only)   : {_pct(g.strict)}",
            f"    loose  (not at the claimed place) : {_pct(g.loose)}",
            "    a gap is a statement about the speaker's memory, not about the",
            "    subject's route, so the third row is not an engine error: nobody",
            "    accounted for that span and it is still worth asking about.",
        ]
    )


def yield_block(y: m.GeneratorYield) -> str:
    lines = [
        "  generator yield",
        f"    seeds run                 : {y.seeds}",
        f"    worlds the generator rejected : {y.rejected}"
        f"  ({_pct(y.rejection_rate).strip()})",
        "      structurally zero, and reported rather than omitted: the floor plan",
        "      is connected by a spanning chain and every route pays its travel in",
        "      full at construction, so there is no infeasible world to discard and",
        "      no retry loop that could discard one.",
        f"    fabrications planted      : {y.fabrications}",
        f"    of those, relayed to someone : {y.relayed_fabrications}",
        f"    seeds with no relayed account : {y.without_relayed_fabrication}"
        f"  ({_pct(y.unrelayed_rate).strip()})",
    ]
    if y.seeds_without_relay:
        lines.append(
            f"      seeds: {', '.join(str(s) for s in y.seeds_without_relay)}"
        )
        lines.append(
            "      the culprit shared no room with an honest suspect after the"
        )
        lines.append(
            "      incident, so there was nobody to tell. Kept in every denominator"
        )
        lines.append("      and not redrawn (spec 8.4.2).")
    return "\n".join(lines)


def backing_block(records: list) -> str:
    rows = m.backing_by_verdict(records)
    lines = [
        "  the speaker's own witnessed memory, per verdict",
        f"    {'verdict':<15}{'backed':>8}{'unbacked':>10}",
    ]
    for verdict in ALL_VERDICTS:
        backed, unbacked = rows[verdict]
        lines.append(f"    {verdict:<15}{backed:>8}{unbacked:>10}")
    lines += [
        "    the breakdown behind grounding recall. HEARSAY and INDETERMINATE",
        "    claims are unbacked by witnessed memory and are deliberately not",
        "    reported as ungrounded, which is where that recall goes.",
    ]
    return "\n".join(lines)


def notes(records: list, tally: dict[str, int]) -> str:
    """The standing caveats, printed with the numbers rather than filed away."""
    lines = ["  reading these numbers"]
    if tally.get("UNSUPPORTED", 0) == 0:
        lines += [
            "    UNSUPPORTED is zero, and that is a property of the world, not a",
            "    bug: every claim a scripted suspect makes derives from some memory",
            "    it holds, so there is always something overlapping to find. The",
            "    verdict is exercised against a hand-built graph in test_audit.py.",
            "    An LLM suspect (M3) is the path that would produce it from a",
            "    generated world, by asserting something no memory bears on.",
        ]
    hearsay = tally.get(HEARSAY, 0)
    indeterminate = tally.get(INDETERMINATE, 0)
    lines += [
        f"    {hearsay} HEARSAY and {indeterminate} INDETERMINATE claims are neither",
        "    grounded nor reported as ungrounded. They are the engine declining to",
        "    conclude, which costs recall on both questions below and is the",
        "    behaviour the decision table is specified to have (spec 5.5).",
        "    No weight, threshold or knob was fitted to any of this (spec 8.4.5).",
    ]
    return "\n".join(lines)


def full_report(runs: list, records: list, gaps: list, *, title: str) -> str:
    """The whole thing, in one string, matrix first."""
    c = m.confusion(records)
    tally = m.verdict_tally(records)
    blocks = [
        "=" * 72,
        title,
        "=" * 72,
        "",
        f"{len(runs)} seeds, {len(records)} labelled claims, {len(gaps)} gaps, "
        f"scripted suspects, no LLM calls.",
        "",
        "-- confusion matrix: engine verdict x ground-truth label (raw counts) --",
        "",
        confusion_table(c),
        "",
        "  verdicts: spec 5.5 / audit/verdicts.py. labels: spec 8.1.",
        "  TRUE = TRUE_CLAIM, DELIB = DELIBERATE_FABRICATION,",
        "  RELAY = RELAYED_FALSEHOOD, HONEST = HONEST_ERROR.",
        "",
        notes(records, tally),
        "",
        "-- grounding vs falsehood " + "-" * 46,
        "",
        pr_block(m.strict_grounding_pr(records)),
        "",
        pr_block(m.falsehood_pr(records)),
        "",
        "  those two are the result. The same engine signal, scored against two",
        "  different truths: the engine reads grounding accurately and does not",
        "  thereby detect falsehood. What it misses on the second question is",
        "  claims that were grounded in some memory and false anyway, which is",
        "  the case no amount of auditing can close — and the reason this project",
        "  reports grounding rather than truth.",
        "",
        pr_block(m.grounding_pr(records)),
        "",
        backing_block(records),
        "",
        "-- origin identification " + "-" * 47,
        "",
        origin_block(m.origin_accuracy(records)),
        "",
        pr_block(m.chain_root_accuracy(records)),
        "    claims resting on more than one secondhand memory, and so having",
        f"    more than one chain: {m.multi_chain_claims(records)}. The engine traces",
        "    the first and this scores that one (spec 5.7).",
        "",
        "-- gaps " + "-" * 64,
        "",
        gap_block(m.gap_precision(gaps)),
        "",
        "-- generator " + "-" * 59,
        "",
        yield_block(m.generator_yield(runs)),
        "",
        "-- label tally " + "-" * 57,
        "",
    ]
    for label in ALL_LABELS:
        blocks.append(f"  {label:<26} {m.label_tally(records)[label]:>6}")
    blocks += ["", "=" * 72]
    return "\n".join(blocks)


def per_seed_table(runs: list) -> str:
    """One line per seed, so an outlier is visible rather than averaged away."""
    lines = [
        f"{'seed':>8}{'claims':>8}{'chains':>8}{'gaps':>7}{'culprit':>9}"
        f"{'relayed':>9}{'rejected':>10}",
        "-" * 59,
    ]
    for run in runs:
        lines.append(
            f"{run.seed:>8}{run.claim_count:>8}{run.chains:>8}{len(run.gaps):>7}"
            f"{run.culprit:>9}{run.relayed_fabrications:>9}{run.rejected:>10}"
        )
    return "\n".join(lines)
