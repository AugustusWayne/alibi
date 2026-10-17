// Direction 2: the hardware toy. The recorder as a small, delightful device:
// an aluminium body, a dark display, a key per suspect, knobs and a REC lamp.
import { PEN, SELECTED, ORDER, clock, covered, lanes, pct } from "./shared.js";

function bar(c, top, h) {
  const v = c.verdict.toLowerCase();
  const end = Math.min(c.t1, PEN);
  let inner = "";
  if (c.verdict === "INDETERMINATE")
    inner = covered(c).map(([a, b]) => `<i class="ty-cov" style="left:${((a - c.t0) / (c.t1 - c.t0)) * 100}%;width:${((Math.min(b, end) - a) / (c.t1 - c.t0)) * 100}%"></i>`).join("");
  if (c.verdict === "CONTRADICTED") inner = '<i class="ty-strike"></i>';
  return `<span class="ty-bar ty-${v}${c.id === SELECTED ? " ty-sel" : ""}" style="left:${pct(c.t0)}%;width:${pct(end) - pct(c.t0)}%;top:${top}px;height:${h}px">${inner}</span>`;
}

function strip(claims, h, pitch, offset = 0) {
  return lanes(claims)
    .map((lane, i) => lane.filter((c) => c.t0 <= PEN).map((c) => bar(c, offset + i * pitch, h)).join(""))
    .join("");
}

export function render(el, d) {
  const sel = d.claim(SELECTED);
  const ids = d.suspects.map((s) => s.id);

  let y = 0;
  const rows = ids
    .map((id) => {
      const own = d.own(id);
      const n = lanes(own).length;
      const h = 26 + (n - 1) * 16;
      const top = y;
      y += h + 4;
      return `<div class="ty-row" style="top:${top}px;height:${h}px">
        <span class="ty-ch">${d.names[id]}</span>
        <div class="ty-track">${strip(own, 14, 16, 6)}</div>
      </div>`;
    })
    .join("");
  const aboutTop = y + 8;
  const about = `<div class="ty-row ty-row--about" style="top:${aboutTop}px;height:${lanes(d.aboutDara).length * 9 + 2}px">
      <span class="ty-ch ty-ch--dim">re: dara</span>
      <div class="ty-track">${strip(d.aboutDara, 7, 9, 1)}</div>
    </div>`;

  const hours = d.meta.hour_labels.map(({ tick, label }) => `<span style="left:${pct(tick)}%">${label.slice(0, 2)}</span>`).join("");

  const keys = ids
    .map((id) => {
      const on = id === sel.speaker;
      const conflict = d.own(id).some((c) => c.verdict === "CONTRADICTED");
      return `<button type="button" class="ty-key${on ? " ty-key--on" : ""}">
        <i class="ty-led${on ? " ty-led--on" : conflict ? " ty-led--warm" : ""}"></i>
        <span class="ty-key-name">${d.names[id]}</span>
        <span class="ty-key-n">${d.claims.filter((c) => c.speaker === id).length}</span>
      </button>`;
    })
    .join("");

  const meters = ORDER.map((v) => {
    const n = d.tally[v] ?? 0;
    const h = n ? Math.max((n / d.meta.claims) * 100, 6) : 0;
    return `<div class="ty-meter"><div class="ty-meter-well"><span class="ty-bar ty-${v.toLowerCase()}" style="left:0;right:0;bottom:0;height:${h}%;top:auto">${v === "CONTRADICTED" && n ? '<i class="ty-strike"></i>' : ""}${v === "INDETERMINATE" ? '<i class="ty-cov" style="left:0;width:100%;top:45%;bottom:0"></i>' : ""}</span></div><span class="ty-meter-n">${n}</span><span class="ty-meter-l">${v.slice(0, 5)}</span></div>`;
  }).join("");

  const grille = Array.from({ length: 6 * 10 }, () => "<i></i>").join("");

  el.innerHTML = `<div class="ty">
    <div class="ty-body">
      <header class="ty-head">
        <div class="ty-brand">alibi<span class="ty-model">AR-${d.meta.seed} epistemic recorder</span></div>
        <div class="ty-rec"><i></i><span>REC</span></div>
        <div class="ty-grille">${grille}</div>
      </header>

      <section class="ty-screen" aria-label="Display">
        <div class="ty-screen-top">
          <div class="ty-clock">${clock(PEN)}</div>
          <div class="ty-say">
            <div><b>CH4 DARA</b> SAYS: HALL ${clock(sel.t0)}-${clock(sel.t1)}</div>
            <div>OWN MEMORY: KITCHEN <span class="ty-hot">CONTRADICTED</span></div>
            <div class="ty-dim">ESME SAW DARA IN THE KITCHEN. 3 REPEAT "HALL", SECONDHAND.</div>
          </div>
          <div class="ty-count">${d.meta.claims}<small>CLAIMS</small></div>
        </div>
        <div class="ty-hours">${hours}</div>
        <div class="ty-rows">${rows}${about}
          <div class="ty-head-line" style="left:calc(64px + (100% - 64px) * ${pct(PEN) / 100})"></div>
          <div class="ty-fog" style="left:calc(64px + (100% - 64px) * ${pct(PEN) / 100})"></div>
        </div>
      </section>

      <section class="ty-side">
        <div class="ty-knobs">
          <div class="ty-knob-wrap"><div class="ty-knob" style="--a:-40deg"></div><span>SPEED</span></div>
          <div class="ty-knob-wrap"><div class="ty-knob ty-knob--hot" style="--a:70deg"></div><span>ZOOM</span></div>
        </div>
        <div class="ty-transport">
          <button type="button" class="ty-tkey" aria-label="Rewind"><svg viewBox="0 0 20 20"><path d="M10 4 3 10l7 6V4Zm7 0-7 6 7 6V4Z"/></svg></button>
          <button type="button" class="ty-tkey ty-tkey--hot" aria-label="Play"><svg viewBox="0 0 20 20"><path d="M5 3v14l12-7L5 3Z"/></svg></button>
          <button type="button" class="ty-tkey" aria-label="Stop"><svg viewBox="0 0 20 20"><path d="M4 4h12v12H4z"/></svg></button>
        </div>
        <div class="ty-mini" aria-label="Trails">
          <div class="ty-mini-title">TRAIL: "DARA IN HALL"</div>
          <div>BLAKE &gt; DARA <span class="ty-hot">ORIGIN</span></div>
          <div>AVERY &gt; ???? <span class="ty-dim">NO RECORD</span></div>
          <div>FARIS &gt; DARA <span class="ty-dim">TOLD EARLY</span></div>
        </div>
      </section>

      <section class="ty-keys" aria-label="Suspects">${keys}</section>

      <section class="ty-foot">
        <div class="ty-meters">${meters}</div>
        <div class="ty-print">
          <span>1 KEY PER SUSPECT</span><span>LED: CONTRADICTED</span><span>HATCH: HEARD, NOT SEEN</span><span>GAPS STAY DARK</span>
        </div>
      </section>
    </div>
  </div>`;
}
