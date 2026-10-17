/** The HUD (brief 5.1) and the JRPG window (brief 5.2). */
import type { ReactNode } from "react";

import { caseFile } from "../lib/case";
import { tickToClock } from "../lib/time";

export function Hud({ tick }: { tick: number }) {
  const { meta } = caseFile;
  return (
    <header className="hud">
      <h1 className="hud__title" data-text="ALIBI">ALIBI</h1>
      <span>CASE {meta.case_id}</span>
      <span className="hud__clock"><i aria-hidden="true" />{tickToClock(Math.floor(tick))}</span>
      <span>
        AUDITED
        <span className="hud__meter" aria-hidden="true"><i style={{ width: `${(meta.audited / meta.claims) * 100}%` }} /></span>
        {meta.audited}/{meta.claims}
      </span>
      <span className="hud__right">SEED {meta.seed}</span>
    </header>
  );
}

interface WindowProps {
  title: string;
  className: string;
  children: ReactNode;
}

/** Night fill inside a cream rule, a black rule and a lavender rule, built from
 *  nested borders: project rules rule 10 allows no shadows. */
export function Window({ title, className, children }: WindowProps) {
  return (
    <section className={`win ${className}`} aria-label={title}>
      <span className="win__rule" aria-hidden="true" />
      <h2 className="win__title">{title}</h2>
      <div className="win__body">{children}</div>
    </section>
  );
}
