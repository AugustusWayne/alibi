// Direction 4: the 8-bit mystery. The house at 19:52 as a top-down pixel map
// with every suspect where they say they were, a case log in an RPG window,
// and the recorder as a level strip with fog over the minutes not yet played.
//
// The rule that carries over unchanged: nothing on this screen accuses. A
// contradiction is an "!" and a link between two places, never a verdict on
// a person.
import { mount } from "./device.js";
import { PEN, SELECTED, ORDER, alibisAt, clock, covered, lanes, pct } from "./shared.js";

// -- sprites --------------------------------------------------------------

const BODY = [
  "...HHHH...",
  "..HHHHHH..",
  ".HHHHHHHH.",
  ".HSSSSSSH.",
  ".SSKSSKSS.",
  ".SSSSSSSS.",
  "..SSMMSS..",
  "...SSSS...",
  ".CCCCCCCC.",
  "CCCCDDCCCC",
  "SCCCDDCCCS",
  ".CCCCCCCC.",
  ".LLL..LLL.",
  ".BBB..BBB.",
];

const LOOK = {
  p1: { H: "#ab5236", C: "#29adff", D: "#1d2b53" }, // avery
  p2: { H: "#000000", C: "#00e436", D: "#008751" }, // blake
  p3: { H: "#ffec27", C: "#83769c", D: "#5f574f" }, // cato
  p4: { H: "#000000", C: "#7e2553", D: "#ff77a8" }, // dara
  p5: { H: "#ff77a8", C: "#ffccaa", D: "#ab5236" }, // esme
  p6: { H: "#5f574f", C: "#ffa300", D: "#ab5236" }, // faris
  p7: { H: "#c2c3c7", C: "#008751", D: "#00e436" }, // gale
};
const BASE = { S: "#ffccaa", K: "#000000", M: "#7e2553", L: "#1d2b53", B: "#000000" };

/** A suspect as an SVG sprite. `mode` is "solid", "ghost" (dithered, every
 *  other pixel) or "unknown" (a flat silhouette). */
function sprite(id, scale = 3, mode = "solid") {
  const pal = { ...BASE, ...(LOOK[id] ?? {}) };
  const rects = [];
  const phase = [[], []];
  BODY.forEach((row, y) =>
    [...row].forEach((ch, x) => {
      if (ch === ".") return;
      const fill = mode === "ghost" ? "#fff1e8" : mode === "unknown" ? "#5f574f" : pal[ch];
      const cell = `<rect x="${x}" y="${y}" width="1" height="1" fill="${fill}"/>`;
      if (mode === "ghost") phase[(x + y) % 2].push(cell);
      else rects.push(cell);
    }),
  );
  // A ghost is a dither. It carries both phases, so a live scene can flicker
  // between them; a still one shows only the first.
  const body = mode === "ghost"
    ? `<g class="px-dither px-dither--a">${phase[0].join("")}</g><g class="px-dither px-dither--b">${phase[1].join("")}</g>`
    : rects.join("");
  return `<svg class="px-sprite" width="${10 * scale}" height="${14 * scale}" viewBox="0 0 10 14" shape-rendering="crispEdges" aria-hidden="true">${body}</svg>`;
}

const LENS = ["0111000", "1000100", "1000100", "1000100", "0111100", "0000010", "0000001"];
function lens(scale = 3) {
  const r = [];
  LENS.forEach((row, y) => [...row].forEach((c, x) => c === "1" && r.push(`<rect x="${x}" y="${y}" width="1" height="1"/>`)));
  return `<svg class="px-lens" width="${7 * scale}" height="${7 * scale}" viewBox="0 0 7 7" shape-rendering="crispEdges" aria-hidden="true">${r.join("")}</svg>`;
}

// -- the house ---------------------------------------------------------------

// Hand-placed on a 3x4 grid so every real corridor runs along a gutter. The
// twelfth cell is left empty on purpose: it is where an unaccounted suspect
// stands.
const CELL = {
  library: [0, 0], scullery: [1, 0], conservatory: [2, 0],
  gallery: [0, 1], cellar: [1, 1], ballroom: [2, 1],
  hall: [0, 2], billiard: [1, 2], study: [2, 2],
  kitchen: [0, 3], terrace: [1, 3],
};
const RW = 196, RH = 92, GX = 44, GY = 24, OX = 40, OY = 44;
const room = (id) => {
  const [c, r] = CELL[id];
  return { x: OX + c * (RW + GX), y: OY + r * (RH + GY), w: RW, h: RH };
};

/** A corridor as a path through the gutters, with its walk in minutes. */
function corridor(a, b, minutes) {
  const A = room(a), B = room(b);
  const [ca, ra] = CELL[a], [cb, rb] = CELL[b];
  let pts;
  if (ra === rb && Math.abs(ca - cb) === 1) {
    const [L, R] = ca < cb ? [A, B] : [B, A];
    const y = L.y + RH / 2;
    pts = [[L.x + RW, y], [R.x, y]];
  } else if (ca === cb && Math.abs(ra - rb) === 1) {
    const [T, D] = ra < rb ? [A, B] : [B, A];
    const x = T.x + RW / 2;
    pts = [[x, T.y + RH], [x, D.y]];
  } else {
    // Not neighbours: run along the gutter under the upper room.
    const [T, D] = A.y <= B.y ? [A, B] : [B, A];
    const gy = T.y + RH + GY / 2;
    const tx = T.x + RW * 0.78;
    const dx = D.x + RW * (D.y > T.y ? 0.78 : 0.22);
    pts = [[tx, T.y + RH], [tx, gy], [dx, gy], [dx, D.y > T.y ? D.y : D.y + RH]];
  }
  const d = pts.map(([x, y], i) => `${i ? "L" : "M"}${x} ${y}`).join(" ");
  const mid = pts[Math.floor((pts.length - 1) / 2)];
  const nxt = pts[Math.floor((pts.length - 1) / 2) + 1];
  const mx = (mid[0] + nxt[0]) / 2, my = (mid[1] + nxt[1]) / 2;
  return `<path d="${d}" class="px-corr"/><g class="px-w" transform="translate(${mx - 9} ${my - 8})"><rect width="18" height="16"/><text x="9" y="12">${minutes}</text></g>`;
}

export function render(el, d, opts = {}) {
  const sel = d.claim(SELECTED);
  const at = alibisAt(d, PEN);
  const name = (id) => d.names[id].toUpperCase();

  // Where each sprite stands: the room their own account names at 19:52.
  // Dara's account names the hall; dara's memory has the kitchen.
  const placed = {};
  const stand = (place, html) => (placed[place] ??= []).push(html);
  for (const s of d.suspects) {
    if (s.id === "p4") continue;
    const here = at[s.id][0];
    if (here) stand(here.place, `<div class="px-who">${sprite(s.id)}<span>${name(s.id)}</span></div>`);
  }
  stand("hall", `<div class="px-who px-who--ghost">${sprite("p4", 3, "ghost")}<span>DARA?</span><b class="px-alert">!</b></div>`);
  stand("kitchen", `<div class="px-who">${sprite("p4")}<span>DARA</span></div>`);

  // Who repeats "dara was in the hall", heard rather than seen.
  const heard = new Set(["hall"].flatMap((place) =>
    d.aboutDara.filter((c) => c.place === place && c.t0 <= PEN && PEN < c.t1 && c.verdict === "HEARSAY").map((c) => c.speaker)));

  const rooms = Object.keys(CELL)
    .map((id) => {
      const r = room(id);
      const incident = id === d.incident.place;
      const bubbles = Object.entries(at)
        .filter(([sid, cs]) => heard.has(sid) && cs[0]?.place === id)
        .map(([sid]) => `<div class="px-bubble">"DARA WAS IN THE HALL"<i>HEARD, NOT SEEN</i></div>`)
        .join("");
      return `<div class="px-room px-room--${id}${incident ? " px-room--incident" : ""}" style="left:${r.x}px;top:${r.y}px;width:${r.w}px;height:${r.h}px">
        <span class="px-room-name">${id.toUpperCase()}</span>
        ${incident ? `<span class="px-room-flag">INCIDENT ${clock(d.incident.t0)}-${clock(d.incident.t1)}</span>` : ""}
        <div class="px-occupants">${(placed[id] ?? []).join("")}</div>
        ${bubbles}
      </div>`;
    })
    .join("");

  const voidCell = (() => {
    const x = OX + 2 * (RW + GX), y = OY + 3 * (RH + GY);
    return `<div class="px-void" style="left:${x}px;top:${y}px;width:${RW}px;height:${RH}px">
      <div class="px-who">${sprite("p5", 3, "unknown")}<span>ESME</span><b class="px-q">?</b></div>
      <p>NO ACCOUNT<br>FROM ${clock(PEN)}</p>
    </div>`;
  })();

  const links = (() => {
    const h = room("hall"), k = room("kitchen");
    const x = h.x + 54, y1 = h.y + RH - 6, y2 = k.y + 18;
    return `<path d="M${x} ${y1} L${x} ${y2}" class="px-link"/>`;
  })();

  const corridors = d.floor_plan.corridors.map((c) => corridor(c.a, c.b, c.minutes)).join("");

  // -- the case log ----------------------------------------------------------
  const trails = [
    ["p2", "p4", "TRAIL ENDS AT DARA"],
    ["p1", null, "NO SUCH RECORD"],
    ["p6", "p4", "TOLD 1 MIN EARLY"],
  ]
    .map(([from, to, what]) => `<div class="px-trail"><span class="px-chip px-chip--heard">${name(from)}</span>
      <svg class="px-arrow" viewBox="0 0 12 7" width="24" height="14" shape-rendering="crispEdges" aria-hidden="true"><path d="M3 0h1v1H3zM2 1h1v1H2zM1 2h1v1H1zM0 3h12v1H0zM1 4h1v1H1zM2 5h1v1H2zM3 6h1v1H3z"/></svg>
      <span class="px-chip${to ? " px-chip--origin" : " px-chip--void"}">${to ? name(to) : "???"}</span><span class="px-trail-what">${what}</span></div>`)
    .join("");

  const slots = ORDER.map((v) => {
    const n = d.tally[v] ?? 0;
    return `<div class="px-slot"><div class="px-slot-well"><span class="px-f px-${v.toLowerCase()}">${v === "CONTRADICTED" ? "<i class='px-strike'></i>" : ""}${v === "INDETERMINATE" ? "<i class='px-cov'></i>" : ""}</span>${v === "INDETERMINATE" ? "<i class='px-slot-bracket'></i>" : ""}</div><span class="px-slot-n">x${n}</span><span class="px-slot-l">${v.slice(0, 6)}</span></div>`;
  }).join("");

  // -- the level strip --------------------------------------------------------
  const ids = d.suspects.map((s) => s.id);
  let y = 0;
  const bar = (c, top, h) => {
    const end = Math.min(c.t1, PEN);
    const v = c.verdict.toLowerCase();
    let inner = "";
    if (c.verdict === "INDETERMINATE")
      inner = covered(c).map(([a, b]) => `<i class="px-cov" style="left:${((a - c.t0) / (c.t1 - c.t0)) * 100}%;width:${((Math.min(b, end) - a) / (c.t1 - c.t0)) * 100}%"></i>`).join("");
    if (c.verdict === "CONTRADICTED") inner = "<i class='px-strike'></i>";
    return `<span class="px-f px-${v}${c.id === SELECTED ? " px-sel" : ""}" style="left:${pct(c.t0)}%;width:${pct(end) - pct(c.t0)}%;top:${top}px;height:${h}px">${inner}</span>`;
  };
  const strip = (claims, h, pitch, off) =>
    lanes(claims).map((lane, i) => lane.filter((c) => c.t0 <= PEN).map((c) => bar(c, off + i * pitch, h)).join("")).join("");
  const rows = ids
    .map((id) => {
      const own = d.own(id);
      const n = lanes(own).length;
      const h = 14 + (n - 1) * 11;
      const top = y;
      y += h;
      return `<div class="px-lrow" style="top:${top}px;height:${h}px"><span class="px-lname">${sprite(id, 1)}${name(id)}</span><div class="px-ltrack">${strip(own, 9, 11, 2)}</div></div>`;
    })
    .join("");
  const aboutRow = `<div class="px-lrow" style="top:${y + 3}px;height:${lanes(d.aboutDara).length * 5 + 2}px"><span class="px-lname px-lname--dim">RE: DARA</span><div class="px-ltrack">${strip(d.aboutDara, 4, 5, 1)}</div></div>`;
  const hours = d.meta.hour_labels.map(({ tick, label }) => `<span style="left:${pct(tick)}%">${label}</span>`).join("");

  el.innerHTML = `<div class="px${opts.device ? " px--device px--live" : ""}">
    <header class="px-hud">
      <div class="px-title">ALIBI</div>
      <div class="px-hud-item">CASE ${d.meta.case_id}</div>
      <div class="px-hud-item px-clock"><i></i>${clock(PEN)}</div>
      <div class="px-hud-item">AUDITED<span class="px-meter"><i style="width:100%"></i></span>${d.meta.audited}/${d.meta.claims}</div>
      <div class="px-hud-item px-hud-right">SEED ${d.meta.seed}</div>
    </header>

    <section class="px-win px-map" aria-label="The house at ${clock(PEN)}">
      <div class="px-win-title">THE HOUSE AT ${clock(PEN)}</div>
      <svg class="px-corridors" width="740" height="500" shape-rendering="crispEdges" aria-hidden="true">${corridors}${links}</svg>
      ${rooms}
      ${voidCell}
    </section>

    <section class="px-win px-log" aria-label="Case log">
      <div class="px-win-title">CASE LOG</div>
      <div class="px-portrait">
        <div class="px-portrait-frame">${sprite("p4", 5)}</div>
        <div class="px-portrait-text">
          <div class="px-portrait-name">DARA</div>
          <div class="px-line">SAYS: <b>HALL</b> ${clock(sel.t0)}-${clock(sel.t1)}</div>
          <div class="px-line">OWN MEMORY: <b>KITCHEN</b>, SEEN</div>
          <div class="px-badge"><span class="px-f px-contradicted"><i class="px-strike"></i></span>CONTRADICTED</div>
        </div>
      </div>
      <div class="px-witness"><span class="px-f px-supported"></span>ESME SAW DARA IN THE KITCHEN</div>
      <div class="px-sub">"DARA WAS IN THE HALL", HEARD BY 3</div>
      ${trails}
      <div class="px-sub">INVENTORY</div>
      <div class="px-slots">${slots}</div>
    </section>

    <section class="px-win px-level" aria-label="Timeline">
      <div class="px-win-title">TIMELINE</div>
      <div class="px-hours">${hours}</div>
      <div class="px-lrows">
        ${rows}${aboutRow}
        <div class="px-fog" style="left:calc(112px + (100% - 112px) * ${pct(PEN) / 100})"></div>
        <div class="px-head" style="left:calc(112px + (100% - 112px) * ${pct(PEN) / 100})">${lens(3)}</div>
      </div>
      <div class="px-keys"><span><b>A</b> SELECT CLAIM</span><span><b>B</b> BACK</span><span><b>START</b> REPLAY</span><i class="px-cursor"></i></div>
    </section>
    ${opts.device ? '<section class="dv" aria-label="Pocket recorder"></section>' : ""}
  </div>`;
  if (opts.device) mount(el.querySelector(".dv"), d, el.querySelector(".px"));
}
