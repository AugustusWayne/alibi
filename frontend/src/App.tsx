/** The case board (brief 6.1): the HUD, the house, the case log, the level
 *  strip and the pocket recorder. One screen at 1280x820.
 *
 *  Everything on it was computed by the audit engine and the referee and read
 *  out of the case graph. This component decides nothing about a claim.
 */
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import { CaseLog } from "./components/CaseLog";
import { Hud, Window } from "./components/Frame";
import { House } from "./components/House";
import { Level } from "./components/Level";
import { PocketRecorder } from "./components/PocketRecorder";
import { caseFile, claimOf, memoryLine, nameOf, setCaseFile, walkOf } from "./lib/case";
import { fetchBoard, investigate, openCase, openStream, shouldRedraw } from "./lib/live";
import { useReplay } from "./lib/replay";
import { tickToClock } from "./lib/time";

/**
 * Live mode, opted into with `?seed=7777`. Without it the board shows the
 * dumped fixture, which is what makes it work with no server at all.
 *
 * `?investigate=1` also starts the detective, so the board can be opened on
 * an empty case and watched filling in. The orchestrator runs the loop on a
 * worker thread and publishes a turn at a time; this only reads.
 */
function liveSeed(): number | null {
  const raw = new URLSearchParams(window.location.search).get("seed");
  if (raw === null) return null;
  const seed = Number.parseInt(raw, 10);
  return Number.isFinite(seed) ? seed : null;
}

/**
 * Attach to a live case: open it if it is not open, read the whole board
 * once, then redraw on the events that can change what is drawn.
 *
 * The stream says *when* to read, never *what* — every number on the board
 * still comes from the one board read, so a half-applied update cannot show
 * a claim beside a tally that does not count it.
 */
function useLiveCase(seed: number | null) {
  const [state, setState] = useState<"off" | "loading" | "ready" | "failed">(
    seed === null ? "off" : "loading",
  );
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  const [last, setLast] = useState<string | null>(null);

  useEffect(() => {
    if (seed === null) return;
    let live = true;
    let closeStream: (() => void) | null = null;

    const redraw = async () => {
      const board = await fetchBoard(seed);
      if (!live) return;
      setCaseFile(board);
      setVersion((v) => v + 1);
    };

    (async () => {
      try {
        await openCase(seed);
        await redraw();
        if (!live) return;
        setState("ready");
        if (new URLSearchParams(window.location.search).get("investigate") === "1") {
          await investigate(seed);
        }
        closeStream = openStream(seed, (e) => {
          setLast(e.type);
          if (shouldRedraw(e.type)) void redraw();
        });
      } catch (err) {
        if (!live) return;
        // Reported, not swallowed: a board that quietly showed the fixture
        // while claiming to be live would be the worst outcome here.
        setState("failed");
        setError(err instanceof Error ? err.message : String(err));
      }
    })();

    return () => {
      live = false;
      closeStream?.();
    };
  }, [seed]);

  return { state, error, version, last };
}

/**
 * Fit the whole board to the window (brief 10).
 *
 * The board is laid out at 1280x820 and never reflows: a broken map or time
 * axis is worse than one at another size. So the window scales the board as
 * one piece, uniformly, to whatever it gives — down on a small window, up on
 * a large one, until one side of the board meets one side of the window. It
 * is `zoom` rather than a transform because `zoom` takes the scaled size into
 * the layout, so the page can centre the board and needs no scrollbar for
 * space the board no longer occupies. The board's own size is read off the
 * element, so this holds whatever `base.css` says the board is.
 */
function useFitToWindow(board: React.RefObject<HTMLElement>) {
  useLayoutEffect(() => {
    const el = board.current;
    if (!el) return;
    // `innerWidth`/`innerHeight` include the scrollbar gutter, so the measure
    // does not change when a scrollbar appears or goes. Measuring the space
    // inside the scrollbars instead would oscillate: a fitted board needs no
    // scrollbar, no scrollbar means more space, more space means fit again.
    const fit = () => {
      const scale = Math.min(window.innerWidth / el.offsetWidth, window.innerHeight / el.offsetHeight);
      document.documentElement.style.setProperty("--fit", String(scale));
    };
    fit();
    // The observer, not the event, is what makes this reliable: a window
    // resized by the browser's own chrome, or by a tool driving it, does not
    // always fire `resize`, but the layout viewport always changes size.
    const watch = new ResizeObserver(fit);
    watch.observe(document.documentElement);
    window.addEventListener("resize", fit);
    return () => {
      watch.disconnect();
      window.removeEventListener("resize", fit);
    };
  }, [board]);
}

export function App() {
  const board = useRef<HTMLElement>(null);
  useFitToWindow(board);
  const [seed] = useState(liveSeed);
  const feed = useLiveCase(seed);
  const replay = useReplay();
  // `?claim=p4-c7` opens with that claim selected, if the case has it.
  const [selected, setSelected] = useState<string | null>(() =>
    claimOf(new URLSearchParams(window.location.search).get("claim"))?.id ?? null,
  );
  const [party, setParty] = useState(false);
  const claim = claimOf(selected);
  const walk = claim ? walkOf(claim) : null;
  const now = Math.floor(replay.tick);

  const onSelect = useCallback((id: string) => setSelected((prev) => (prev === id ? null : id)), []);
  const onParty = useCallback(() => {
    setParty(true);
    window.setTimeout(() => setParty(false), 4000);
  }, []);

  // Space plays and pauses, Esc clears the selection (brief 8). Space on a
  // focused control is that control's own press, so it is left alone.
  const { toggle } = replay;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSelected(null);
      const onControl = e.target instanceof HTMLElement && e.target.closest("button, input, a, textarea, select");
      if (e.key === " " && !onControl) {
        e.preventDefault();
        toggle();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [toggle]);

  const status =
    feed.state === "failed"
      ? `LIVE CASE ${seed} UNREACHABLE: ${feed.error}`
      : feed.state === "loading"
        ? `OPENING CASE ${seed}...`
        : feed.last
          ? `LIVE ${caseFile.meta.case_id} - ${feed.last.toUpperCase().replace(/[._]/g, " ")}`
          : null;

  const marquee = status
    ? status
    : claim
      ? `${nameOf(claim.speaker)} SAYS ${claim.subject === claim.speaker ? "" : `${nameOf(claim.subject)} IN THE `}${claim.place.toUpperCase()} ${tickToClock(claim.t0)}-${tickToClock(claim.t1)}. ${memoryLine(claim)}. ${claim.verdict}.`
      : `${caseFile.meta.claims} CLAIMS. ${caseFile.audit_summary.uncovered_minutes} MIN UNACCOUNTED. SELECT A CLAIM.`;

  // The board redraws whole when the live case advances: `version` is the
  // only thing tying a React render to a module-level case swap.
  void feed.version;

  return (
    <div className="page">
      <main ref={board} className={`board${party ? " party" : ""}`}>
        <Hud tick={replay.tick} />
        <Window title={`THE HOUSE AT ${tickToClock(now)}`} className="win--house">
          <House tick={now} selected={selected} walk={walk} onSelect={onSelect} />
        </Window>
        <Window title="CASE LOG" className="win--log">
          <CaseLog claim={claim} onSelect={onSelect} />
        </Window>
        <Window title="TIMELINE" className="win--level">
          <Level tick={replay.tick} selected={claim} onSelect={onSelect} />
        </Window>
        <PocketRecorder replay={replay} marquee={marquee} onParty={onParty} />
      </main>
    </div>
  );
}
