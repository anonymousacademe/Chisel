import type { SprintState } from "./types";

/** "+1,240" / "−35": a net word count with its sign. */
export function signedWords(n: number): string {
  const f = Math.abs(n).toLocaleString("en-US");
  return n < 0 ? `−${f}` : `+${f}`;
}

/** "Oct 1" from an ISO date (local calendar day, no time zone shifts). */
export function dayLabel(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

/** Bar heights (percent of the best day; a day with words is at least 4 so it shows). */
export function chartBars(chart: { date: string; words: number }[], target = 0): { date: string; words: number; height: number; met: boolean }[] {
  const top = Math.max(0, ...chart.map((c) => c.words));
  return chart.map((c) => ({
    ...c,
    height: c.words > 0 && top > 0 ? Math.max(4, Math.round((c.words / top) * 100)) : 0,
    met: target > 0 ? c.words >= target : c.words > 0,
  }));
}

/** "24:05" countdown text for a sprint (seconds left, rounded up to whole seconds). */
export function clock(seconds: number): string {
  const s = Math.max(0, Math.ceil(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** Seconds left in a sprint according to the browser clock (the server sent epoch seconds). */
export function remaining(sprint: Pick<SprintState, "endsAt">, nowMs: number): number {
  return Math.max(0, sprint.endsAt - nowMs / 1000);
}

/** "Sprint done: 25 minutes, +312 words." (or stopped). */
export function sprintNotice(minutes: number, words: number, cancelled: boolean): string {
  const w = Math.abs(words);
  return `${cancelled ? "Sprint stopped" : "Sprint done"}: ${minutes} minute${minutes === 1 ? "" : "s"}, ${words < 0 ? "−" : "+"}${w.toLocaleString("en-US")} word${w === 1 ? "" : "s"}.`;
}
