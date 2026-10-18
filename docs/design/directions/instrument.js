// Direction 1: the living instrument. A pale chart-paper roll with teal ink,
// fed through a dark machine body. The needle's trace swings where nothing
// accounts for the minutes, and the paper past the pen is simply unwritten.
import { PEN, SELECTED, ORDER, clock, covered, lanes, pct } from "./shared.js";

const ROW = 34;
const BAR = 20;

function fill(c, extra = "") {
  const v = c.verdict.toLowerCase();
  let inner = "";
  if (c.verdict === "INDETERMINATE")
    inner = covered(c)
      .map(([a, b]) => `<i class="in-cov" style="left:${((a - c.t0) / (c.t1 - c.t0)) * 100}%;width:${((b - a) / (c.t1 - c.t0)) * 100}%"></i>`)
      .join("");
  if (c.verdict === "CONTRADICTED") inner = '<i class="in-strike"></i>';
  return `<span class="in-bar in-${v}${c.id === SELECTED ? " in-sel" : ""}" ${extra}>${inner}</span>`;
}

function bars(claims, rowTop, barH, pitch) {
  return lanes(claims)
    .map((lane, li) =>
      lane
        .filter((c) => c.t0 <= PEN)
        // Ink cannot run ahead of the pen: a claim still being written stops at it.
        .map((c) => fill(c, `style="left:${pct(c.t0)}%;width:${pct(Math.min(c.t1, PEN)) - pct(c.t0)}%;top:${rowTop + li * pitch}px;height:${barH}px"`))
        .join(""),
    )
    .join("");
}

// A deterministic wobble, so the trace looks hand-drawn by a needle but is
// the same on every load.
function noise(i, seed) {
  const x = Math.sin(i * 12.9898 + seed * 78.233) * 43758.5453;
  return x - Math.floor(x);
}

/** The needle trace for one channel: near-flat where the account covers the
 *  minute, a wide swing where it does not. Drawn only up to the pen. */
function trace(claims, seed, width) {
  const isCovered = (t) => claims.some((c) => c.t0 <= t && t < c.t1);
  const conflict = (t) => claims.some((c) => c.verdict === "CONTRADICTED" && c.t0 <= t && t < c.t1);
  const pts = [];
  const red = [];
  for (let t = 0; t <= PEN; t += 1) {
    const x = (pct(t) / 100) * width;
    const amp = isCovered(t) ? 1.2 : 6;
    const y = 5 + (noise(t, seed) - 0.5) * 2 * amp;
    pts.push(`${x.toFixed(1)},${y.toFixed(1)}`);
    if (conflict(t)) red.push(`${x.toFixed(1)},${y.toFixed(1)}`);
  }
  return `<svg class="in-trace" width="${width}" height="10" aria-hidden="true">
    <polyline points="${pts.join(" ")}" />
    ${red.length ? `<polyline class="in-trace--red" points="${red.join(" ")}" />` : ""}
  </svg>`;
}

const icon = {
  rew: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M10 4 3 10l7 6V4Zm7 0-7 6 7 6V4Z"/></svg>',
  play: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M5 3v14l12-7L5 3Z"/></svg>',
};

export function render(el, d) {
  const TRACK_W = 1280 - 80 - 40 - 92 - 16; // paper width minus margins and the name column
  const sel = d.claim(SELECTED);
  const order = d.suspects.map((s) => s.id);

  let y = 0;
  const rows = order
    .map((id, i) => {
      const own = d.own(id);
      const n = lanes(own).length;
      const h = ROW + (n - 1) * (BAR + 8);
      const top = y;
      y += h + 6;
      return `<div class="in-row" style="top:${top}px;height:${h}px">
        <div class="in-name${own.some((c) => c.verdict === "CONTRADICTED") ? " in-name--conflict" : ""}">${d.names[id]}</div>
        <div class="in-track">
          ${trace(own, i + 1, TRACK_W)}
          ${bars(own, 12, BAR, BAR + 8)}
        </div>
      </div>`;
    })
    .join("");

  const aboutTop = y + 10;
  const about = d.aboutDara;
  const aboutLanes = lanes(about).length;
  const aboutRow = `<div class="in-about-label" style="top:${aboutTop}px">what everyone else said about dara</div>
    <div class="in-row in-row--about" style="top:${aboutTop + 20}px;height:${aboutLanes * 16 + 4}px">
      <div class="in-name in-name--dim">about dara</div>
      <div class="in-track">${bars(about, 2, 12, 16)}</div>
    </div>`;

  const gridLines = Array.from({ length: 61 }, (_, i) => `<i class="${i % 12 === 0 ? "hr" : ""}" style="left:${pct(i * 5)}%"></i>`).join("");
  const sprockets = Array.from({ length: 66 }, (_, i) => `<i style="left:${10 + i * 18}px"></i>`).join("");
  const hours = d.meta.hour_labels
    .map(({ tick, label }) => `<span style="left:${pct(tick)}%"${tick === 300 ? ' class="end"' : ""}>${label}</span>`)
    .join("");

  const tally = ORDER.map((v) => {
    const n = d.tally[v] ?? 0;
    const w = Math.max((n / d.meta.claims) * 100, n ? 3 : 0);
    const sample = v === "INDETERMINATE"
      ? `<span class="in-bar in-indeterminate" style="width:${w}%"><i class="in-cov" style="left:0;width:55%"></i></span><span class="in-bracket" style="left:55%;width:${w * 0.45}%"></span>`
      : n ? `<span class="in-bar in-${v.toLowerCase()}" style="width:${w}%">${v === "CONTRADICTED" ? '<i class="in-strike"></i>' : ""}</span>` : "";
    return `<div class="in-tally-row"><span class="in-tally-name">${v.toLowerCase()}</span><span class="in-tally-track">${sample}</span><span class="in-tally-n">${n}</span></div>`;
  }).join("");

  const trails = [
    ["blake", "dara", "reaches dara, whose own memory puts dara elsewhere"],
    ["avery", "?", "cites a record that exists in no memory"],
    ["faris", "dara", "told at 19:41, a minute before dara learned it"],
  ]
    .map(([from, to, what]) => `<div class="in-trail"><span class="in-chip">${from}</span><span class="in-link${to === "?" ? " in-link--dead" : ""}"></span><span class="in-chip${to === "?" ? " in-chip--void" : " in-chip--origin"}">${to === "?" ? "no record" : to}</span><span class="in-trail-what">${what}</span></div>`)
    .join("");

  el.innerHTML = `<div class="in">
    <header class="in-head">
      <div class="in-mark">alibi<span>strip recorder, seed ${d.meta.seed}</span></div>
      <div class="in-status"><span>case ${d.meta.case_id}</span><span>claims ${d.meta.claims}</span><span>audited ${d.meta.audited}</span><span class="in-rec"><i></i>recording</span></div>
    </header>

    <section class="in-top">
      <div class="in-clock">${clock(PEN)}</div>
      <div class="in-headline">
        <h1>Dara says the hall. Dara's own memory says the kitchen.</h1>
        <p>${clock(sel.t0)} to ${clock(sel.t1)}, the incident window. Esme saw dara in the kitchen. Avery, blake and faris repeat the hall, and none of them saw it.</p>
      </div>
      <aside class="in-card" aria-label="Verdict tally">
        <div class="in-card-sprockets"></div>
        ${tally}
      </aside>
    </section>

    <section class="in-paper" aria-label="Chart paper">
      <div class="in-sprockets in-sprockets--top">${sprockets}</div>
      <div class="in-sprockets in-sprockets--bottom">${sprockets}</div>
      <div class="in-hours">${hours}</div>
      <div class="in-grid">${gridLines}</div>
      <div class="in-rows">${rows}${aboutRow}</div>
      <div class="in-pen" style="left:${128 + (pct(PEN) / 100) * TRACK_W}px">
        <span class="in-pen-head"></span>
      </div>
    </section>

    <footer class="in-deck">
      <div class="in-keys">
        <button type="button" class="in-key" aria-label="Rewind">${icon.rew}</button>
        <button type="button" class="in-key in-key--on" aria-label="Play">${icon.play}</button>
        <button type="button" class="in-key in-key--text">1x</button>
        <span class="in-pos">${clock(PEN)} <em>of</em> 23:00</span>
      </div>
      <div class="in-trails">
        <div class="in-trails-title">Three trails for "dara was in the hall"</div>
        ${trails}
      </div>
    </footer>
  </div>`;
}
