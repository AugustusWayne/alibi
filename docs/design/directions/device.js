// The pocket recorder: the hardware toy, redrawn as an object that belongs in
// the 8-bit house. Pixel art on a 4px grid, in the same sixteen colours.
//
// What each part is a reference to, so none of it is decoration:
//   cassette   the board is a replay; the reels' tape packs are sized from
//              the replay position, so the take-up reel fills as the case plays
//   tape label the seed is the tape: same tape, same evening, every time
//   counter    the tape counter is the tick
//   RX lamp    claims arrive over a feed; the antenna blinks as they do
//   polygraph  the strip chart, as a slip of paper under a jittering needle;
//              the pips are the detective's real budget of two traces
//   sticker    the one-line thesis of the fill system
import { PEN, clock } from "./shared.js";

const C = {
  black: "#000000", night: "#1d2b53", plum: "#7e2553", brown: "#ab5236", stone: "#5f574f",
  silver: "#c2c3c7", cream: "#fff1e8", red: "#ff004d", orange: "#ffa300", lime: "#00e436", lav: "#83769c",
};
const U = 4;
const W = 114;
const H = 88;
const rect = (x, y, w, h, fill) => `<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="${fill}"/>`;

/** A filled pixel disc: every grid cell whose centre is inside radius r. */
function disc(cx, cy, r, fill) {
  const out = [];
  for (let y = Math.floor(cy - r); y <= Math.ceil(cy + r); y++)
    for (let x = Math.floor(cx - r); x <= Math.ceil(cx + r); x++)
      if ((x - cx) ** 2 + (y - cy) ** 2 <= r * r + r * 0.6) out.push(rect(x, y, 1, 1, fill));
  return out.join("");
}

const ICONS = {
  rec: [".###.", "#####", "#####", "#####", ".###."],
  play: ["#....", "###..", "#####", "###..", "#...."],
  rew: ["..#..#", ".##.##", "######", ".##.##", "..#..#"],
  ff: ["#..#..", "##.##.", "######", "##.##.", "#..#.."],
  stop: ["#####", "#####", "#####", "#####", "#####"],
  pause: ["##.##", "##.##", "##.##", "##.##", "##.##"],
};
const KEYS = [
  { id: "rec", label: "Record" },
  { id: "play", label: "Play" },
  { id: "rew", label: "Rewind" },
  { id: "ff", label: "Fast forward" },
  { id: "stop", label: "Stop" },
  { id: "pause", label: "Pause" },
];
const keyX = (i) => 8 + i * 16;

function keys(pressed) {
  return KEYS.map((k, i) => {
    const x = keyX(i);
    const down = k.id === pressed;
    const top = down ? 2 : 0;
    const face = k.id === "rec" ? C.red : down ? C.lav : C.silver;
    const icon = ICONS[k.id];
    const ix = x + 1 + Math.floor((12 - icon[0].length) / 2);
    const iy = top + 2;
    const glyph = icon.flatMap((row, y) => [...row].map((c, x2) => (c === "#" ? rect(ix + x2, iy + y, 1, 1, k.id === "rec" ? C.cream : C.black) : ""))).join("");
    return rect(x, top, 14, 10 - top, C.black) + rect(x + 1, top + 1, 12, 8 - top, face) +
      rect(x + 1, top + 1, 12, 1, down ? C.stone : C.cream) + (down ? "" : rect(x + 1, 8, 12, 1, C.stone)) + glyph;
  }).join("");
}

/** One reel: a tape pack sized by how much tape it holds, and a hub whose
 *  three spokes are drawn in three frames so it can turn in steps. */
function reel(cx, cy, pack, cls) {
  const frames = [90, 130, 170].map((deg, f) => {
    const spokes = [0, 120, 240].flatMap((off) => {
      const a = ((deg + off) * Math.PI) / 180;
      return [1, 2].map((d) => rect(Math.round(cx + d * Math.cos(a)), Math.round(cy - d * Math.sin(a)), 1, 1, C.stone));
    });
    return `<g class="dv-f dv-f${f}">${spokes.join("")}</g>`;
  });
  return `<g class="${cls}">${disc(cx, cy, pack, C.brown)}${disc(cx, cy, 2.2, C.cream)}${rect(cx, cy, 1, 1, C.black)}${frames.join("")}</g>`;
}

function knob(speed) {
  const cx = 95, cy = 66;
  const angle = { 1: 135, 2: 90, 4: 45 }[speed];
  const a = (angle * Math.PI) / 180;
  let shine = "";
  for (let y = cy - 8; y <= cy; y++)
    for (let x = cx - 8; x <= cx; x++)
      if ((x - cx) ** 2 + (y - cy) ** 2 <= 60 && (x - cx) + (y - cy) < -7) shine += rect(x, y, 1, 1, C.silver);
  const line = [2, 3, 4, 5, 6].map((d) => rect(Math.round(cx + d * Math.cos(a)), Math.round(cy - d * Math.sin(a)), 1, 1, C.cream)).join("");
  return disc(cx, cy, 9, C.black) + disc(cx, cy, 8, C.stone) + shine + line;
}

function art(state) {
  const p = PEN / 300;
  const packL = 3 + Math.round((1 - p) * 2.6);
  const packR = 3 + Math.round(p * 2.6);
  const glare = [0, 1, 2, 3, 4, 5].map((k) => rect(8 + k, 26 - k, 1, 1, C.lav)).join("") +
    [0, 1, 2, 3].map((k) => rect(11 + k, 26 - k, 1, 1, C.lav)).join("");
  const grille = [];
  for (let y = 79; y <= 84; y += 2) for (let x = 82; x <= 108; x += 2) grille.push(rect(x, y, 1, 1, C.stone));

  return `<svg class="dv-art" width="${W * U}" height="${H * U}" viewBox="0 0 ${W} ${H}" shape-rendering="crispEdges" aria-hidden="true">
    ${rect(3, 8, 112, 80, C.night)}
    ${rect(106, 0, 3, 7, C.black)}${rect(107, 1, 1, 6, C.silver)}<g class="dv-rx-tip">${rect(106, 0, 3, 2, C.lime)}</g>
    ${rect(1, 6, 112, 81, C.black)}${rect(2, 7, 110, 79, C.silver)}
    ${rect(2, 7, 110, 1, C.cream)}${rect(2, 7, 1, 79, C.cream)}${rect(2, 85, 110, 1, C.stone)}${rect(111, 7, 1, 79, C.stone)}
    ${rect(2, 7, 1, 1, C.black)}${rect(111, 7, 1, 1, C.black)}${rect(2, 85, 1, 1, C.black)}${rect(111, 85, 1, 1, C.black)}
    ${rect(2, 16, 110, 1, C.orange)}
    ${rect(7, 5, 96, 5, C.black)}
    ${keys(state.running ? "play" : "pause")}
    ${rect(87, 9, 5, 5, C.black)}<g class="dv-rec">${rect(88, 10, 3, 3, C.red)}${rect(88, 10, 1, 1, C.cream)}</g>
    ${rect(99, 9, 5, 5, C.black)}<g class="dv-rx">${rect(100, 10, 3, 3, C.lime)}${rect(100, 10, 1, 1, C.cream)}</g>

    ${rect(5, 18, 58, 33, C.black)}${rect(6, 19, 56, 31, C.night)}
    ${rect(8, 20, 52, 29, C.black)}${rect(9, 21, 50, 27, C.stone)}${rect(9, 21, 50, 1, C.silver)}
    ${rect(12, 23, 44, 8, C.cream)}${rect(12, 29, 44, 1, C.orange)}${rect(12, 30, 44, 1, C.red)}
    ${rect(15, 32, 38, 14, C.black)}${rect(16, 33, 36, 12, C.night)}
    ${reel(23, 38, packL, "dv-reel")}${reel(45, 38, packR, "dv-reel")}
    ${rect(23, 43, 22, 1, C.brown)}
    ${rect(10, 22, 1, 1, C.black)}${rect(57, 22, 1, 1, C.black)}${rect(10, 46, 1, 1, C.black)}${rect(57, 46, 1, 1, C.black)}
    ${glare}

    ${rect(65, 18, 46, 24, C.black)}${rect(66, 19, 44, 22, C.stone)}${rect(68, 21, 40, 18, C.black)}
    ${rect(65, 44, 46, 8, C.black)}${rect(66, 45, 44, 6, C.silver)}
    ${[0, 1, 2, 3].map((i) => rect(78 + i * 8, 45, 7, 6, C.black)).join("")}

    ${rect(46, 53, 3, 3, C.lime)}${rect(51, 53, 3, 3, C.lime)}
    ${rect(5, 56, 72, 1, C.black)}${rect(5, 57, 72, 1, C.stone)}
    ${rect(7, 58, 68, 18, C.cream)}${rect(7, 58, 1, 18, C.silver)}${rect(74, 58, 1, 18, C.silver)}

    ${knob(state.speed)}
    ${grille.join("")}
    ${rect(4, 77, 42, 9, C.black)}${rect(5, 78, 40, 7, C.orange)}${rect(44, 78, 1, 1, C.cream)}
  </svg>`;
}

/** A pixel squiggle for the polygraph slip, as one seamless tile. */
function slipTile() {
  const w = 68;
  let y = 9;
  const cells = [];
  for (let x = 0; x < w; x++) {
    const n = Math.sin(x * 12.9898) * 43758.5453;
    const step = Math.round((n - Math.floor(n)) * 6 - 3);
    const next = x === w - 1 ? 9 : Math.max(3, Math.min(15, y + step));
    for (let yy = Math.min(y, next); yy <= Math.max(y, next); yy++) cells.push(`<rect x="${x}" y="${yy}" width="1" height="1"/>`);
    y = next;
  }
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${w * U}" height="${18 * U}" viewBox="0 0 ${w} 18" shape-rendering="crispEdges" fill="#1d2b53">${cells.join("")}</svg>`;
  return `url('data:image/svg+xml,${encodeURIComponent(svg)}')`;
}

const MARQUEE = "DARA SAYS HALL. DARA'S MEMORY SAYS KITCHEN. ESME SAW DARA THERE. 3 REPEAT 'HALL', HEARD NOT SEEN.";
const BEEPS = {
  rec: "ALREADY RECORDING. IT NEVER STOPS.",
  rew: "REWIND = REPLAY. SAME TAPE, SAME EVENING.",
  ff: "NO SKIPPING. THE PEN WRITES IN ORDER.",
  stop: `STOPPED AT ${clock(PEN)}. PRESS PLAY.`,
};

function markup(d, state) {
  const counter = String(PEN).padStart(4, "0");
  return `${art(state)}
    <div class="dv-brand"><b>ALIBI</b><span>POCKET RECORDER AR-${d.meta.seed}</span></div>
    <span class="dv-lbl" style="left:${92 * U}px;top:${10 * U}px">REC</span>
    <span class="dv-lbl" style="left:${104 * U + 2}px;top:${10 * U}px">RX</span>
    <div class="dv-tape"><b>SEED ${d.meta.seed}</b><span>SAME TAPE, SAME EVENING</span></div>
    <div class="dv-lcd" role="status" aria-live="polite">
      <div class="dv-lcd-clock">${clock(PEN)}</div>
      <div class="dv-lcd-mode">${state.running ? "PLAY" : "PAUSE"} ${state.speed}X</div>
      <div class="dv-lcd-scroll"><span>${state.message ?? MARQUEE}</span></div>
    </div>
    <span class="dv-lbl dv-lbl--dark" style="left:${67 * U}px;top:${46 * U + 2}px">CNT</span>
    ${[...counter].map((c, i) => `<span class="dv-digit" style="left:${(78 + i * 8) * U}px">${c}</span>`).join("")}
    <span class="dv-lbl dv-lbl--dark dv-poly" style="left:${5 * U}px;top:${52 * U + 2}px">POLYGRAPH</span>
    <span class="dv-lbl dv-lbl--dark" style="left:${55 * U + 2}px;top:${52 * U + 2}px">2 LEFT</span>
    <div class="dv-slip" style="background-image:${slipTile()}"></div>
    <div class="dv-needle"><i></i></div>
    ${[["1X", 84, 55], ["2X", 93, 52], ["4X", 103, 55]].map(([t, x, y]) => `<span class="dv-lbl dv-lbl--dark${String(state.speed) + "X" === t ? " dv-lbl--on" : ""}" style="left:${x * U}px;top:${y * U}px">${t}</span>`).join("")}
    <span class="dv-lbl dv-lbl--dark" style="left:${89 * U}px;top:${76 * U + 2}px">SPEED</span>
    <span class="dv-sticker">HEARD != SEEN</span>
    ${KEYS.map((k, i) => `<button type="button" class="dv-key" style="left:${keyX(i) * U}px" aria-label="${k.label}"></button>`).join("")}
    <button type="button" class="dv-knob" aria-label="Speed, ${state.speed}x"></button>`;
}

/** Mount the recorder into `host` and make its controls work. */
export function mount(host, d, scene) {
  const state = { running: true, speed: 1, message: null };
  let timer = null;
  const draw = () => {
    host.innerHTML = markup(d, state);
    host.classList.toggle("dv--paused", !state.running);
    host.style.setProperty("--spd", String(state.speed));
    host.querySelectorAll(".dv-key").forEach((btn, i) => btn.addEventListener("click", () => press(KEYS[i].id)));
    host.querySelector(".dv-knob").addEventListener("click", () => {
      state.speed = { 1: 2, 2: 4, 4: 1 }[state.speed];
      draw();
    });
  };
  const say = (msg) => {
    state.message = msg;
    draw();
    clearTimeout(timer);
    timer = setTimeout(() => {
      state.message = null;
      draw();
    }, 4000);
  };
  const press = (id) => {
    if (id === "play") state.running = true;
    if (id === "pause" || id === "stop") state.running = false;
    if (BEEPS[id]) say(BEEPS[id]);
    else draw();
  };
  draw();

  // Up up down down left right left right B A. The audit takes no shortcuts,
  // so the code only makes the house dance.
  const code = ["ArrowUp", "ArrowUp", "ArrowDown", "ArrowDown", "ArrowLeft", "ArrowRight", "ArrowLeft", "ArrowRight", "b", "a"];
  let at = 0;
  document.addEventListener("keydown", (e) => {
    at = e.key === code[at] ? at + 1 : e.key === code[0] ? 1 : 0;
    if (at < code.length) return;
    at = 0;
    scene.classList.add("px-party");
    say("CHEATS OFF. THE AUDIT ONLY TAKES EVIDENCE.");
    setTimeout(() => scene.classList.remove("px-party"), 4000);
  });
}
