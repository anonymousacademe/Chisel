import { useEffect, useRef, useState } from "react";
import { remaining } from "../data/stats";
import type { Workspace } from "../data/types";

type Sprint = NonNullable<NonNullable<Workspace["status"]["stats"]>["sprint"]>;

/**
 * Focus-sprint clock (the countdown is client-side; the server keeps the start/end and counts the words).
 * Call it above any early return in App. `onDue` fires once per sprint, when its time is up.
 */
export function useSprintClock(sprint: Sprint | null, onDue: () => void) {
  const [nowMs, setNowMs] = useState(() => Date.now());
  const sprintStart = sprint ? sprint.startedAt : null;
  useEffect(() => {
    if (sprintStart === null) return;
    const t = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(t);
  }, [sprintStart]);   // one timer per sprint
  const ended = useRef(false);
  const due = !!sprint && remaining(sprint, nowMs) <= 0;
  useEffect(() => {
    if (!sprint) { ended.current = false; return; }
    if (due && !ended.current) { ended.current = true; onDue(); }
  });
  return { nowMs, setNowMs };
}
