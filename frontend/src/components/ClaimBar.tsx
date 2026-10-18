/** One claim as a mark on the level strip.
 *
 *  **The five fills live here and nowhere else** (brief 10). The fill carries
 *  the verdict, so the mark survives grayscale and colourblindness by
 *  construction. Anything else that shows a fill (the inventory, the case-log
 *  badge, a witness line) asks this module for it through `Fill`.
 *
 *  A gap gets no colour: it is the track showing through.
 */
import type { CSSProperties } from "react";

import type { Claim, Verdict } from "../lib/case";
import { nameOf } from "../lib/case";
import { spanStyle, tickToClock, tickToPercent } from "../lib/time";

export function fillClass(verdict: Verdict): string {
  return `fill fill--${verdict.toLowerCase()}`;
}

/** A verdict's fill as a swatch, for places that teach or label it. */
export function Fill({ verdict, style, className = "" }: { verdict: Verdict; style?: CSSProperties; className?: string }) {
  return (
    <span className={`${fillClass(verdict)} ${className}`} style={style} aria-hidden="true">
      {verdict === "INDETERMINATE" && <i className="fill__covered" style={{ left: 0, width: "50%" }} />}
      {verdict === "CONTRADICTED" && <i className="fill__strike" />}
    </span>
  );
}

const laneTop = (lane: number, extra = "0px") =>
  `calc(var(--bar-top) + ${lane} * var(--lane-pitch) + ${extra})`;

/** A tick as a percentage of the drawn part of one bar. Still one mapping:
 *  it rebases `tickToPercent` onto the bar's span rather than mapping time again. */
function within(tick: number, from: number, to: number): number {
  const base = tickToPercent(from);
  return ((tickToPercent(tick) - base) / (tickToPercent(to) - base)) * 100;
}

/** The covered part of a claim: its window minus the proved gaps. */
function coveredSpans(c: Claim): [number, number][] {
  const spans: [number, number][] = [];
  let cursor = c.t0;
  for (const [g0, g1] of [...c.gaps].sort((a, b) => a[0] - b[0])) {
    if (g0 > cursor) spans.push([cursor, g0]);
    cursor = Math.max(cursor, g1);
  }
  if (cursor < c.t1) spans.push([cursor, c.t1]);
  return spans;
}

interface Props {
  claim: Claim;
  lane: number;
  /** The playhead. Ink cannot run ahead of it: a claim still being written stops there. */
  drawnTo: number;
  selected: boolean;
  onSelect: (claimId: string) => void;
}

export function ClaimBar({ claim, lane, drawnTo, selected, onSelect }: Props) {
  const end = Math.min(claim.t1, drawnTo);
  if (end <= claim.t0) return null;
  const about = claim.subject === claim.speaker ? "" : ` about ${nameOf(claim.subject)}`;

  return (
    <>
      <button
        type="button"
        className={`bar ${fillClass(claim.verdict)}${selected ? " bar--selected" : ""}`}
        style={{ ...spanStyle(claim.t0, end), top: laneTop(lane) }}
        onClick={() => onSelect(claim.id)}
        aria-pressed={selected}
        aria-label={`claim ${claim.id}, ${nameOf(claim.speaker)}${about}, ${claim.place}, ${tickToClock(claim.t0)} to ${tickToClock(claim.t1)}, ${claim.verdict}`}
      >
        {claim.verdict === "INDETERMINATE" &&
          coveredSpans(claim)
            .filter(([a]) => a < end)
            .map(([a, b]) => (
              <i
                key={a}
                className="fill__covered"
                style={{ left: `${within(a, claim.t0, end)}%`, width: `${within(Math.min(b, end), claim.t0, end) - within(a, claim.t0, end)}%` }}
              />
            ))}
        {claim.verdict === "CONTRADICTED" && <i className="fill__strike" />}
      </button>

      {/* Brief 5.7: the open bracket under each span nothing accounted for. */}
      {claim.verdict === "INDETERMINATE" &&
        claim.gaps
          .filter(([g0]) => g0 < end)
          .map(([g0, g1]) => {
            const g = Math.min(g1, end);
            return (
              <span key={g0}>
                <span className="bracket" style={{ ...spanStyle(g0, g), top: laneTop(lane, "var(--bar-h) + 1px") }} />
                {tickToPercent(g) - tickToPercent(g0) >= 3 && (
                  <span className="bracket__count" style={{ left: `${tickToPercent(g)}%`, top: laneTop(lane, "var(--bar-h) - 3px") }}>
                    {g - g0}
                  </span>
                )}
              </span>
            );
          })}
    </>
  );
}
