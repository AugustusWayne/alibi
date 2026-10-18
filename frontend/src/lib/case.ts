/** The fixture, and the readings the board takes from it.
 *
 *  `frontend/fixtures/case-7777.json` is a dump of a real seed-7777 run
 *  (`scripts/dump_case.py`), so every verdict, gap, shadow and trail here was
 *  computed by the audit engine and the referee. Nothing in this module decides
 *  anything about a claim; it only selects and arranges what was proved.
 */
import fixture from "../../fixtures/case-7777.json";
import { tickToClock } from "./time";

export const VERDICTS = [
  "SUPPORTED",
  "HEARSAY",
  "INDETERMINATE",
  "CONTRADICTED",
  "UNSUPPORTED",
] as const;

export type Verdict = (typeof VERDICTS)[number];

export interface Claim {
  id: string;
  speaker: string;
  subject: string;
  place: string;
  t0: number;
  t1: number;
  turn: number;
  modality: string;
  verdict: Verdict;
  coverage: number;
  uncovered: number;
  relayed_from: string | null;
  covered: [number, number][];
  gaps: [number, number][];
  support: string[];
  conflict: string[];
}

export interface Suspect {
  id: string;
  name: string;
}

/** One record out of the speaker's own memory, as the audit matched it against
 *  the claim: a support shadow carries the slice of the claim it covers, a
 *  conflict shadow carries only its own window. `src` is how that memory was
 *  acquired, so `hearsay` means the record itself is secondhand. */
export interface Shadow {
  claim_id: string;
  id: string;
  fact_id: string;
  src: string;
  place: string;
  agent: string;
  t0: number;
  t1: number;
  /** Support shadows only: the part of the claim's window this record covers. */
  covers_t0?: number;
  covers_t1?: number;
}

export interface Hop {
  depth: number;
  agent: string;
  fact_id: string;
  src: string | null;
  transmission_id: string | null;
  tick: number | null;
  verdict: string | null;
  learned_at: number | null;
}

export interface Chain {
  claim_id: string;
  speaker: string;
  terminal: string;
  origin_agent: string | null;
  is_origin: boolean;
  is_ungrounded: boolean;
  carriers: string[];
  detail: string;
  hops: Hop[];
}

/** A CONTRADICTS edge the cross-claim checks wrote. `gap` and `needed` are
 *  filled for `impossible_travel` only: the minutes between the two claims,
 *  and the minutes the floor plan needs for the walk. */
export interface Contradiction {
  pair_id: string;
  kind: string;
  a: string;
  b: string;
  speaker_a: string;
  speaker_b: string;
  subject: string;
  gap: number | null;
  needed: number | null;
}

export interface CaseFixture {
  meta: {
    seed: number;
    case_id: string;
    hour_labels: { tick: number; label: string }[];
    claims: number;
    audited: number;
    interviews: number;
  };
  suspects: Suspect[];
  incident: { id: string; place: string; t0: number; t1: number };
  claims: Claim[];
  evidence: { support: Shadow[]; conflict: Shadow[] };
  contradictions: Contradiction[];
  chains: Chain[];
  tally: Partial<Record<Verdict, number>>;
  floor_plan: {
    places: { id: string; name: string }[];
    corridors: { a: string; b: string; minutes: number }[];
    /** The all-pairs travel matrix, keyed `from|to`, in minutes. */
    travel: Record<string, number>;
    /** The walk behind each cell of that matrix, room by room. */
    routes: Record<string, string[]>;
  };
  audit_summary: { uncovered_minutes: number; claims_with_gaps: number };
}

export const caseFile = fixture as unknown as CaseFixture;

const claimById = new Map(caseFile.claims.map((c) => [c.id, c]));
const chainByClaim = new Map(caseFile.chains.map((c) => [c.claim_id, c]));
const conflictByClaim = new Map<string, Shadow[]>();
for (const s of caseFile.evidence.conflict) {
  conflictByClaim.set(s.claim_id, [...(conflictByClaim.get(s.claim_id) ?? []), s]);
}
const supportByClaim = new Map<string, Shadow[]>();
for (const s of caseFile.evidence.support) {
  supportByClaim.set(s.claim_id, [...(supportByClaim.get(s.claim_id) ?? []), s]);
}

export const claimOf = (id: string | null) => (id ? (claimById.get(id) ?? null) : null);
export const chainOf = (claimId: string) => chainByClaim.get(claimId) ?? null;
export const conflictsOf = (claimId: string) => conflictByClaim.get(claimId) ?? [];
export const supportOf = (claimId: string) => supportByClaim.get(claimId) ?? [];

/** A suspect's name as the board prints it. The pixel face is all caps. */
export function nameOf(id: string): string {
  const s = caseFile.suspects.find((x) => x.id === id);
  return (s ? s.name : id).toUpperCase();
}

/** Which of the seven looks a suspect wears: their position in the case file. */
export const lookOf = (id: string) => Math.max(0, caseFile.suspects.findIndex((s) => s.id === id));

/** A suspect's account of their own evening: claims whose subject is the speaker. */
export const ownClaims = (id: string) =>
  caseFile.claims.filter((c) => c.speaker === id && c.subject === id);

/** What everyone else said about a person. */
export const claimsAbout = (subject: string) =>
  caseFile.claims.filter((c) => c.subject === subject && c.speaker !== subject);

const covers = (c: Claim, tick: number) => c.t0 <= tick && tick < c.t1;
const overlaps = (a: Claim, b: Claim) => a.t0 < b.t1 && b.t0 < a.t1;

/**
 * Pack claims into lanes so no two bars occupy the same minutes. Greedy
 * first-fit over claims sorted by start, so the packing is stable between runs.
 */
export function packLanes(claims: Claim[]): Claim[][] {
  const ordered = [...claims].sort((a, b) => a.t0 - b.t0 || a.t1 - b.t1 || a.turn - b.turn);
  const lanes: Claim[][] = [];
  const ends: number[] = [];
  for (const claim of ordered) {
    const i = ends.findIndex((end) => end <= claim.t0);
    if (i === -1) {
      lanes.push([claim]);
      ends.push(claim.t1);
    } else {
      lanes[i].push(claim);
      ends[i] = claim.t1;
    }
  }
  return lanes;
}

// -- the house at one minute ------------------------------------------------

export type Stance = "solid" | "ghost" | "hollow";

/** Where one suspect's own account puts them at one minute, and how firmly. */
export interface Placement {
  suspect: string;
  claim: Claim;
  place: string;
  stance: Stance;
  /** For a contradicted claim: the place the conflicting memory names. */
  memoryAt: string | null;
}

/**
 * Every placement at a minute (brief 4 and 5.3). A contradicted claim stands
 * as a ghost, linked to the place its own conflicting memory names; a claim
 * with nothing behind it stands hollow; anything with support stands solid.
 */
export function placementsAt(tick: number): Placement[] {
  return caseFile.suspects.flatMap((s) =>
    ownClaims(s.id)
      .filter((c) => covers(c, tick))
      .map((c) => ({
        suspect: s.id,
        claim: c,
        place: c.place,
        stance:
          c.verdict === "CONTRADICTED" ? "ghost" : c.verdict === "UNSUPPORTED" ? "hollow" : "solid",
        memoryAt: c.verdict === "CONTRADICTED" ? (conflictsOf(c.id)[0]?.place ?? null) : null,
      })),
  );
}

/** Suspects whose own account has no entry for this minute: they stand in the void. */
export function unaccountedAt(tick: number): string[] {
  return caseFile.suspects
    .map((s) => s.id)
    .filter((id) => !ownClaims(id).some((c) => covers(c, tick)));
}

/** How many suspects have no account at each minute. Drives the polygraph needle. */
export const unaccountedByTick: number[] = Array.from({ length: 300 }, (_, t) => unaccountedAt(t).length);

const BUBBLE_ORDER: Verdict[] = ["CONTRADICTED", "HEARSAY", "INDETERMINATE", "UNSUPPORTED", "SUPPORTED"];

/** The claim about someone else a placed speaker is making at this minute, if any. */
export function remarkOf(speaker: string, tick: number): Claim | null {
  const said = caseFile.claims.filter((c) => c.speaker === speaker && c.subject !== speaker && covers(c, tick));
  said.sort((a, b) => BUBBLE_ORDER.indexOf(a.verdict) - BUBBLE_ORDER.indexOf(b.verdict) || a.t0 - b.t0);
  return said[0] ?? null;
}

/** How a claim is held, in the tag a speech bubble carries. */
export const HELD: Record<Verdict, string> = {
  SUPPORTED: "SEEN",
  INDETERMINATE: "PARTLY SEEN",
  HEARSAY: "HEARD, NOT SEEN",
  CONTRADICTED: "OWN MEMORY DISAGREES",
  UNSUPPORTED: "NOTHING BEHIND IT",
};

// -- the case log -----------------------------------------------------------

/** What the speaker's own memory holds about the claim, in one line. */
export function memoryLine(c: Claim): string {
  const mins = c.t1 - c.t0;
  switch (c.verdict) {
    case "CONTRADICTED": {
      const s = conflictsOf(c.id)[0];
      return s ? `OWN MEMORY: ${s.place.toUpperCase()}, ${s.src === "witnessed" ? "SEEN" : "HEARD"}` : "OWN MEMORY DISAGREES";
    }
    case "SUPPORTED":
      return `OWN MEMORY: SEEN, ALL ${mins} MIN`;
    case "INDETERMINATE":
      return `OWN MEMORY COVERS ${mins - c.uncovered} OF ${mins} MIN`;
    case "HEARSAY": {
      const from = chainOf(c.id)?.hops[1]?.agent;
      return from ? `OWN MEMORY: HEARD FROM ${nameOf(from)}` : "OWN MEMORY: HEARD IT";
    }
    case "UNSUPPORTED":
      return "NOTHING IN OWN MEMORY BEARS ON IT";
  }
}

/** One record out of the speaker's own memory as the case log prints it: the
 *  fill that carries how it stands against the claim, what the record says,
 *  and how much of the claim it accounts for. A record acquired secondhand
 *  says so in both the fill and the words. */
export interface MemoryRow {
  shadow: Shadow;
  /** The record's own id in that memory, printed so two records that say the
   *  same thing about the same minutes are still two records. */
  fact: string;
  /** Which of `ClaimBar`'s five fills this record is drawn with. The fills
   *  live there and nowhere else, so this names one rather than drawing it. */
  fill: Verdict;
  says: string;
  bears: string;
}

function memoryRow(c: Claim, s: Shadow, kind: "support" | "conflict"): MemoryRow {
  const when = `${tickToClock(s.t0)}-${tickToClock(s.t1)}`;
  // The record's own room, printed only where it is not the room the claim
  // names: on a conflict that difference is the whole finding.
  const where = s.place === c.place ? "" : ` ${s.place.toUpperCase()}`;
  const whose = s.agent === c.speaker ? "" : `${nameOf(s.agent)}: `;
  const held = s.src === "hearsay" ? "HEARD, NOT SEEN" : "SAW";
  const says = `${whose}${held}${where} ${when}`;
  const fact = s.fact_id.toUpperCase();
  if (kind === "conflict") {
    // A conflict shadow is a witnessed memory of another room over minutes the
    // claim also covers, so what it bears on the claim is that overlap.
    const overlap = Math.min(s.t1, c.t1) - Math.max(s.t0, c.t0);
    return {
      shadow: s,
      fact,
      fill: "CONTRADICTED",
      says,
      bears: `${overlap} MIN IN ANOTHER ROOM`,
    };
  }
  const claimed = c.t1 - c.t0;
  const covers = (s.covers_t1 ?? s.t1) - (s.covers_t0 ?? s.t0);
  const bears = covers >= claimed ? `COVERS ALL ${claimed} MIN` : `COVERS ${covers} OF ${claimed} MIN`;
  return {
    shadow: s,
    fact,
    fill: s.src === "hearsay" ? "HEARSAY" : "SUPPORTED",
    says,
    bears,
  };
}

/**
 * Every record of the speaker's own memory the audit matched against the
 * claim, the conflicting ones first (brief 5.4, 6.2). These are the shadows
 * the engine materialized: nothing here is inferred.
 */
export function memoryRows(c: Claim): MemoryRow[] {
  return [
    ...conflictsOf(c.id).map((s) => memoryRow(c, s, "conflict")),
    ...supportOf(c.id)
      .slice()
      .sort((a, b) => (a.covers_t0 ?? a.t0) - (b.covers_t0 ?? b.t0))
      .map((s) => memoryRow(c, s, "support")),
  ];
}

export type TrailEnd = "origin-grounded" | "origin-ungrounded" | "unresolved";

/** One hearsay claim's trail, as brief 5.5 draws it. An unresolved chain never
 *  names an origin: the end chip shows who was cited, dashed, or `???`. */
export interface Trail {
  claim: Claim;
  carrier: string;
  end: string;
  endKind: TrailEnd;
  outcome: string;
}

export function trailOf(c: Claim): Trail | null {
  const ch = chainOf(c.id);
  if (!ch) return null;
  const cited = ch.hops[1]?.agent ?? null;
  const origin = ch.origin_agent;
  const base = { claim: c, carrier: c.speaker };
  switch (ch.terminal) {
    case "ORIGIN_WITNESSED":
      return { ...base, end: nameOf(origin!), endKind: "origin-grounded", outcome: `TRAIL ENDS AT ${nameOf(origin!)}, WHO SAW IT` };
    case "ORIGIN_UNSUPPORTED":
      return { ...base, end: nameOf(origin!), endKind: "origin-ungrounded", outcome: `TRAIL ENDS AT ${nameOf(origin!)}, NOTHING BEHIND IT` };
    case "ORIGIN_CONTRADICTED":
      return { ...base, end: nameOf(origin!), endKind: "origin-ungrounded", outcome: `TRAIL ENDS AT ${nameOf(origin!)}` };
    case "CHAIN_BROKEN":
      return { ...base, end: "???", endKind: "unresolved", outcome: "NO SUCH RECORD" };
    case "CHAIN_TEMPORAL_VIOLATION": {
      const told = ch.hops[0]?.tick;
      const learned = ch.hops[1]?.learned_at;
      const early = told != null && learned != null ? learned - told : null;
      return { ...base, end: cited ? nameOf(cited) : "???", endKind: "unresolved", outcome: early ? `TOLD ${early} MIN EARLY` : "TOLD BEFORE IT WAS KNOWN" };
    }
    case "CHAIN_CYCLE":
      return { ...base, end: cited ? nameOf(cited) : "???", endKind: "unresolved", outcome: "GOES IN A CIRCLE" };
    case "CHAIN_TOO_DEEP":
      return { ...base, end: "...", endKind: "unresolved", outcome: "TOO LONG TO FOLLOW" };
    default:
      throw new Error(`unknown chain terminal ${ch.terminal} on claim ${c.id}`);
  }
}

/** What other suspects said about the same person in the same window. */
export function othersOn(c: Claim) {
  const near = claimsAbout(c.subject).filter((o) => o.id !== c.id && o.speaker !== c.speaker && overlaps(o, c));
  const seen = near.filter((o) => o.verdict === "SUPPORTED");
  const heard = near.filter((o) => o.verdict === "HEARSAY");
  const places = [...new Set(heard.map((o) => o.place))];
  return {
    seen,
    heard: places.map((place) => ({ place, trails: heard.filter((o) => o.place === place).map(trailOf).filter((t): t is Trail => t !== null) })),
    rest: near.filter((o) => o.verdict !== "SUPPORTED" && o.verdict !== "HEARSAY"),
  };
}

// -- the impossible walk (brief 5.9) ----------------------------------------

/** One corridor of a route, with its walk in minutes. */
export interface Leg {
  a: string;
  b: string;
  minutes: number;
}

/**
 * An `impossible_travel` pair as the board draws it: the two claims, the walk
 * the floor plan actually allows between their rooms, and the subtraction.
 * Every number comes from the CONTRADICTS edge the check wrote or from the
 * dumped route; none of it is computed here beyond the subtraction itself.
 */
export interface Walk {
  pair_id: string;
  subject: string;
  /** The earlier claim, then the later one, as the check matched them. */
  from: Claim;
  to: Claim;
  /** The rooms the shortest walk passes through, in order. */
  route: string[];
  legs: Leg[];
  /** Minutes between the end of the first claim and the start of the second. */
  available: number;
  /** Minutes the shortest walk between the two rooms costs. */
  needed: number;
  shortBy: number;
  /** Further impossible-travel pairs this claim is in, not drawn. */
  more: number;
}

/** A corridor's walk. A route step that is not a corridor means the dumped
 *  route and the dumped floor plan disagree, which must not be drawn over. */
function corridorMinutes(a: string, b: string): number {
  const c = caseFile.floor_plan.corridors.find(
    (x) => (x.a === a && x.b === b) || (x.a === b && x.b === a),
  );
  if (!c) throw new Error(`the route steps ${a} to ${b}, which is no corridor on the floor plan`);
  return c.minutes;
}

/**
 * The impossible walk a claim is in, if any. Where a claim is in several, the
 * first by pair id is drawn and the rest are counted, so the house never shows
 * two routes at once.
 */
export function walkOf(claim: Claim): Walk | null {
  const pairs = caseFile.contradictions
    .filter((x) => x.kind === "impossible_travel" && (x.a === claim.id || x.b === claim.id))
    .sort((p, q) => p.pair_id.localeCompare(q.pair_id));
  const pair = pairs[0];
  if (!pair) return null;

  const from = claimOf(pair.a);
  const to = claimOf(pair.b);
  if (!from || !to) throw new Error(`contradiction ${pair.pair_id} names a claim the case file does not hold`);
  if (pair.gap === null || pair.needed === null) {
    throw new Error(`impossible-travel pair ${pair.pair_id} carries no gap and needed; the case graph wrote an incomplete edge`);
  }

  const route = caseFile.floor_plan.routes[`${from.place}|${to.place}`];
  if (!route) {
    throw new Error(`no route from ${from.place} to ${to.place} in the fixture; re-run scripts/dump_case.py`);
  }
  const legs = route.slice(1).map((b, i) => ({ a: route[i], b, minutes: corridorMinutes(route[i], b) }));
  const walked = legs.reduce((n, l) => n + l.minutes, 0);
  if (walked !== pair.needed) {
    throw new Error(`the drawn route costs ${walked} min but the travel check read ${pair.needed} min for ${from.place} to ${to.place}`);
  }

  return {
    pair_id: pair.pair_id,
    subject: pair.subject,
    from,
    to,
    route,
    legs,
    available: pair.gap,
    needed: pair.needed,
    shortBy: pair.needed - pair.gap,
    more: pairs.length - 1,
  };
}
