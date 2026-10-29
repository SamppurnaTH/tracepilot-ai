"use client";

import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { recordingFallback, streamRun } from "./api";
import { initialState, reduce, type Recording, type RunEvent, type RunState } from "./run";

type Action = { type: "event"; event: RunEvent } | { type: "events"; events: RunEvent[] } | { type: "reset" };

function runReducer(state: RunState, action: Action): RunState {
  if (action.type === "reset") return initialState;
  if (action.type === "events") return action.events.reduce(reduce, state);
  return reduce(state, action.event);
}

export const SPEEDS = [4, 10, 25];
const MAX_GAP_MS = 1400;

/** One investigation's state, fed by a recording (instantly or replayed step by step) or by a live event stream. */
export function useRun() {
  const [state, dispatch] = useReducer(runReducer, initialState);
  const [queue, setQueue] = useState<RunEvent[]>([]);
  const [cursor, setCursor] = useState(0);
  const [speed, setSpeed] = useState(SPEEDS[1]);
  const [mode, setMode] = useState<"replay" | "live" | null>(null);
  const [startedAt, setStartedAt] = useState<number | undefined>();
  const close = useRef<(() => void) | null>(null);

  const reset = useCallback(() => {
    close.current?.();
    close.current = null;
    dispatch({ type: "reset" });
    setQueue([]);
    setCursor(0);
  }, []);

  const show = useCallback(
    (rec: Recording, animate: boolean) => {
      reset();
      const events = rec.events.filter((e) => e.type !== "tool_result" && e.type !== "message");
      setMode("replay");
      setStartedAt(rec.started_at);
      if (animate) setQueue(events);
      else dispatch({ type: "events", events });
    },
    [reset],
  );

  const follow = useCallback(
    (runId: string, started?: number) => {
      reset();
      setMode("live");
      setStartedAt(started ?? Date.now() / 1000);
      close.current = streamRun(
        runId,
        (event) => dispatch({ type: "event", event }),
        () => (close.current = null),
        (error) => dispatch({ type: "event", event: { seq: Number.MAX_SAFE_INTEGER, type: "error", recordingFallback: recordingFallback(error) !== null, message: `Live connection interrupted: ${error instanceof Error ? error.message : "unavailable"}. The server may still be running; check My runs before starting another investigation.` } }),
      );
    },
    [reset],
  );

  const skip = useCallback(() => {
    dispatch({ type: "events", events: queue.slice(cursor) });
    setCursor(queue.length);
  }, [queue, cursor]);

  // Play the next recorded event after a gap compressed from the real timing.
  useEffect(() => {
    if (mode !== "replay" || cursor >= queue.length) return;
    const prev = queue[cursor - 1]?.t ?? 0;
    const next = queue[cursor].t ?? prev;
    const delay = Math.min(Math.max(((next - prev) * 1000) / speed, 40), MAX_GAP_MS);
    const timer = setTimeout(() => {
      dispatch({ type: "event", event: queue[cursor] });
      setCursor((c) => c + 1);
    }, delay);
    return () => clearTimeout(timer);
  }, [mode, cursor, queue, speed]);

  useEffect(() => () => close.current?.(), []);

  return { state, mode, startedAt, speed, setSpeed, replaying: mode === "replay" && cursor < queue.length, show, follow, skip, reset };
}
