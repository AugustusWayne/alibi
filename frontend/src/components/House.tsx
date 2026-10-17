/** The house at one minute (brief 5.3).
 *
 *  The public floor plan, hand-placed on a 3x4 grid so every corridor runs
 *  along a gutter; the twelfth cell is the void. Each suspect stands where
 *  their own account places them at the playhead. A contradicted claim stands
 *  as a ghost, joined by a red string to the place its own conflicting memory
 *  names. A suspect with no account for the minute stands in the void.
 */
import type { Claim, Placement, Walk } from "../lib/case";
import { HELD, caseFile, lookOf, nameOf, placementsAt, remarkOf, unaccountedAt } from "../lib/case";
import { tickToClock } from "../lib/time";
import { Arrow, Cursor, Sprite } from "./Sprite";

// The world generator's eleven rooms, placed by hand (brief 10: hand-place the
// rooms). A floor plan with a room missing from this table is a broken
// assumption, not something to draw around, so it raises.
const CELL: Record<string, [number, number]> = {
  library: [0, 0], scullery: [1, 0], conservatory: [2, 0],
  gallery: [0, 1], cellar: [1, 1], ballroom: [2, 1],
  hall: [0, 2], billiard: [1, 2], study: [2, 2],
  kitchen: [0, 3], terrace: [1, 3],
};
const VOID: [number, number] = [2, 3];
const RW = 196, RH = 92, GX = 44, GY = 24, OX = 40, OY = 44;

interface Box { x: number; y: number; w: number; h: number }

function box(place: string): Box {
  const cell = CELL[place];
  if (!cell) throw new Error(`room ${place} has no cell on the house map; add it to CELL`);
  return { x: OX + cell[0] * (RW + GX), y: OY + cell[1] * (RH + GY), w: RW, h: RH };
}
const voidBox: Box = { x: OX + VOID[0] * (RW + GX), y: OY + VOID[1] * (RH + GY), w: RW, h: RH };

/** A corridor as a path through the gutters, with the two room mouths it joins. */
function corridorPath(a: string, b: string): { d: string; mid: [number, number]; from: [number, number]; to: [number, number] } {
  const A = box(a), B = box(b);
  const [ca, ra] = CELL[a], [cb, rb] = CELL[b];
  let pts: [number, number][];
  if (ra === rb && Math.abs(ca - cb) === 1) {
    const [L, R] = ca < cb ? [A, B] : [B, A];
    pts = [[L.x + RW, L.y + RH / 2], [R.x, R.y + RH / 2]];
  } else if (ca === cb && Math.abs(ra - rb) === 1) {
    const [T, D] = ra < rb ? [A, B] : [B, A];
    pts = [[T.x + RW / 2, T.y + RH], [T.x + RW / 2, D.y]];
  } else {
    const [T, D] = A.y <= B.y ? [A, B] : [B, A];
    const gy = T.y + RH + GY / 2;
    // Snapped to the 4px grid: a route is drawn over these points, and pixel
    // art on a fractional coordinate is a blurred line (brief 3 and 7).
    const snap = (n: number) => Math.round(n / 4) * 4;
    const tx = T.x + snap(RW * 0.78);
    const below = D.y > T.y;
    const dx = D.x + snap(RW * (below ? 0.78 : 0.22));
    pts = [[tx, T.y + RH], [tx, gy], [dx, gy], [dx, below ? D.y : D.y + RH]];
  }
  const i = Math.floor((pts.length - 1) / 2);
  // The path above is built from whichever room sits higher or further left, so
  // which end belongs to `a` is decided by distance from `a`'s own centre. A
  // route walks its corridors in order, and its pins mark the two far ends.
  const head = pts[0], tail = pts[pts.length - 1];
  const nearer = Math.hypot(head[0] - (A.x + RW / 2), head[1] - (A.y + RH / 2)) <=
    Math.hypot(tail[0] - (A.x + RW / 2), tail[1] - (A.y + RH / 2));
  return {
    d: pts.map(([x, y], k) => `${k ? "L" : "M"}${x} ${y}`).join(" "),
    mid: [(pts[i][0] + pts[i + 1][0]) / 2, (pts[i][1] + pts[i + 1][1]) / 2],
    from: nearer ? head : tail,
    to: nearer ? tail : head,
  };
}

/** Where the straight line from a box's centre towards a point leaves the box. */
function exitPoint(b: Box, toward: [number, number]): [number, number] {
  const cx = b.x + b.w / 2, cy = b.y + b.h / 2;
  const dx = toward[0] - cx, dy = toward[1] - cy;
  const t = Math.min(dx ? (b.w / 2) / Math.abs(dx) : Infinity, dy ? (b.h / 2) / Math.abs(dy) : Infinity);
  return [cx + dx * t, cy + dy * t];
}

interface Props {
  tick: number;
  selected: string | null;
  /** The impossible walk the selected claim is in, if it is in one (brief 5.9). */
  walk: Walk | null;
  onSelect: (claimId: string) => void;
}

/** One term of the travel subtraction: the minutes, and a bracket four pixels
 *  to the minute so the three terms are comparable by length. A term of zero
 *  collapses to its two end caps, which is what nothing available looks like. */
function Term({ label, minutes, short = false }: { label: string; minutes: number; short?: boolean }) {
  return (
    <span className={`term${short ? " term--short" : ""}`}>
      {label} {minutes} MIN
      <i className="term__bar" style={{ width: minutes * 4 }} aria-hidden="true" />
    </span>
  );
}

/** The impossible walk, over the map: the two claims it holds between, and the
 *  subtraction. The route itself is drawn corridor by corridor on the plan. */
function WalkBand({ walk, selected, onSelect }: { walk: Walk; selected: string | null; onSelect: (id: string) => void }) {
  const who = nameOf(walk.subject);
  const leg = (c: Claim, text: string, when: string) => (
    <button
      type="button"
      className={`walk__leg${selected === c.id ? " walk__leg--selected" : ""}`}
      onClick={() => onSelect(c.id)}
      aria-pressed={selected === c.id}
      aria-label={`${nameOf(c.speaker)} places ${who} in the ${c.place} ${when}; select that claim`}
    >
      {text}
    </button>
  );
  return (
    <div className="walk">
      <div className="walk__top">
        <span className="walk__tag">IMPOSSIBLE WALK</span>
        {leg(walk.from, `${who} IN ${walk.from.place.toUpperCase()} UNTIL ${tickToClock(walk.from.t1)}`, `until ${tickToClock(walk.from.t1)}`)}
        <Arrow />
        {leg(walk.to, `${walk.to.place.toUpperCase()} FROM ${tickToClock(walk.to.t0)}`, `from ${tickToClock(walk.to.t0)}`)}
        {walk.more > 0 && <span className="walk__more">AND {walk.more} MORE PAIR{walk.more > 1 ? "S" : ""}</span>}
      </div>
      <div className="walk__sum">
        <Term label="SHORTEST WALK" minutes={walk.needed} />
        <b className="walk__op" aria-hidden="true">-</b>
        <Term label="AVAILABLE" minutes={walk.available} />
        <b className="walk__op" aria-hidden="true">=</b>
        <Term label="SHORT BY" minutes={walk.shortBy} short />
      </div>
    </div>
  );
}

function Occupant({ p, scale, selected, onSelect }: { p: Placement; scale: number; selected: boolean; onSelect: (id: string) => void }) {
  const c = p.claim;
  return (
    <button
      type="button"
      className={`who who--${p.stance}${selected ? " who--selected" : ""}`}
      onClick={() => onSelect(c.id)}
      aria-pressed={selected}
      aria-label={`${nameOf(p.suspect)} says ${c.place}, ${tickToClock(c.t0)} to ${tickToClock(c.t1)}, ${c.verdict}`}
    >
      {selected && <Cursor />}
      <Sprite look={lookOf(p.suspect)} mode={p.stance} scale={scale} />
      <span className="who__name">{nameOf(p.suspect)}{p.stance === "ghost" ? "?" : ""}</span>
      {p.stance === "ghost" && <b className="who__alert" aria-hidden="true">!</b>}
    </button>
  );
}

export function House({ tick, selected, walk, onSelect }: Props) {
  const placed = placementsAt(tick);
  const lost = unaccountedAt(tick);
  const { incident } = caseFile;
  const inIncident = incident.t0 <= tick && tick < incident.t1;

  const strings = placed
    .filter((p) => p.stance === "ghost" && p.memoryAt && p.memoryAt !== p.place)
    .map((p) => {
      const A = box(p.place), B = box(p.memoryAt!);
      const a = exitPoint(A, [B.x + B.w / 2, B.y + B.h / 2]);
      const b = exitPoint(B, [A.x + A.w / 2, A.y + A.h / 2]);
      return { key: p.claim.id, a, b };
    });

  return (
    <>
      <svg className="house__corridors" width={740} height={492} shapeRendering="crispEdges" aria-hidden="true">
        {caseFile.floor_plan.corridors.map(({ a, b, minutes }) => {
          const { d, mid } = corridorPath(a, b);
          return (
            <g key={`${a}-${b}`}>
              <path d={d} className="corridor" />
              <g transform={`translate(${mid[0] - 9} ${mid[1] - 8})`} className="corridor__w">
                <rect width={18} height={16} />
                <text x={9} y={12}>{minutes}</text>
              </g>
            </g>
          );
        })}
      </svg>

      {walk && <WalkBand walk={walk} selected={selected} onSelect={onSelect} />}

      {Object.keys(CELL).map((place) => {
        const b = box(place);
        const here = placed.filter((p) => p.place === place);
        const scale = here.length >= 3 ? 2 : 3;
        const talker = here.length <= 2 ? here.map((p) => remarkOf(p.suspect, tick)).find((r) => r !== null) : null;
        const isIncident = place === incident.place;
        return (
          <div
            key={place}
            className={`room room--${place}${isIncident ? " room--incident" : ""}${isIncident && inIncident ? " room--now" : ""}`}
            style={{ left: b.x, top: b.y, width: b.w, height: b.h }}
          >
            <span className="room__name">{place.toUpperCase()}</span>
            {isIncident && (
              <span className="room__flag">INCIDENT {tickToClock(incident.t0)}-{tickToClock(incident.t1)}</span>
            )}
            <div className="room__occupants">
              {here.map((p) => (
                <Occupant key={p.claim.id} p={p} scale={scale} selected={selected === p.claim.id} onSelect={onSelect} />
              ))}
            </div>
            {talker && (
              <button
                type="button"
                className={`bubble bubble--${talker.verdict.toLowerCase()}${selected === talker.id ? " bubble--selected" : ""}`}
                onClick={() => onSelect(talker.id)}
                aria-pressed={selected === talker.id}
                aria-label={`${nameOf(talker.speaker)} says ${nameOf(talker.subject)} was in the ${talker.place}, ${HELD[talker.verdict]}`}
              >
                "{nameOf(talker.subject)} IN THE {talker.place.toUpperCase()}"
                <i>{HELD[talker.verdict]}</i>
              </button>
            )}
          </div>
        );
      })}

      <div className="void" style={{ left: voidBox.x, top: voidBox.y, width: voidBox.w, height: voidBox.h }}>
        <div className="void__who">
          {lost.slice(0, 6).map((id) => (
            <span key={id} className="who who--unknown">
              <Sprite look={lookOf(id)} mode="unknown" scale={lost.length > 2 ? 2 : 3} />
              <span className="who__name">{nameOf(id)}</span>
            </span>
          ))}
          {lost.length > 6 && <span className="void__more">+{lost.length - 6}</span>}
        </div>
        <p className="void__text">
          {lost.length ? <>NO ACCOUNT<br />AT {tickToClock(Math.floor(tick))}</> : <>NOBODY HERE<br />AT {tickToClock(Math.floor(tick))}</>}
        </p>
      </div>

      {/* Brief 5.9: the walk the floor plan allows, corridor by corridor,
          drawn over the dashed corridors it uses. Never a straight line. */}
      {walk && (
        <svg className="house__route" width={740} height={492} shapeRendering="crispEdges" aria-hidden="true">
          {walk.legs.map((l, i) => {
            const { d, mid, from, to } = corridorPath(l.a, l.b);
            return (
              <g key={`${l.a}-${l.b}`}>
                <path d={d} className="route" />
                <g transform={`translate(${mid[0] - 9} ${mid[1] - 8})`} className="route__w">
                  <rect width={18} height={16} />
                  <text x={9} y={12}>{l.minutes}</text>
                </g>
                {i === 0 && <rect x={from[0] - 5} y={from[1] - 5} width={10} height={10} className="route__pin" />}
                {i === walk.legs.length - 1 && (
                  <rect x={to[0] - 5} y={to[1] - 5} width={10} height={10} className="route__pin" />
                )}
              </g>
            );
          })}
        </svg>
      )}

      <svg className="house__strings" width={740} height={492} shapeRendering="crispEdges" aria-hidden="true">
        {strings.map(({ key, a, b }) => (
          <g key={key}>
            <line x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} className="string" />
            <rect x={a[0] - 4} y={a[1] - 4} width={8} height={8} className="string__pin" />
            <rect x={b[0] - 4} y={b[1] - 4} width={8} height={8} className="string__pin" />
          </g>
        ))}
      </svg>
    </>
  );
}
