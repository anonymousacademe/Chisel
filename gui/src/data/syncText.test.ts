import { describe, expect, it } from "vitest";
import type { SyncInfo } from "./types";
import { syncTip } from "./syncText";

const repo = (o: Partial<Extract<SyncInfo, { repo: true }>>): SyncInfo => ({
  repo: true, canInit: false, state: "synced", label: "Synced", changes: 0, scenes: 0, ahead: 0, behind: 0,
  branch: "main", remote: null, canPush: false, remoteUrl: "", toplevel: "/p", defaultMessage: "", ...o,
});

describe("syncTip", () => {
  it("explains every state and what a click does", () => {
    expect(syncTip({ repo: false, canInit: true, label: "Sync" })).toContain("turn this folder into a git repository");
    expect(syncTip(repo({ state: "changes", changes: 1 }))).toBe("1 uncommitted change. Click to commit them.");
    expect(syncTip(repo({ state: "changes", changes: 3 }))).toContain("3 uncommitted changes");
    expect(syncTip(repo({ state: "ahead", ahead: 2, remote: "origin" }))).toBe("2 commits not pushed to origin. Click to push.");
    expect(syncTip(repo({ remote: "origin" }))).toBe("Committed and pushed to origin.");
  });
  it("does not claim a push when there is no remote", () => {
    expect(syncTip(repo({}))).toContain("no remote");
  });
});
