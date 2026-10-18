/** A suspect as pixel art: 10x14 on a whole-number grid, crisp edges.
 *
 *  The coat colour identifies a suspect and carries no verdict (brief 3). How
 *  firmly they stand is the stance: a solid sprite, a ghost drawn as a checker
 *  dither in two phases so a live house can flicker it, a hollow outline for a
 *  claim with nothing behind it, or a flat silhouette in the void.
 */
import { memo } from "react";

export type SpriteMode = "solid" | "ghost" | "hollow" | "unknown";

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

// Seven looks, one per suspect in case-file order. Palette colours only.
const LOOKS = [
  { H: "var(--brown)", C: "var(--sky)", D: "var(--night)" },
  { H: "var(--black)", C: "var(--lime)", D: "var(--forest)" },
  { H: "var(--yellow)", C: "var(--lav)", D: "var(--stone)" },
  { H: "var(--black)", C: "var(--plum)", D: "var(--pink)" },
  { H: "var(--pink)", C: "var(--peach)", D: "var(--brown)" },
  { H: "var(--stone)", C: "var(--orange)", D: "var(--brown)" },
  { H: "var(--silver)", C: "var(--forest)", D: "var(--lime)" },
];
const BASE: Record<string, string> = {
  S: "var(--peach)",
  K: "var(--black)",
  M: "var(--plum)",
  L: "var(--night)",
  B: "var(--black)",
};

const filled = (x: number, y: number) => BODY[y]?.[x] !== undefined && BODY[y][x] !== ".";

interface Props {
  look: number;
  mode?: SpriteMode;
  scale?: number;
}

export const Sprite = memo(function Sprite({ look, mode = "solid", scale = 3 }: Props) {
  const pal = { ...BASE, ...LOOKS[look % LOOKS.length] } as Record<string, string>;
  const cells: { x: number; y: number; fill: string; phase: number }[] = [];
  BODY.forEach((row, y) =>
    [...row].forEach((ch, x) => {
      if (ch === ".") return;
      if (mode === "hollow") {
        const edge = !filled(x - 1, y) || !filled(x + 1, y) || !filled(x, y - 1) || !filled(x, y + 1);
        if (edge) cells.push({ x, y, fill: "var(--stone)", phase: 0 });
        return;
      }
      const fill = mode === "ghost" ? "var(--cream)" : mode === "unknown" ? "var(--stone)" : pal[ch];
      cells.push({ x, y, fill, phase: (x + y) % 2 });
    }),
  );
  const rect = (c: (typeof cells)[number]) => (
    // Fill through `style`, so the palette tokens resolve; a presentation
    // attribute would not reliably take var().
    <rect key={`${c.x}-${c.y}`} x={c.x} y={c.y} width={1} height={1} style={{ fill: c.fill }} />
  );
  return (
    <svg
      className={`sprite sprite--${mode}`}
      width={10 * scale}
      height={14 * scale}
      viewBox="0 0 10 14"
      shapeRendering="crispEdges"
      aria-hidden="true"
    >
      {mode === "ghost" ? (
        <>
          <g className="dither dither--a">{cells.filter((c) => c.phase === 0).map(rect)}</g>
          <g className="dither dither--b">{cells.filter((c) => c.phase === 1).map(rect)}</g>
        </>
      ) : (
        cells.map(rect)
      )}
    </svg>
  );
});

const LENS = ["0111000", "1000100", "1000100", "1000100", "0111100", "0000010", "0000001"];

/** The magnifier that rides the playhead. */
export function Lens({ scale = 3 }: { scale?: number }) {
  return (
    <svg className="lens" width={7 * scale} height={7 * scale} viewBox="0 0 7 7" shapeRendering="crispEdges" aria-hidden="true">
      {LENS.flatMap((row, y) =>
        [...row].map((c, x) => (c === "1" ? <rect key={`${x}-${y}`} x={x} y={y} width={1} height={1} /> : null)),
      )}
    </svg>
  );
}

/** A pixel arrow pointing right, for trails. */
export function Arrow() {
  return (
    <svg className="arrow" viewBox="0 0 12 7" width={24} height={14} shapeRendering="crispEdges" aria-hidden="true">
      <path d="M8 0h1v1H8zM9 1h1v1H9zM10 2h1v1h-1zM0 3h12v1H0zM10 4h1v1h-1zM9 5h1v1H9zM8 6h1v1H8z" />
    </svg>
  );
}

/** The RPG cursor that points at the selected suspect. */
export function Cursor() {
  return (
    <svg className="cursor" viewBox="0 0 7 4" width={14} height={8} shapeRendering="crispEdges" aria-hidden="true">
      <path d="M0 0h7v1H0zM1 1h5v1H1zM2 2h3v1H2zM3 3h1v1H3z" />
    </svg>
  );
}
