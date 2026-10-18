/** The live case: one read of the board, and the stream that says to read again.
 *
 *  The board was built against a dumped fixture. This module fetches the same
 *  shape from the orchestrator instead, so nothing downstream of `lib/case.ts`
 *  knows which one it got.
 *
 *  **What the live payload cannot carry.** A chain's hops name facts inside a
 *  private mind, so no route serves them (the project rules, rule 6) and the
 *  live `chains` arrive with `hops: []`. `trailOf` falls back to the claim's
 *  own public `relayed_from` for the cited speaker. Trails also appear only
 *  where the detective spent a polygraph, because that is the only thing that
 *  writes a chain conclusion into a case graph — the budget, made visible.
 */
import type { CaseFixture } from "./case";

/** Events worth redrawing on. EventSource has no wildcard, so the types the
 *  orchestrator emits are named here; anything else is ignored rather than
 *  silently redrawing the board on every heartbeat. */
export const STREAM_EVENTS = [
  "case.generating",
  "case.generated",
  "case.audited",
  "case.ready",
  "investigation.started",
  "turn.taken",
  "tool.called",
  "tool.result",
  "tool.refused",
  "accusation",
  "investigation.finished",
  "investigation.failed",
  "stream.closed",
  "stream.timeout",
] as const;

export type StreamEventType = (typeof STREAM_EVENTS)[number];

export interface StreamEvent {
  seq: number;
  type: string;
  at: string | null;
  data: Record<string, unknown>;
}

/** Events after which the case graph may hold something new to draw. A turn
 *  the detective spent thinking changes nothing on the board. */
const REDRAW_AFTER = new Set<string>([
  "case.audited",
  "case.ready",
  "tool.result",
  "accusation",
  "investigation.finished",
]);

export const shouldRedraw = (type: string) => REDRAW_AFTER.has(type);

export async function fetchBoard(seed: number): Promise<CaseFixture> {
  const res = await fetch(`/api/cases/${seed}/board`);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`GET /cases/${seed}/board failed: ${res.status} ${detail}`);
  }
  return (await res.json()) as CaseFixture;
}

export async function openCase(seed: number, pathologies = true): Promise<void> {
  const res = await fetch("/api/cases", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ seed, pathologies }),
  });
  // 409 means the case is already open, which is a fine state to attach to.
  if (!res.ok && res.status !== 409) {
    throw new Error(`POST /cases failed: ${res.status} ${await res.text()}`);
  }
}

export async function investigate(seed: number): Promise<void> {
  const res = await fetch(`/api/cases/${seed}/investigate`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({}),
  });
  if (!res.ok && res.status !== 409) {
    throw new Error(`POST /cases/${seed}/investigate failed: ${res.status} ${await res.text()}`);
  }
}

/** Subscribe to a case's event log from the beginning. Returns a closer. */
export function openStream(
  seed: number,
  onEvent: (e: StreamEvent) => void,
  cursor = 0,
): () => void {
  const source = new EventSource(`/api/cases/${seed}/events?cursor=${cursor}`);
  const handler = (e: MessageEvent) => {
    try {
      onEvent(JSON.parse(e.data) as StreamEvent);
    } catch {
      // A malformed frame is the server's problem to fix, not something to
      // redraw the board on. It is dropped loudly in the console, not hidden.
      console.error("unparseable event frame", e.data);
    }
  };
  for (const type of STREAM_EVENTS) source.addEventListener(type, handler as EventListener);
  source.onerror = () => source.close();
  return () => source.close();
}
