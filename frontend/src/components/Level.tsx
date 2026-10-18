/** The level strip (brief 5.7): the recorder as a level timeline.
 *
 *  One row per suspect holding their claims about themselves, then `RE:` the
 *  selected claim's subject, holding what everyone else said about them. The
 *  axis is always the full case window. Right of the playhead is fog that
 *  lifts as it passes.
 */
import { useMemo } from "react";

import type { Claim } from "../lib/case";
import { caseFile, claimsAbout, nameOf, ownClaims, packLanes } from "../lib/case";
import { TICK_MAX, tickToPercent } from "../lib/time";
import { Channel } from "./Channel";
import { Lens } from "./Sprite";

interface Props {
  tick: number;
  selected: Claim | null;
  onSelect: (claimId: string) => void;
}

export function Level({ tick, selected, onSelect }: Props) {
  const rows = useMemo(
    () =>
      caseFile.suspects.map((s) => {
        const own = ownClaims(s.id);
        const all = caseFile.claims.filter((c) => c.speaker === s.id);
        return {
          id: s.id,
          lanes: packLanes(own),
          aria: `${nameOf(s.id)}, ${own.length} claims about themselves, ${all.reduce((n, c) => n + c.uncovered, 0)} minutes unaccounted across all ${all.length} of their claims`,
        };
      }),
    [],
  );
  const subject = selected?.subject ?? null;
  const about = useMemo(() => (subject ? packLanes(claimsAbout(subject)) : []), [subject]);
  const at = `${tickToPercent(tick)}%`;

  return (
    <div className="level">
      <div className="level__hours" aria-hidden="true">
        {caseFile.meta.hour_labels.map(({ tick: t, label }) => (
          <span key={t} className={t >= TICK_MAX ? "level__hour level__hour--end" : "level__hour"} style={t >= TICK_MAX ? undefined : { left: `${tickToPercent(t)}%` }}>
            {label}
          </span>
        ))}
      </div>
      <div className="level__rows">
        {rows.map((r) => (
          <Channel key={r.id} label={nameOf(r.id)} head={r.id} lanes={r.lanes} ariaLabel={r.aria} drawnTo={tick} selected={selected?.id ?? null} onSelect={onSelect} />
        ))}
        {subject && (
          <Channel
            label={`RE: ${nameOf(subject)}`}
            head={null}
            lanes={about}
            ariaLabel={`what everyone else said about ${nameOf(subject)}, ${about.flat().length} claims`}
            drawnTo={tick}
            selected={selected?.id ?? null}
            onSelect={onSelect}
            dim
          />
        )}
        <div className="level__overlay" aria-hidden="true">
          <div className="fog" style={{ left: at }} />
          <div className="playhead" style={{ left: at }}><Lens /></div>
        </div>
      </div>
      <div className="level__keys" aria-hidden="true">
        <span><b>SPACE</b> PLAY/PAUSE</span>
        <span><b>ENTER</b> SELECT</span>
        <span><b>ESC</b> BACK</span>
        <i className="level__cursor" />
      </div>
    </div>
  );
}
