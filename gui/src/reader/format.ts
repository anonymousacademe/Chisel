import type { EndpointCost, ReadUtterance } from "./types";

/** "92 MB" */
export function megabytes(bytes: number): string {
  return `${Math.max(1, Math.round(bytes / 1_000_000))} MB`;
}

/** The speech server's cost as Python reports it (local: free; else the published price, when known), plus what
 * this session's clips cost (an estimate). */
export function costLine(c: EndpointCost, spent = 0): string {
  const so = spent > 0 ? ` This session: about $${spent.toFixed(spent < 0.1 ? 3 : 2)}.` : "";
  if (c.local) return "On this computer or your network: no cost.";
  if (c.pricePerMillion === null) return `Cloud service: check its price per character.${so}`;
  const hour = c.perHour ?? 0;
  return `Cloud service: about $${c.pricePerMillion} per million characters, about $${hour.toFixed(2)} per hour of listening (estimate; clips heard again are free).${so}`;
}

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
