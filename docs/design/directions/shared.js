// Shared by the four direction mockups. Every number they draw comes from the
// real seed-7777 fixture, so the directions differ in style only, not in data.

export const PEN = 112; // 19:52, inside the incident window [102, 122)
export const SELECTED = "p4-c7"; // dara: "I was in the hall", contradicted by dara's own memory

export async function load() {
  const res = await fetch("../../../frontend/fixtures/case-7777.json");
  if (!res.ok) throw new Error(`fixture not found (${res.status}); serve the repo root, not docs/`);
  const d = await res.json();
  const names = Object.fromEntries(d.suspects.map((s) => [s.id, s.name.toLowerCase()]));
  const own = (id) => d.claims.filter((c) => c.speaker === id && c.subject === id);
  const aboutDara = d.claims.filter((c) => c.subject === "p4" && c.speaker !== "p4");
  const claim = (id) => d.claims.find((c) => c.id === id);
  const chain = (id) => d.chains.find((c) => c.claim_id === id);
  return { ...d, names, own, aboutDara, claim, chain };
}

export const pct = (t) => (t / 300) * 100;
export const clock = (t) =>
  `${String(18 + Math.floor(t / 60)).padStart(2, "0")}:${String(t % 60).padStart(2, "0")}`;

/** Greedy first-fit lane packing, the same rule the real board uses. */
export function lanes(claims) {
  const out = [];
  const ends = [];
  for (const c of [...claims].sort((a, b) => a.t0 - b.t0 || a.t1 - b.t1)) {
    const i = ends.findIndex((e) => e <= c.t0);
    if (i === -1) {
      out.push([c]);
      ends.push(c.t1);
    } else {
      out[i].push(c);
      ends[i] = c.t1;
    }
  }
  return out;
}

/** The covered part of a claim: its window minus the proved gaps. */
export function covered(c) {
  const spans = [];
  let cur = c.t0;
  for (const [g0, g1] of [...c.gaps].sort((a, b) => a[0] - b[0])) {
    if (g0 > cur) spans.push([cur, g0]);
    cur = Math.max(cur, g1);
  }
  if (cur < c.t1) spans.push([cur, c.t1]);
  return spans;
}

/** Where each suspect says they were at a tick, from their own account. */
export function alibisAt(d, tick) {
  const out = {};
  for (const s of d.suspects) {
    out[s.id] = d.own(s.id).filter((c) => c.t0 <= tick && tick < c.t1);
  }
  return out;
}

export const ORDER = ["SUPPORTED", "HEARSAY", "INDETERMINATE", "CONTRADICTED", "UNSUPPORTED"];
