import type { SyncInfo } from "./types";

/** The tooltip of the status-bar sync item (what it means, what a click does). */
export function syncTip(s: SyncInfo): string {
  if (!s.repo) return s.canInit ? "Not under git. Click to turn this folder into a git repository." : "Not under git";
  if (s.state === "changes") return `${s.changes} uncommitted change${s.changes === 1 ? "" : "s"}. Click to commit them.`;
  if (s.state === "ahead") return `${s.ahead} commit${s.ahead === 1 ? "" : "s"} not pushed to ${s.remote}. Click to push.`;
  return s.remote ? `Committed and pushed to ${s.remote}.` : "Committed (no remote is configured, so nothing is pushed).";
}
