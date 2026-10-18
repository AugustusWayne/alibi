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
import { caseFile, claimOf, memoryLine, nameOf, walkOf } from "./lib/case";
import { useReplay } from "./lib/replay";
import { tickToClock } from "./lib/time";

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

  const marquee = claim
    ? `${nameOf(claim.speaker)} SAYS ${claim.subject === claim.speaker ? "" : `${nameOf(claim.subject)} IN THE `}${claim.place.toUpperCase()} ${tickToClock(claim.t0)}-${tickToClock(claim.t1)}. ${memoryLine(claim)}. ${claim.verdict}.`
    : `${caseFile.meta.claims} CLAIMS. ${caseFile.audit_summary.uncovered_minutes} MIN UNACCOUNTED. SELECT A CLAIM.`;

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
