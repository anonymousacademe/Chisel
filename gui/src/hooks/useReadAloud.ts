import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { api } from "../backend/api";
import type { DocumentPayload } from "../data/types";
import type { EditorHandle } from "../components/EditorPane";
import { loadPrefs, resolveCast, savePrefs } from "../reader/cast";
import { browserEngine } from "../reader/engine";
import { ReadSession, utteranceIndexAt, type SessionStatus } from "../reader/session";
import { DEFAULT_READ_OPTIONS, type ReadOptions, type ReadPlan, type VoiceInfo } from "../reader/types";

export interface ReaderState {
  open: boolean;
  busy: boolean;                      // the plan is being made
  plan: ReadPlan | null;
  status: SessionStatus;
  index: number;
  voices: VoiceInfo[];
  cast: Record<string, string>;       // voice role -> system voice id
  rate: number;
  options: ReadOptions;
  message: string;
}

const CLOSED: ReaderState = {
  open: false, busy: false, plan: null, status: "idle", index: 0, voices: [], cast: {}, rate: 1,
  options: DEFAULT_READ_OPTIONS, message: "",
};

/** Documents the reader can read (a scene, a character / place note, a notebook note). */
export const READABLE: readonly string[] = ["scene", "entity", "research"];

/**
 * Read aloud, desktop: the plan comes from Python (Api.read_plan), the window's own speech service speaks it,
 * and the utterance being read is highlighted in the editor. Sound only ever starts from a click (Play).
 */
export function useReadAloud(d: {
  editorRef: RefObject<EditorHandle | null>;
  docRef: RefObject<DocumentPayload | null>;
  projectKey: string;
  notify: (text: string, tone?: "info" | "error") => void;
}) {
  const engine = useMemo(() => browserEngine(), []);
  const prefs = useRef(loadPrefs());
  const [state, setState] = useState<ReaderState>(() => ({ ...CLOSED, rate: prefs.current.rate, options: prefs.current.options }));
  const session = useRef<ReadSession | null>(null);
  const planRef = useRef<ReadPlan | null>(null);
  const castRef = useRef<Record<string, string>>({});
  const rateRef = useRef(prefs.current.rate);
  const optionsRef = useRef(prefs.current.options);
  const stale = useRef(true);                // the text changed since the plan was made
  const stateRef = useRef(state);
  useEffect(() => { stateRef.current = state; });

  const clearHighlight = () => d.editorRef.current?.clearReading();
  const highlight = (index: number) => {
    const u = planRef.current?.utterances[index];
    if (u) d.editorRef.current?.showReading(u.start, u.end);
  };

  /** Make a plan from the editor's text now and a session to play it. */
  const load = useCallback(async (): Promise<boolean> => {
    const doc = d.docRef.current, ed = d.editorRef.current;
    if (!doc || !ed || !READABLE.includes(doc.kind)) {
      d.notify("Open a scene or a note to read aloud.");
      return false;
    }
    setState((s) => ({ ...s, busy: true, message: "" }));
    session.current?.stop();
    const r = await api.readPlan(doc.id, ed.getText(), optionsRef.current);
    if (!r.ok) {
      setState((s) => ({ ...s, busy: false, open: false }));
      d.notify(r.error, "error");
      return false;
    }
    const voices = await engine.voices();
    const roles = r.voices.map((v) => v.voice);
    castRef.current = resolveCast(prefs.current.casts[d.projectKey], roles, voices);
    planRef.current = r;
    stale.current = false;
    session.current = new ReadSession({
      utterances: r.utterances, engine, rate: () => rateRef.current, voiceFor: (role) => castRef.current[role],
      onChange: (status, index) => {
        setState((s) => ({ ...s, status, index }));
        if (status === "playing" || status === "paused") highlight(index); else clearHighlight();
      },
      onError: (message) => { setState((s) => ({ ...s, message })); d.notify(message, "error"); },
    });
    setState((s) => ({
      ...s, open: true, busy: false, plan: r, status: "idle", index: 0, voices, cast: castRef.current,
      message: voices.length ? (r.utterances.length ? "" : "There is nothing to read in this text.")
        : "This window offers no speech voices. Install one in your system's speech settings.",
    }));
    return true;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [engine, d.projectKey]);

  const open = useCallback(async () => { if (!stateRef.current.open) await load(); }, [load]);

  const close = useCallback(() => {
    session.current?.stop();
    engine.cancel();
    clearHighlight();
    session.current = null;
    planRef.current = null;
    stale.current = true;
    setState((s) => ({ ...CLOSED, rate: s.rate, options: s.options }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [engine]);

  /** Play from the cursor (or the start). The first click makes the plan, if there is none or the text changed. */
  const play = useCallback(async (from: "cursor" | "start" = "cursor") => {
    const ready = session.current && !stale.current ? true : await load();
    if (!ready || !session.current || !planRef.current) return;
    const ed = d.editorRef.current;
    const start = from === "cursor" && ed ? utteranceIndexAt(planRef.current.utterances, ed.selection().from) : 0;
    session.current.play(start);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load]);

  const toggle = useCallback(() => {
    const s = session.current;
    if (!s || stale.current) return void play("cursor");
    if (s.status === "playing") s.pause();
    else if (s.status === "paused") s.resume();
    else void play("cursor");
  }, [play]);

  const persist = () => savePrefs(prefs.current);

  const setRate = useCallback((rate: number) => {
    rateRef.current = rate; prefs.current.rate = rate; persist();
    setState((s) => ({ ...s, rate }));
  }, []);

  const setOption = useCallback((key: keyof ReadOptions, value: boolean) => {
    optionsRef.current = { ...optionsRef.current, [key]: value };
    prefs.current.options = optionsRef.current; persist();
    setState((s) => ({ ...s, options: optionsRef.current }));
    if (stateRef.current.open) void load();          // the list changes: make it again
  }, [load]);

  const setVoice = useCallback((role: string, id: string) => {
    castRef.current = { ...castRef.current, [role]: id };
    prefs.current.casts = { ...prefs.current.casts, [d.projectKey]: castRef.current }; persist();
    setState((s) => ({ ...s, cast: castRef.current }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [d.projectKey]);

  /** Say a short sample in a role's voice. */
  const hear = useCallback((role: string) => {
    session.current?.stop();
    engine.cancel();
    const what = role === "narrator" ? "the narrator" : role === "quote" ? "quoted speech" : role;
    engine.speak(`This is how ${what} sounds.`, { voice: castRef.current[role], rate: rateRef.current }, { onend: () => {}, onerror: () => {} });
  }, [engine]);

  /** The author typed: ranges in the plan no longer match the text, so stop and plan again on the next Play. */
  const noteEdited = useCallback(() => {
    if (!planRef.current || stale.current) return;
    stale.current = true;
    if (session.current && session.current.status !== "idle") session.current.stop();
    clearHighlight();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => () => { session.current?.stop(); engine.cancel(); }, [engine]);

  return {
    state, open, close, play, toggle, setRate, setOption, setVoice, hear, noteEdited,
    pause: () => session.current?.pause(), resume: () => session.current?.resume(),
    stop: () => session.current?.stop(), next: () => session.current?.next(), prev: () => session.current?.prev(),
    fromStart: () => void play("start"),
  };
}
