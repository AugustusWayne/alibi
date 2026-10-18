/** The pocket recorder (brief 5.8): the hardware toy as pixel art, and the
 *  real control surface for the replay.
 *
 *  Every part refers to something true. The reels' tape packs are sized from
 *  the playhead. The tape label is the seed: same tape, same evening. The
 *  counter is the tick. The RX lamp lights when a claim has just been drawn.
 *  The polygraph needle swings by how many suspects have no account at each
 *  minute, and its slip feeds only while the replay runs. The pips are the
 *  detective's budget of two traces.
 */
import { memo, useEffect, useRef, useState } from "react";

import { caseFile, unaccountedByTick } from "../lib/case";
import type { Replay } from "../lib/replay";
import { TICK_MAX, tickToClock } from "../lib/time";

const U = 4;
const W = 114;
const H = 88;

type Cell = { x: number; y: number; w?: number; h?: number; c: string };
const R = ({ x, y, w = 1, h = 1, c }: Cell) => <rect x={x} y={y} width={w} height={h} style={{ fill: `var(--${c})` }} />;
const rects = (cells: Cell[]) => cells.map((cell, i) => <R key={i} {...cell} />);

function disc(cx: number, cy: number, r: number, c: string): Cell[] {
  const out: Cell[] = [];
  for (let y = Math.floor(cy - r); y <= Math.ceil(cy + r); y++)
    for (let x = Math.floor(cx - r); x <= Math.ceil(cx + r); x++)
      if ((x - cx) ** 2 + (y - cy) ** 2 <= r * r + r * 0.6) out.push({ x, y, c });
  return out;
}

const ICONS: Record<string, string[]> = {
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
  { id: "rew", label: "Rewind to 18:00" },
  { id: "ff", label: "Fast forward to 23:00" },
  { id: "stop", label: "Stop" },
  { id: "pause", label: "Pause" },
] as const;
type KeyId = (typeof KEYS)[number]["id"];
const keyX = (i: number) => 8 + i * 16;

/** The body, cassette shell, bezels and everything that never changes. */
const Chassis = memo(function Chassis() {
  const grille: Cell[] = [];
  for (let y = 79; y <= 84; y += 2) for (let x = 82; x <= 108; x += 2) grille.push({ x, y, c: "stone" });
  const glare: Cell[] = [0, 1, 2, 3, 4, 5].map((k) => ({ x: 8 + k, y: 26 - k, c: "lav" }))
    .concat([0, 1, 2, 3].map((k) => ({ x: 11 + k, y: 26 - k, c: "lav" })));
  return (
    <svg className="rec__art" width={W * U} height={H * U} viewBox={`0 0 ${W} ${H}`} shapeRendering="crispEdges" aria-hidden="true">
      {rects([
        { x: 3, y: 8, w: 112, h: 80, c: "night" },
        { x: 106, y: 0, w: 3, h: 7, c: "black" }, { x: 107, y: 1, w: 1, h: 6, c: "silver" },
        { x: 1, y: 6, w: 112, h: 81, c: "black" }, { x: 2, y: 7, w: 110, h: 79, c: "silver" },
        { x: 2, y: 7, w: 110, h: 1, c: "cream" }, { x: 2, y: 7, w: 1, h: 79, c: "cream" },
        { x: 2, y: 85, w: 110, h: 1, c: "stone" }, { x: 111, y: 7, w: 1, h: 79, c: "stone" },
        { x: 2, y: 7, c: "black" }, { x: 111, y: 7, c: "black" }, { x: 2, y: 85, c: "black" }, { x: 111, y: 85, c: "black" },
        { x: 2, y: 16, w: 110, h: 1, c: "orange" },
        { x: 7, y: 5, w: 96, h: 5, c: "black" },
        { x: 87, y: 9, w: 5, h: 5, c: "black" }, { x: 99, y: 9, w: 5, h: 5, c: "black" },
        // cassette lid, shell, label and tape window
        { x: 5, y: 18, w: 58, h: 33, c: "black" }, { x: 6, y: 19, w: 56, h: 31, c: "night" },
        { x: 8, y: 20, w: 52, h: 29, c: "black" }, { x: 9, y: 21, w: 50, h: 27, c: "stone" }, { x: 9, y: 21, w: 50, h: 1, c: "silver" },
        { x: 12, y: 23, w: 44, h: 8, c: "cream" }, { x: 12, y: 29, w: 44, h: 1, c: "orange" }, { x: 12, y: 30, w: 44, h: 1, c: "red" },
        { x: 15, y: 32, w: 38, h: 14, c: "black" }, { x: 16, y: 33, w: 36, h: 12, c: "night" },
        { x: 10, y: 22, c: "black" }, { x: 57, y: 22, c: "black" }, { x: 10, y: 46, c: "black" }, { x: 57, y: 46, c: "black" },
        // LCD and counter
        { x: 65, y: 18, w: 46, h: 24, c: "black" }, { x: 66, y: 19, w: 44, h: 22, c: "stone" }, { x: 68, y: 21, w: 40, h: 18, c: "black" },
        { x: 65, y: 44, w: 46, h: 8, c: "black" }, { x: 66, y: 45, w: 44, h: 6, c: "silver" },
        ...[0, 1, 2, 3].map((i) => ({ x: 78 + i * 8, y: 45, w: 7, h: 6, c: "black" })),
        // polygraph: pips, slot and slip
        { x: 45, y: 52, w: 5, h: 5, c: "black" }, { x: 46, y: 53, w: 3, h: 3, c: "lime" },
        { x: 50, y: 52, w: 5, h: 5, c: "black" }, { x: 51, y: 53, w: 3, h: 3, c: "lime" },
        { x: 5, y: 56, w: 72, h: 1, c: "black" }, { x: 5, y: 57, w: 72, h: 1, c: "stone" },
        { x: 7, y: 58, w: 68, h: 18, c: "cream" }, { x: 7, y: 58, w: 1, h: 18, c: "silver" }, { x: 74, y: 58, w: 1, h: 18, c: "silver" },
        // sticker
        { x: 4, y: 77, w: 42, h: 9, c: "black" }, { x: 5, y: 78, w: 40, h: 7, c: "orange" }, { x: 44, y: 78, c: "cream" },
      ])}
      {rects(grille)}
      {rects(glare)}
    </svg>
  );
});

function Keys({ pressed }: { pressed: KeyId }) {
  const cells: Cell[] = [];
  KEYS.forEach((k, i) => {
    const x = keyX(i);
    const down = k.id === pressed;
    const top = down ? 2 : 0;
    const face = k.id === "rec" ? "red" : down ? "lav" : "silver";
    cells.push({ x, y: top, w: 14, h: 10 - top, c: "black" }, { x: x + 1, y: top + 1, w: 12, h: 8 - top, c: face });
    cells.push({ x: x + 1, y: top + 1, w: 12, h: 1, c: down ? "stone" : "cream" });
    if (!down) cells.push({ x: x + 1, y: 8, w: 12, h: 1, c: "stone" });
    const icon = ICONS[k.id];
    const ix = x + 1 + Math.floor((12 - icon[0].length) / 2);
    icon.forEach((row, y) => [...row].forEach((ch, dx) => ch === "#" && cells.push({ x: ix + dx, y: top + 2 + y, c: k.id === "rec" ? "cream" : "black" })));
  });
  return <svg className="rec__layer" width={W * U} height={H * U} viewBox={`0 0 ${W} ${H}`} shapeRendering="crispEdges" aria-hidden="true">{rects(cells)}</svg>;
}

/** The reels: a tape pack sized by how much tape each holds, and a hub whose
 *  three spokes are drawn in three frames so it turns in steps. */
const Reels = memo(function Reels({ packL, packR }: { packL: number; packR: number }) {
  const reel = (cx: number, cy: number, pack: number) => (
    <g>
      {rects([...disc(cx, cy, pack, "brown"), ...disc(cx, cy, 2.2, "cream"), { x: cx, y: cy, c: "black" }])}
      {[90, 130, 170].map((deg, f) => (
        <g key={f} className={`rec__frame rec__frame--${f}`}>
          {rects([0, 120, 240].flatMap((off) => {
            const a = ((deg + off) * Math.PI) / 180;
            return [1, 2].map((d) => ({ x: Math.round(cx + d * Math.cos(a)), y: Math.round(cy - d * Math.sin(a)), c: "stone" }));
          }))}
        </g>
      ))}
    </g>
  );
  return (
    <svg className="rec__layer" width={W * U} height={H * U} viewBox={`0 0 ${W} ${H}`} shapeRendering="crispEdges" aria-hidden="true">
      {reel(23, 38, packL)}
      {reel(45, 38, packR)}
      {rects([{ x: 23, y: 43, w: 22, h: 1, c: "brown" }])}
      {rects([0, 1, 2, 3, 4, 5].map((k) => ({ x: 8 + k, y: 26 - k, c: "lav" })))}
    </svg>
  );
});

const Knob = memo(function Knob({ speed }: { speed: 1 | 2 | 4 }) {
  const cx = 95, cy = 66;
  const a = ({ 1: 135, 2: 90, 4: 45 }[speed] * Math.PI) / 180;
  const shine: Cell[] = [];
  for (let y = cy - 8; y <= cy; y++)
    for (let x = cx - 8; x <= cx; x++)
      if ((x - cx) ** 2 + (y - cy) ** 2 <= 60 && x - cx + (y - cy) < -7) shine.push({ x, y, c: "silver" });
  const line = [2, 3, 4, 5, 6].map((d) => ({ x: Math.round(cx + d * Math.cos(a)), y: Math.round(cy - d * Math.sin(a)), c: "cream" }));
  return (
    <svg className="rec__layer" width={W * U} height={H * U} viewBox={`0 0 ${W} ${H}`} shapeRendering="crispEdges" aria-hidden="true">
      {rects([...disc(cx, cy, 9, "black"), ...disc(cx, cy, 8, "stone"), ...shine, ...line])}
    </svg>
  );
});

function noise(t: number): number {
  const x = Math.sin(t * 12.9898) * 43758.5453;
  return x - Math.floor(x);
}

const NEEDLE = 70; // grid column the needle writes at
const SPAN = NEEDLE - 7; // minutes of trace visible on the slip

/** The polygraph trace for the minutes up to the playhead, newest at the needle. */
function Trace({ now }: { now: number }) {
  const ys: number[] = [];
  for (let i = 0; i <= SPAN; i++) {
    const t = now - SPAN + i;
    const lost = t >= 0 && t < unaccountedByTick.length ? unaccountedByTick[t] : 0;
    ys.push(t < 0 ? 9 : Math.max(1, Math.min(16, 9 + Math.round((noise(t) * 2 - 1) * (1 + lost)))));
  }
  const cells: Cell[] = [];
  ys.forEach((y, i) => {
    const prev = ys[i - 1] ?? y;
    for (let yy = Math.min(prev, y); yy <= Math.max(prev, y); yy++) cells.push({ x: 7 + i, y: 58 + yy, c: "night" });
  });
  return (
    <>
      <svg className="rec__layer" width={W * U} height={H * U} viewBox={`0 0 ${W} ${H}`} shapeRendering="crispEdges" aria-hidden="true">
        {rects(cells)}
      </svg>
      <div className="rec__needle" style={{ left: NEEDLE * U, height: (58 + ys[ys.length - 1] - 49) * U }}><i /></div>
    </>
  );
}

const BEEPS: Partial<Record<KeyId, string>> = {
  rec: "ALREADY RECORDING. IT NEVER STOPS.",
  rew: "REWIND = REPLAY. SAME TAPE, SAME EVENING.",
  ff: "FAST FORWARD. 23:00, ALL CLAIMS DRAWN.",
};

const KONAMI = ["ArrowUp", "ArrowUp", "ArrowDown", "ArrowDown", "ArrowLeft", "ArrowRight", "ArrowLeft", "ArrowRight", "b", "a"];

interface Props {
  replay: Replay;
  marquee: string;
  onParty: () => void;
}

export function PocketRecorder({ replay, marquee, onParty }: Props) {
  const [message, setMessage] = useState<string | null>(null);
  const timer = useRef<number>();
  const now = Math.floor(replay.tick);
  const p = replay.tick / TICK_MAX;
  const rx = caseFile.claims.some((c) => now - c.t0 >= 0 && now - c.t0 < 2);

  const say = (text: string) => {
    setMessage(text);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setMessage(null), 4000);
  };
  const press = (id: KeyId) => {
    if (id === "play") replay.play();
    if (id === "pause") replay.pause();
    if (id === "stop") {
      replay.pause();
      say(`STOPPED AT ${tickToClock(now)}.`);
    }
    if (id === "rew") replay.rewind();
    if (id === "ff") replay.toEnd();
    const beep = BEEPS[id];
    if (beep) say(beep);
  };

  // Up up down down left right left right B A. The audit takes no shortcuts,
  // so the code only makes the house dance; it can never reveal anything.
  useEffect(() => {
    let at = 0;
    const onKey = (e: KeyboardEvent) => {
      at = e.key === KONAMI[at] ? at + 1 : e.key === KONAMI[0] ? 1 : 0;
      if (at < KONAMI.length) return;
      at = 0;
      onParty();
      say("CHEATS OFF. THE AUDIT ONLY TAKES EVIDENCE.");
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onParty]);

  return (
    <section className={`rec${replay.playing ? "" : " rec--paused"}`} aria-label="Pocket recorder" style={{ ["--spd" as string]: replay.speed }}>
      <Chassis />
      <Keys pressed={replay.playing ? "play" : "pause"} />
      <Reels packL={3 + Math.round((1 - p) * 2.6)} packR={3 + Math.round(p * 2.6)} />
      <Knob speed={replay.speed} />
      <svg className="rec__layer" width={W * U} height={H * U} viewBox={`0 0 ${W} ${H}`} shapeRendering="crispEdges" aria-hidden="true">
        <g className="rec__lamp-rec">{rects([{ x: 88, y: 10, w: 3, h: 3, c: "red" }, { x: 88, y: 10, c: "cream" }])}</g>
        {rx && rects([{ x: 100, y: 10, w: 3, h: 3, c: "lime" }, { x: 100, y: 10, c: "cream" }, { x: 106, y: 0, w: 3, h: 2, c: "lime" }])}
      </svg>
      <Trace now={now} />

      <div className="rec__brand"><b>ALIBI</b><span>POCKET RECORDER AR-{caseFile.meta.seed}</span></div>
      <span className="rec__lbl" style={{ left: 92 * U, top: 10 * U }}>REC</span>
      <span className="rec__lbl" style={{ left: 104 * U + 2, top: 10 * U }}>RX</span>
      <div className="rec__tape"><b>SEED {caseFile.meta.seed}</b><span>SAME TAPE, SAME EVENING</span></div>
      {/* <output> is a status region by nature, so no role is put on a div. */}
      <output className="rec__lcd" aria-live="polite">
        <span className="rec__clock">{tickToClock(now)}</span>
        <span className="rec__mode">{replay.playing ? "PLAY" : now >= TICK_MAX ? "END" : "PAUSE"} {replay.speed}X</span>
        <span className="rec__scroll"><span key={message ?? marquee}>{message ?? marquee}</span></span>
      </output>
      <span className="rec__lbl" style={{ left: 67 * U, top: 46 * U + 2 }}>CNT</span>
      {[...String(now).padStart(4, "0")].map((d, i) => (
        <span key={i} className="rec__digit" style={{ left: (78 + i * 8) * U }}>{d}</span>
      ))}
      <span className="rec__lbl" style={{ left: 5 * U, top: 52 * U + 2 }}>POLYGRAPH</span>
      <span className="rec__lbl" style={{ left: 56 * U, top: 52 * U + 2 }}>2 LEFT</span>
      {(["1X", "2X", "4X"] as const).map((t, i) => (
        <span key={t} className={`rec__lbl${`${replay.speed}X` === t ? " rec__lbl--on" : ""}`} style={{ left: [84, 93, 103][i] * U, top: [55, 52, 55][i] * U }}>{t}</span>
      ))}
      <span className="rec__lbl" style={{ left: 89 * U, top: 76 * U + 2 }}>SPEED</span>
      <span className="rec__sticker">HEARD != SEEN</span>

      {KEYS.map((k, i) => (
        <button key={k.id} type="button" className="rec__key" style={{ left: keyX(i) * U }} aria-label={k.label} onClick={() => press(k.id)} />
      ))}
      <button type="button" className="rec__knob" aria-label={`Speed, ${replay.speed}x`} onClick={replay.cycleSpeed} />
    </section>
  );
}
