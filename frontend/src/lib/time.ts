/** The case clock. Tick 0 is 18:00, the window is 300 minutes, and the axis is
 *  always the whole window so bars are comparable across channels (brief 5.1).
 */
export const TICK_MIN = 0;
export const TICK_MAX = 300;

/**
 * The one place time becomes a percentage. Every position, width, bracket and
 * pen offset on the board goes through this; no component does its own
 * arithmetic (brief 10).
 */
export function tickToPercent(tick: number): number {
  const span = TICK_MAX - TICK_MIN;
  return ((tick - TICK_MIN) / span) * 100;
}

/** A tick as a wall clock reading. */
export function tickToClock(tick: number): string {
  const hour = 18 + Math.floor(tick / 60);
  const minute = tick % 60;
  return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
}

/** `left` and `width` as percentage strings for a half-open span [t0, t1). */
export function spanStyle(t0: number, t1: number): { left: string; width: string } {
  const left = tickToPercent(t0);
  return { left: `${left}%`, width: `${tickToPercent(t1) - left}%` };
}
