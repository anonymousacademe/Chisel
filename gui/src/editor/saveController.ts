// Autosave state machine for the open document. Pure (no DOM, no React): the
// api and timers are injected so it can be unit-tested.

export type SaveState = "saved" | "dirty" | "saving" | "conflict" | "error";

export interface SaveResult {
  ok: boolean;
  error?: string;
  saved?: boolean;
  conflict?: boolean;
  mtime?: string;
  words?: number;
  snapshotAt?: string | null;
}

export interface SaveDeps {
  save(id: string, text: string, baseMtime: string | null, force: boolean): Promise<SaveResult>;
  onState(state: SaveState): void;
  onSaved?(result: SaveResult): void;
  onError?(message: string): void;
  delayMs?: number;
  setTimer?: (fn: () => void, ms: number) => unknown;
  clearTimer?: (handle: unknown) => void;
}

export class SaveController {
  state: SaveState = "saved";
  private id: string | null = null;
  private text = "";
  private mtime: string | null = null;
  private dirty = false;
  private timer: unknown = null;
  private inflight: Promise<void> | null = null;
  private readonly delay: number;
  private readonly setTimer: (fn: () => void, ms: number) => unknown;
  private readonly clearTimer: (h: unknown) => void;

  private readonly deps: SaveDeps;

  constructor(deps: SaveDeps) {
    this.deps = deps;
    this.delay = deps.delayMs ?? 1500;
    this.setTimer = deps.setTimer ?? ((fn, ms) => setTimeout(fn, ms));
    this.clearTimer = deps.clearTimer ?? ((h) => clearTimeout(h as ReturnType<typeof setTimeout>));
  }

  get documentId() { return this.id; }
  get baseMtime() { return this.mtime; }
  get isDirty() { return this.dirty; }

  private set(state: SaveState) {
    if (this.state !== state) { this.state = state; this.deps.onState(state); }
  }

  /** A document was (re)loaded from disk: it is clean at *mtime*. */
  open(id: string, text: string, mtime: string) {
    this.cancelTimer();
    this.id = id; this.text = text; this.mtime = mtime; this.dirty = false;
    this.set("saved");
  }

  /** Forget the document (deleted, or closed): nothing is saved afterwards. */
  detach() {
    this.cancelTimer();
    this.id = null; this.dirty = false;
    this.set("saved");
  }

  /** The buffer changed. */
  edit(text: string) {
    if (this.id === null || text === this.text) return;
    this.text = text;
    this.dirty = true;
    if (this.state === "conflict") return; // resolve the conflict first
    this.set("dirty");
    this.cancelTimer();
    this.timer = this.setTimer(() => { void this.flush(); }, this.delay);
  }

  private cancelTimer() {
    if (this.timer !== null) { this.clearTimer(this.timer); this.timer = null; }
  }

  /** Save now (ctrl+s, blur, before navigating). Resolves true when nothing is left unsaved. */
  async flush(): Promise<boolean> {
    this.cancelTimer();
    while (this.dirty && this.id !== null && this.state !== "conflict") {
      await this.saveOnce(false);
      if (this.state === "error") break;
    }
    return !this.dirty;
  }

  /** "Keep mine" after a conflict: overwrite the file with the buffer. */
  async keepMine(): Promise<boolean> {
    if (this.id === null) return true;
    this.set("dirty");
    await this.saveOnce(true);
    return this.flush();
  }

  private async saveOnce(force: boolean): Promise<void> {
    if (this.inflight) { await this.inflight; return; }
    const id = this.id!, text = this.text;
    this.set("saving");
    this.inflight = (async () => {
      let result: SaveResult;
      try {
        result = await this.deps.save(id, text, this.mtime, force);
      } catch (e) {
        result = { ok: false, error: String(e) };
      }
      if (this.id !== id) return; // switched or detached while saving
      if (!result.ok) {
        this.set("error");
        this.deps.onError?.(result.error ?? "Save failed");
      } else if (result.conflict) {
        if (result.mtime) this.mtime = result.mtime;
        this.set("conflict");
      } else {
        if (result.mtime) this.mtime = result.mtime;
        if (this.text === text) { this.dirty = false; this.set("saved"); }
        else this.set("dirty"); // edited while saving: loop saves again
        this.deps.onSaved?.(result);
      }
    })().finally(() => { this.inflight = null; });
    await this.inflight;
  }

  /** The file changed on disk while the buffer has unsaved edits. */
  markConflict() {
    if (this.dirty) { this.cancelTimer(); this.set("conflict"); }
  }
}
