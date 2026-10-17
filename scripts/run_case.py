"""One seed, one case, printed in full: every verdict beside its ground truth.

This is the eval's single-case view, and it generalises the seed-7777
comparison in `test_provenance.py` — the pattern of checking the engine's
answer against what the generator actually did, rather than against the
engine's own opinion. Use it to look at one world claim by claim; `run_eval`
aggregates the frozen set.

    python -m scripts.run_case --seed 10037
    python -m scripts.run_case --seed 10037 --keep       # leave graphs to inspect
    python -m scripts.run_case --seed 7777 --pathologies # the development world

No LLM is called. The suspects are scripted, which is the tested default path.

The ground-truth labels this prints are referee-only scoring vocabulary (spec
8.1, project rules rule 2). They appear here because this *is* the scoring tool.
They must never be written into a case graph, served from the API, or put in a
UI fixture.
"""

from __future__ import annotations

import argparse
import sys

from backend.app.config import settings
from backend.app.db import connect
from backend.app.eval import report
from backend.app.eval.harness import run_seed
from backend.app.world.generator import WorldSpec


def _claim_table(run) -> str:
    lines = [
        f"{'claim':<10}{'speaker':<9}{'subject':<9}{'place':<14}{'window':<12}"
        f"{'verdict':<15}{'label':<24}{'chain':<26}{'origin':<8}",
        "-" * 128,
    ]
    for c in run.claims:
        window = f"[{c.t0},{c.t1})"
        chain = c.chain_terminal or ""
        origin = c.chain_origin or ""
        truth_origin = f" (truth {c.truth_origin})" if c.truth_origin else ""
        lines.append(
            f"{c.claim_id:<10}{c.speaker:<9}{c.subject:<9}{c.place:<14}{window:<12}"
            f"{c.verdict:<15}{c.label:<24}{chain:<26}{origin:<8}{truth_origin}"
        )
    return "\n".join(lines)


def _gap_table(run) -> str:
    if not run.gaps:
        return "  no gaps materialized in this case."
    lines = [
        f"  {'claim':<10}{'subject':<9}{'place':<14}{'gap':<12}{'truth':<20}",
        "  " + "-" * 63,
    ]
    for g in run.gaps:
        lines.append(
            f"  {g.claim_id:<10}{g.subject:<9}{g.place:<14}"
            f"{f'[{g.t0},{g.t1})':<12}{g.truth:<20}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument(
        "--keep",
        action="store_true",
        help="leave the seed's graphs on the server instead of dropping them",
    )
    parser.add_argument(
        "--pathologies",
        action="store_true",
        help="also plant the broken-chain and temporal-violation chains",
    )
    args = parser.parse_args(argv)

    db = connect()
    db.connection.ping()
    spec = WorldSpec(
        plant_broken_chain=args.pathologies,
        plant_temporal_violation=args.pathologies,
    )
    run = run_seed(db, args.seed, spec=spec, drop=not args.keep)

    print("=" * 72)
    print(f"seed {run.seed} — one case in full")
    print("=" * 72)
    print(
        f"FalkorDB {settings.falkor_host}:{settings.falkor_port}  "
        f"culprit (ground truth) {run.culprit}  "
        f"claims {run.claim_count}  chains {run.chains}  gaps {len(run.gaps)}"
    )
    print(f"world counts: {run.counts}")
    print()
    print("-- every claim: the engine's verdict beside the generator's label --")
    print()
    print(_claim_table(run))
    print()
    print("-- gaps --")
    print()
    print(_gap_table(run))
    print()
    print(
        report.full_report(
            [run], list(run.claims), list(run.gaps), title=f"seed {run.seed} — metrics"
        )
    )
    if args.keep:
        print(f"\ngraphs left in place for seed {run.seed}.")
    disagreed = [c for c in run.claims if c.chain_origin and c.truth_origin
                 and c.chain_origin != c.truth_origin]
    if disagreed:
        print("\nchains that named an agent other than the one the plan records:")
        for c in disagreed:
            print(f"  {c.claim_id}: chain says {c.chain_origin}, plan says {c.truth_origin}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
