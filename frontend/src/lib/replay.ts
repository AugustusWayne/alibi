/** The replay clock: the only source of the playhead (brief 10).
 *
 *  The pocket recorder drives it; SSE will later. Linear and continuous: the
 *  playhead advances by wall time times speed, so a hidden tab that resumes
 *  catches up rather than drifting.
 *
 *  `prefers-reduced-motion: reduce` pins the replay to 23:00, paused: the
 *  strip is simply already written. `?t=112` in the URL opens the replay
 *  paused at that minute, so a demo can open on a moment.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { TICK_MAX, TICK_MIN } from "./time";

const TICKS_PER_SECOND = 10;

export interface Replay {
  tick: number;
  playing: boolean;
  speed: 1 | 2 | 4;
  play: () => void;
  pause: () => void;
  toggle: () => void;
  rewind: () => void;
  toEnd: () => void;
  cycleSpeed: () => void;
}

const reducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** The minute named by `?t=`, if it is a whole minute inside the case window. */
function startAt(): number | null {
  if (typeof window === "undefined") return null;
  const raw = new URLSearchParams(window.location.search).get("t");
  const t = raw === null ? NaN : Number(raw);
  return Number.isInteger(t) && t >= TICK_MIN && t <= TICK_MAX ? t : null;
}

export function useReplay(): Replay {
  const reduced = reducedMotion();
  const from = startAt();
  const [tick, setTick] = useState(reduced ? TICK_MAX : (from ?? TICK_MIN));
  const [playing, setPlaying] = useState(!reduced && from === null);
  const [speed, setSpeed] = useState<1 | 2 | 4>(1);
  const tickRef = useRef(tick);
  tickRef.current = tick;

  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    let last = performance.now();
    const step = (now: number) => {
      const next = Math.min(TICK_MAX, tickRef.current + ((now - last) / 1000) * TICKS_PER_SECOND * speed);
      last = now;
      setTick(next);
      if (next >= TICK_MAX) {
        setPlaying(false);
        return;
      }
      frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [playing, speed]);

  const play = useCallback(() => {
    if (tickRef.current >= TICK_MAX) setTick(TICK_MIN);
    setPlaying(true);
  }, []);
  const pause = useCallback(() => setPlaying(false), []);
  const toggle = useCallback(() => (playing ? setPlaying(false) : play()), [playing, play]);
  const rewind = useCallback(() => setTick(TICK_MIN), []);
  const toEnd = useCallback(() => {
    setTick(TICK_MAX);
    setPlaying(false);
  }, []);
  const cycleSpeed = useCallback(() => setSpeed((s) => (s === 1 ? 2 : s === 2 ? 4 : 1)), []);

  return { tick, playing, speed, play, pause, toggle, rewind, toEnd, cycleSpeed };
}
