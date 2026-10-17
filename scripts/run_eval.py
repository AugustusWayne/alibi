"""The benchmark: every frozen seed, audited and scored, aggregated.

    make eval
    python -m scripts.run_eval --seeds eval/seeds.json
    python -m scripts.run_eval --seeds eval/seeds.json --pathologies
    python -m scripts.run_eval --seeds eval/seeds.json --out eval/results.json

Scripted suspects, no LLM calls, no cost, no flakiness. The seed list is read
and never written: it was frozen before any seed in it was generated (spec
8.4.3), and re-drawing it after a number is known voids every figure already
recorded.

**Nothing in this run is tuned.** Every seed gets the same `WorldSpec`, the
scoreboard weights are not consulted, and a seed that produces an awkward
result stays in the denominator. Spec 8.5: a credible negative result beats an
unreproducible win.

The ground-truth labels in the output are referee-only scoring vocabulary (spec
8.1, project rules rule 2). This is the scoring tool, the one place they
belong. They are never written to a case graph, served from the API, or used in
a UI fixture — `--out` writes a scoring artifact, not a fixture.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from backend.app.config import settings
from backend.app.eval import metrics as m
from backend.app.eval import report
from backend.app.eval.harness import all_claims, all_gaps, run_seeds
from backend.app.eval.seeds import DEFAULT_PATH, load_seeds
from backend.app.world.generator import WorldSpec


def _results_document(runs, records, gaps, *, seeds_path: str, spec: WorldSpec) -> dict:
    """Everything a reader would need to check the numbers themselves."""
    c = m.confusion(records)
    return {
        "seeds_file": seeds_path,
        "seeds": [r.seed for r in runs],
        "spec": asdict(spec),
        "falkordb": f"{settings.falkor_host}:{settings.falkor_port}",
        "claims": len(records),
        "gaps": len(gaps),
        "confusion": {f"{v}|{lab}": n for (v, lab), n in sorted(c.cells.items())},
        "verdict_tally": m.verdict_tally(records),
        "label_tally": m.label_tally(records),
        "grounding_strict": asdict(m.strict_grounding_pr(records)),
        "full_coverage": asdict(m.grounding_pr(records)),
        "falsehood": asdict(m.falsehood_pr(records)),
        "origin": asdict(m.origin_accuracy(records)),
        "chain_root": asdict(m.chain_root_accuracy(records)),
        "gap_precision": asdict(m.gap_precision(gaps)),
        "generator_yield": asdict(m.generator_yield(runs)),
        "per_seed": [
            {
                "seed": r.seed,
                "culprit": r.culprit,
                "claims": r.claim_count,
                "chains": r.chains,
                "gaps": len(r.gaps),
                "rejected": r.rejected,
                "fabrications": r.fabrications,
                "relayed_fabrications": r.relayed_fabrications,
            }
            for r in runs
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", default=str(DEFAULT_PATH))
    parser.add_argument(
        "--pathologies",
        action="store_true",
        help="plant the broken-chain and temporal-violation chains in every world, "
        "which is the only way those two terminal states arise from a generated "
        "world at all",
    )
    parser.add_argument("--out", help="also write the figures as JSON to this path")
    parser.add_argument(
        "--keep",
        action="store_true",
        help="leave every seed's graphs on the server (24 seeds is 216 graphs)",
    )
    args = parser.parse_args(argv)

    # Imported here so --help works without a database.
    from backend.app.db import connect

    seeds = load_seeds(args.seeds)
    db = connect()
    db.connection.ping()

    spec = WorldSpec(
        plant_broken_chain=args.pathologies,
        plant_temporal_violation=args.pathologies,
    )
    print(
        f"{len(seeds)} frozen seeds from {args.seeds}, "
        f"FalkorDB {settings.falkor_host}:{settings.falkor_port}, "
        f"pathological chains {'planted' if args.pathologies else 'not planted'}"
    )
    print(f"seeds: {', '.join(str(s) for s in seeds)}")
    print()

    def progress(run) -> None:
        print(
            f"  seed {run.seed:>7}: {run.claim_count:>4} claims, "
            f"{run.chains:>3} chains, {len(run.gaps):>3} gaps, culprit {run.culprit}",
            flush=True,
        )

    runs = run_seeds(db, seeds, spec=spec, drop=not args.keep, on_seed=progress)
    records = all_claims(runs)
    gaps = all_gaps(runs)

    title = "ALIBI eval — frozen seeds, scripted suspects, no LLM"
    if args.pathologies:
        title += " (pathological chains planted)"
    print()
    print(report.per_seed_table(runs))
    print()
    print(report.full_report(runs, records, gaps, title=title))

    if args.out:
        doc = _results_document(runs, records, gaps, seeds_path=args.seeds, spec=spec)
        Path(args.out).write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
        print(f"\nfigures written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
