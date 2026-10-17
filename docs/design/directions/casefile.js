// Direction 3: the case file on a desk. A typed statement log in a manila
// folder; private memory appears as redaction bars, verdicts as stamps, and
// the reader's own notes in pencil.
import { PEN, SELECTED, ORDER, clock, covered, lanes, pct } from "./shared.js";

function bar(c, top, h) {
  const v = c.verdict.toLowerCase();
  const end = Math.min(c.t1, PEN);
  let inner = "";
  if (c.verdict === "INDETERMINATE")
    inner = covered(c).map(([a, b]) => `<i class="cf-cov" style="left:${((a - c.t0) / (c.t1 - c.t0)) * 100}%;width:${((Math.min(b, end) - a) / (c.t1 - c.t0)) * 100}%"></i>`).join("");
  if (c.verdict === "CONTRADICTED") inner = '<i class="cf-strike"></i>';
  return `<span class="cf-bar cf-${v}" style="left:${pct(c.t0)}%;width:${pct(end) - pct(c.t0)}%;top:${top}px;height:${h}px">${inner}</span>`;
}

function strip(claims, h, pitch, offset) {
  return lanes(claims)
    .map((lane, i) => lane.filter((c) => c.t0 <= PEN).map((c) => bar(c, offset + i * pitch, h)).join(""))
    .join("");
}

export function render(el, d) {
  const sel = d.claim(SELECTED);
  const ids = d.suspects.map((s) => s.id);
  const W = 640; // track width on the sheet

  let y = 0;
  const rows = ids
    .map((id) => {
      const own = d.own(id);
      const n = lanes(own).length;
      const h = 28 + (n - 1) * 18;
      const top = y;
      y += h;
      return `<div class="cf-row" style="top:${top}px;height:${h}px">
        <span class="cf-name">${d.names[id]}</span>
        <div class="cf-track">${strip(own, 13, 18, 8)}</div>
      </div>`;
    })
    .join("");
  const aboutTop = y + 22;
  const about = `<div class="cf-sub" style="top:${y + 4}px">Statements by others about dara</div>
    <div class="cf-row cf-row--about" style="top:${aboutTop}px;height:${lanes(d.aboutDara).length * 10 + 4}px">
      <span class="cf-name cf-name--dim">re: dara</span>
      <div class="cf-track">${strip(d.aboutDara, 7, 10, 2)}</div>
    </div>`;

  const penX = 92 + (pct(PEN) / 100) * W;
  const circle = 92 + (pct(sel.t0) / 100) * W;
  const circleW = (pct(sel.t1) - pct(sel.t0)) / 100 * W;
  const daraTop = ids.slice(0, ids.indexOf("p4")).reduce((s, id) => s + 28 + (lanes(d.own(id)).length - 1) * 18, 0);

  const hours = d.meta.hour_labels.map(({ tick, label }) => `<span style="left:${pct(tick)}%">${label}</span>`).join("");

  const tally = ORDER.map((v) => {
    const n = d.tally[v] ?? 0;
    const marks = "|".repeat(Math.min(n, 5)) + (n > 5 ? ` + ${n - 5}` : "");
    return `<div class="cf-tally-row"><span>${v.toLowerCase()}</span><span class="cf-tally-sample"><span class="cf-bar cf-${v.toLowerCase()}" style="left:0;width:100%;top:0;height:9px">${v === "CONTRADICTED" ? '<i class="cf-strike"></i>' : ""}${v === "INDETERMINATE" ? '<i class="cf-cov" style="left:0;width:55%"></i>' : ""}</span></span><span class="cf-tally-n">${n}</span><span class="cf-marks">${n ? marks : "none"}</span></div>`;
  }).join("");

  el.innerHTML = `<div class="cf">
    <div class="cf-folder">
      <div class="cf-tab">CASE ${d.meta.case_id}</div>
    </div>

    <article class="cf-sheet" aria-label="Statement log">
      <header class="cf-sheet-head">
        <h1>Statement log</h1>
        <p>Seed ${d.meta.seed}. ${d.meta.claims} statements taken, ${d.meta.audited} checked against each speaker's own memory. Read to ${clock(PEN)}.</p>
      </header>
      <div class="cf-hours">${hours}</div>
      <div class="cf-log">
        ${rows}${about}
        <div class="cf-pen" style="left:${penX}px"><span>${clock(PEN)}</span></div>
        <svg class="cf-ring" style="left:${circle - 10}px;top:${daraTop - 4}px" width="${circleW + 20}" height="38" viewBox="0 0 ${circleW + 20} 38" aria-hidden="true">
          <path d="M6 20 C 4 6, ${circleW + 14} 2, ${circleW + 16} 17 S 12 38, 9 16" />
        </svg>
      </div>
      <section class="cf-memory">
        <h2>From dara's own memory, as the audit is allowed to see it</h2>
        <p>Witnessed: <span class="cf-redact" style="width:120px"></span> at <b>kitchen</b>, 19:42 to 20:02 <span class="cf-redact" style="width:64px"></span></p>
        <p>Nothing that places dara at <b>hall</b> in that window.</p>
      </section>
      <section class="cf-tally">${tally}</section>
    </article>

    <aside class="cf-card" aria-label="dara">
      <div class="cf-clip"></div>
      <div class="cf-card-name">DARA</div>
      <div class="cf-card-line">Says: <b>hall</b>, ${clock(sel.t0)} to ${clock(sel.t1)}</div>
      <div class="cf-card-line">Own memory: <b>kitchen</b></div>
      <div class="cf-card-line">Esme saw dara: <b>kitchen</b></div>
      <div class="cf-stamp cf-stamp--red">CONTRADICTED</div>
      <div class="cf-trail">
        <div>Trail of "dara was in the hall"</div>
        <div>blake, from dara</div>
        <div>avery, from a record no one holds</div>
        <div>faris, told at 19:41, before dara knew</div>
      </div>
      <div class="cf-stamp cf-stamp--ochre">HEARSAY x3</div>
    </aside>

    <aside class="cf-note">
      Avery, Blake and Faris all say <u>hall</u>. None of them saw it.<br>Esme did see dara. Kitchen.
    </aside>
  </div>`;
}
