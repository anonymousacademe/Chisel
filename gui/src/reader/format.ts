import type { ReadUtterance } from "./types";

/** "about 4 min" / "under a minute": the estimated time left from utterance *index* on, at *rate*. */
export function timeLeft(utterances: ReadUtterance[], index: number, rate: number): string {
  const seconds = utterances.slice(Math.max(index, 0)).reduce((n, u) => n + u.seconds, 0) / Math.max(rate, 0.1);
  if (seconds < 45) return "under a minute";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `about ${minutes} min`;
  const h = Math.floor(minutes / 60), m = minutes % 60;
  return m ? `about ${h} h ${m} min` : `about ${h} h`;
}

/** "Reading 3 of 24" while playing or paused, "24 passages" before. */
export function progressLabel(status: string, index: number, total: number): string {
  if (!total) return "Nothing to read";
  if (status === "playing" || status === "paused") return `${status === "paused" ? "Paused at" : "Reading"} ${index + 1} of ${total}`;
  if (status === "done") return "Finished";
  return `${total} passage${total === 1 ? "" : "s"}`;
}
