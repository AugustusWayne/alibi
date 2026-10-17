/** The case log (brief 5.4, 5.5, 5.6, and the inspection rows of 6.2).
 *
 *  The selected claim: who said it, what their own memory holds, and the
 *  verdict drawn with its own fill. Then the records of that memory the audit
 *  matched against the claim, one row each. Then what other suspects said
 *  about the same person in the same window: who saw it, and who heard it,
 *  each hearsay with its trail. The inventory under it teaches the fills.
 */
import type { Claim, MemoryRow, Trail } from "../lib/case";
import { VERDICTS, caseFile, lookOf, memoryLine, memoryRows, nameOf, othersOn, trailOf } from "../lib/case";
import { tickToClock } from "../lib/time";
import { Fill } from "./ClaimBar";
import { Arrow, Lens, Sprite } from "./Sprite";

/** Rows the window holds under the portrait before the inventory: four at the
 *  measured row height, and the evidence rows have first call on them. */
const MAX_ROWS = 5;
const MAX_EVIDENCE = 3;

/** One record of the speaker's own memory. A data row, not a control: there is
 *  nothing behind a record to select. */
function EvidenceRow({ r }: { r: MemoryRow }) {
  return (
    <li className="mem">
      <span className="mem__id">{r.fact}</span>
      <Fill verdict={r.fill} className="mem__fill" />
      <span className="mem__says">{r.says}</span>
      <span className="mem__bears">{r.bears}</span>
    </li>
  );
}

function TrailRow({ t, onSelect }: { t: Trail; onSelect: (id: string) => void }) {
  return (
    <button type="button" className="trail" onClick={() => onSelect(t.claim.id)} aria-label={`${nameOf(t.carrier)}: ${t.outcome}`}>
      <span className="chip chip--heard">{nameOf(t.carrier)}</span>
      <Arrow />
      <span className={`chip chip--${t.endKind}`}>{t.end}</span>
      <span className="trail__what">{t.outcome}</span>
    </button>
  );
}

function Inventory() {
  return (
    <>
      <div className="log__sub">INVENTORY</div>
      <div className="slots">
        {VERDICTS.map((v) => (
          <div className="slot" key={v}>
            <div className="slot__well">
              <Fill verdict={v} className="slot__fill" />
              {v === "INDETERMINATE" && <i className="slot__bracket" />}
            </div>
            <span className="slot__n">x{caseFile.tally[v] ?? 0}</span>
            <span className="slot__l">{v.slice(0, 6)}</span>
          </div>
        ))}
      </div>
    </>
  );
}

function Says({ c }: { c: Claim }) {
  const when = `${tickToClock(c.t0)}-${tickToClock(c.t1)}`;
  return c.subject === c.speaker ? (
    <>SAYS: <b>{c.place.toUpperCase()}</b> {when}</>
  ) : (
    <>SAYS: <b>{nameOf(c.subject)}</b> IN <b>{c.place.toUpperCase()}</b> {when}</>
  );
}

interface Props {
  claim: Claim | null;
  onSelect: (claimId: string) => void;
}

export function CaseLog({ claim, onSelect }: Props) {
  if (!claim) {
    return (
      <div className="log">
        <div className="log__idle">
          <Lens scale={8} />
          <div>
            <p className="log__direct">SELECT A CLAIM ON THE TIMELINE, OR A SUSPECT IN THE HOUSE.</p>
            <p className="log__line">{caseFile.meta.audited} OF {caseFile.meta.claims} CLAIMS AUDITED</p>
            <p className="log__line">{caseFile.audit_summary.uncovered_minutes} MINUTES UNACCOUNTED</p>
          </div>
        </div>
        <Inventory />
      </div>
    );
  }

  const others = othersOn(claim);
  const own = claim.verdict === "HEARSAY" ? trailOf(claim) : null;
  const subject = nameOf(claim.subject);
  const records = memoryRows(claim);
  const shownRecords = records.slice(0, MAX_EVIDENCE);
  // The window holds `MAX_ROWS` of these, and a sub-heading takes one of them,
  // so a section is charged for its own heading. What the claim's own memory
  // holds is charged first: it is the audit's own working, and the rows below
  // it are context. Whatever the budget cannot hold is counted, never dropped.
  let budget = MAX_ROWS - (shownRecords.length ? 1 + shownRecords.length : 0) - (own ? 2 : 0);
  const seen = others.seen.slice(0, Math.max(0, Math.min(2, budget)));
  budget -= seen.length;
  const groups = others.heard.map((g) => {
    const shown = g.trails.slice(0, Math.max(0, budget - 1));
    if (shown.length) budget -= 1 + shown.length;
    return { ...g, shown };
  });
  const hidden =
    others.seen.length - seen.length + others.rest.length +
    groups.reduce((n, g) => n + g.trails.length - g.shown.length, 0);
  const heldRecords = records.length - shownRecords.length;

  return (
    <div className="log">
      <div className="portrait">
        <div className="portrait__frame"><Sprite look={lookOf(claim.speaker)} scale={5} /></div>
        <div className="portrait__text">
          <div className="portrait__name">{nameOf(claim.speaker)}</div>
          <div className="log__line"><Says c={claim} /></div>
          <div className="log__line">{memoryLine(claim)}</div>
          <div className={`badge badge--${claim.verdict.toLowerCase()}`}>
            <Fill verdict={claim.verdict} className="badge__fill" />
            {claim.verdict}
          </div>
        </div>
      </div>

      {shownRecords.length > 0 && (
        <>
          <div className="log__sub">
            WHAT THEIR OWN MEMORY HOLDS{heldRecords > 0 ? `, ${shownRecords.length} OF ${records.length}` : ""}
          </div>
          <ul className="mems">
            {shownRecords.map((r) => (
              <EvidenceRow key={r.shadow.id} r={r} />
            ))}
          </ul>
        </>
      )}

      {own && (
        <>
          <div className="log__sub">THIS CLAIM'S TRAIL</div>
          <TrailRow t={own} onSelect={onSelect} />
        </>
      )}

      {seen.map((o) => (
        <button type="button" key={o.id} className="seen" onClick={() => onSelect(o.id)}>
          <Fill verdict="SUPPORTED" className="seen__fill" />
          {nameOf(o.speaker)} SAW {subject} IN THE {o.place.toUpperCase()}
        </button>
      ))}

      {groups.filter((g) => g.shown.length).map((g) => (
        <div key={g.place}>
          <div className="log__sub">"{subject} WAS IN THE {g.place.toUpperCase()}", HEARD BY {g.trails.length}</div>
          {g.shown.map((t) => <TrailRow key={t.claim.id} t={t} onSelect={onSelect} />)}
        </div>
      ))}

      {!own && seen.length === 0 && others.heard.length === 0 && others.rest.length === 0 && (
        <p className="log__line log__line--dim">NO ONE ELSE SPOKE ABOUT {subject} IN THIS WINDOW.</p>
      )}
      {hidden > 0 && <p className="log__more">+{hidden} MORE ON THE RE: {subject} ROW</p>}

      <Inventory />
    </div>
  );
}
