/** One row of the level strip: a pixel head, a name, and a track of claims.
 *
 *  The channel owns the row: its height from the lanes it needs, the grid, and
 *  the text equivalent. It draws no fill of its own; every mark on it is a
 *  `ClaimBar` (brief 10).
 */
import type { Claim } from "../lib/case";
import { lookOf } from "../lib/case";
import { ClaimBar } from "./ClaimBar";
import { Sprite } from "./Sprite";

interface Props {
  label: string;
  /** Whose head to draw beside the label, if anyone's. */
  head: string | null;
  lanes: Claim[][];
  ariaLabel: string;
  drawnTo: number;
  selected: string | null;
  onSelect: (claimId: string) => void;
  dim?: boolean;
}

export function Channel({ label, head, lanes, ariaLabel, drawnTo, selected, onSelect, dim = false }: Props) {
  const n = Math.max(lanes.length, 1);
  return (
    <section
      className={`channel${dim ? " channel--re" : ""}`}
      aria-label={ariaLabel}
      style={{ height: `calc(var(--row-h) + ${n - 1} * var(--lane-pitch))` }}
    >
      <span className={`channel__label${dim ? " channel__label--dim" : ""}`}>
        {head && <Sprite look={lookOf(head)} scale={1} />}
        {label}
      </span>
      <div className="channel__track">
        {lanes.map((lane, i) =>
          lane.map((c) => (
            <ClaimBar key={c.id} claim={c} lane={i} drawnTo={drawnTo} selected={selected === c.id} onSelect={onSelect} />
          )),
        )}
      </div>
    </section>
  );
}
