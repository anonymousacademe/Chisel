import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { api } from "../backend/api";
import type { DocumentPayload } from "../data/types";
import type { EditorHandle } from "../components/EditorPane";
import { castKey, loadPrefs, resolveCast, savePrefs } from "../reader/cast";
import { clipEngine } from "../reader/clips";
import { browserEngine, type SpeechEngine } from "../reader/engine";
import { ReadSession, utteranceIndexAt, type SessionStatus } from "../reader/session";
import { unitText } from "../data/unitWords";
import {
  DEFAULT_READ_OPTIONS, type DownloadStatus, type EngineId, type OpenRouterModel, type ReadOptions, type ReadPlan, type SpeechInfo,
  type SpeechPrefs, type VoiceInfo,
} from "../reader/types";

export interface ReaderState {
  open: boolean;
  busy: boolean;                      // the plan is being made
  plan: ReadPlan | null;
  status: SessionStatus;
  index: number;
  voices: VoiceInfo[];
  cast: Record<string, string>;       // voice role -> voice id of the current engine
  rate: number;
  options: ReadOptions;
  message: string;
  engine: EngineId;
  speech: SpeechInfo | null;          // engines, the local voices, the speech server (python: chisel/speech/)
  download: DownloadStatus | null;    // the natural voices download, while it runs or after it failed
  spent: number;                      // estimated cost of cloud clips this session (USD)
  orModels: OpenRouterModel[] | null; // OpenRouter's speech models, once fetched
}

const CLOSED: ReaderState = {
  open: false, busy: false, plan: null, status: "idle", index: 0, voices: [], cast: {}, rate: 1,
  options: DEFAULT_READ_OPTIONS, message: "", engine: "browser", speech: null, download: null, spent: 0, orModels: null,
};

/** Documents the reader can read (a scene, a character / place note, a notebook note). */
export const READABLE: readonly string[] = ["scene", "entity", "research"];

/** What to tell the author when an engine has nothing to read with. */
function engineMessage(engine: EngineId, info: SpeechInfo | null, voices: VoiceInfo[]): string {
  if (engine === "kokoro" && info && !info.kokoro.engine) return info.kokoro.hint;
  if (engine === "kokoro" && info && !info.kokoro.installed) return "Download the natural voices first (Voices and options), or choose another engine.";
  if (engine === "openrouter" && info && !info.hasOpenRouterKey) return "OpenRouter voices use your OpenRouter key: add it in Settings > AI first.";
  if (!voices.length) {
    return engine === "browser" ? "This window offers no speech voices. Install one in your system's speech settings."
      : "No voices are available from this engine.";
  }
  return "";
}

/**
 * Read aloud, desktop: the plan comes from Python (Api.read_plan); the window's own speech service, or clips
 * Python renders (natural voices on this computer, or a speech server), speak it; the utterance being read is
 * highlighted in the editor. Sound only ever starts from a click (Play).
 */
export function useReadAloud(d: {
  editorRef: RefObject<EditorHandle | null>;
  docRef: RefObject<DocumentPayload | null>;
  projectKey: string;
  unit?: string;
  notify: (text: string, tone?: "info" | "error") => void;
}) {
  const prefs = useRef(loadPrefs());
  const [state, setState] = useState<ReaderState>(() => ({ ...CLOSED, rate: prefs.current.rate, options: prefs.current.options }));
  const session = useRef<ReadSession | null>(null);
  const planRef = useRef<ReadPlan | null>(null);
  const castRef = useRef<Record<string, string>>({});
  const rateRef = useRef(prefs.current.rate);
  const optionsRef = useRef(prefs.current.options);
  const engineId = useRef<EngineId>("browser");
  const infoRef = useRef<SpeechInfo | null>(null);
  const stale = useRef(true);                // the text changed since the plan was made
  const stateRef = useRef(state);
  useEffect(() => { stateRef.current = state; });

  const engines = useMemo<Record<EngineId, SpeechEngine>>(() => {
    const clips = (id: "kokoro" | "endpoint" | "openrouter") => clipEngine({
      voices: async () => {
        if (id === "kokoro") return (infoRef.current?.kokoro.installed ? infoRef.current.kokoro.voices : []).map((v) => ({ ...v, local: true }));
        const r = await api.speechVoices(id);
        if (!r.ok) throw new Error(r.error);
        return r.voices.map((v) => ({ ...v, local: false }));
      },
      clip: async (text, voice, rate) => {
        const r = await api.speechClip(text, voice, rate, id);
        if (!r.ok) throw new Error(r.error);
        if (r.cost) setState((s) => ({ ...s, spent: s.spent + (r.cost ?? 0) }));
        return r.dataUrl;
      },
    });
    return { browser: browserEngine(), kokoro: clips("kokoro"), endpoint: clips("endpoint"), openrouter: clips("openrouter") };
  }, []);
  const engine = () => engines[engineId.current];

  const clearHighlight = () => d.editorRef.current?.clearReading();
  const highlight = (index: number, last = index) => {
    const list = planRef.current?.utterances, u = list?.[index], v = list?.[last] ?? u;
    if (u && v) d.editorRef.current?.showReading(u.start, Math.max(u.end, v.end));
  };

  /** The engine settings from Python (no network); kept for the session. */
  const speechInfo = async (): Promise<SpeechInfo | null> => {
    if (infoRef.current) return infoRef.current;
    const r = await api.speechInfo();
    if (!r.ok) return null;
    infoRef.current = r;
    engineId.current = r.prefs.engine;
    setState((s) => ({ ...s, speech: r, engine: r.prefs.engine }));
    return r;
  };

  /** Make a plan from the editor's text now and a session to play it. */
  const load = useCallback(async (): Promise<boolean> => {
    const doc = d.docRef.current, ed = d.editorRef.current;
    if (!doc || !ed || !READABLE.includes(doc.kind)) {
      d.notify(unitText("Open a scene or a note to read aloud.", d.unit ?? "scene"));
      return false;
    }
    setState((s) => ({ ...s, busy: true, message: "" }));
    session.current?.stop();
    const info = await speechInfo();
    const r = await api.readPlan(doc.id, ed.getText(), optionsRef.current);
    if (!r.ok) {
      setState((s) => ({ ...s, busy: false, open: false }));
      d.notify(r.error, "error");
      return false;
    }
    const id = engineId.current;
    if (id === "kokoro" && info?.kokoro.installed) void api.speechWarm();     // load the model while the author looks
    let voices: VoiceInfo[] = [], voiceError = "";
    try { voices = await engine().voices(); } catch (e) { voiceError = e instanceof Error ? e.message : String(e); }
    const roles = r.voices.map((v) => v.voice);
    castRef.current = resolveCast(prefs.current.casts[castKey(d.projectKey, id)], roles, voices);
    planRef.current = r;
    stale.current = false;
    session.current = new ReadSession({
      utterances: r.utterances, engine: engines[id], rate: () => rateRef.current, voiceFor: (role) => castRef.current[role],
      onChange: (status, index, last) => {
        setState((s) => ({ ...s, status, index }));
        if (status === "playing" || status === "paused") highlight(index, last); else clearHighlight();
      },
      onError: (message) => { setState((s) => ({ ...s, message })); d.notify(message, "error"); },
    });
    const problem = engineMessage(id, info, voices) || voiceError;
    setState((s) => ({
      ...s, open: true, busy: false, plan: r, status: "idle", index: 0, voices, cast: castRef.current, engine: id,
      message: problem || (r.utterances.length ? "" : "There is nothing to read in this text."),
    }));
    return true;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [engines, d.projectKey]);

  // opening asks Python again: a key added in Settings since the last time counts
  const open = useCallback(async () => { if (!stateRef.current.open) { infoRef.current = null; await load(); } }, [load]);

  const close = useCallback(() => {
    session.current?.stop();
    for (const e of Object.values(engines)) e.cancel();
    clearHighlight();
    session.current = null;
    planRef.current = null;
    stale.current = true;
    setState((s) => ({ ...CLOSED, rate: s.rate, options: s.options, engine: s.engine, speech: s.speech, download: s.download, spent: s.spent, orModels: s.orModels }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [engines]);

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
    prefs.current.casts = { ...prefs.current.casts, [castKey(d.projectKey, engineId.current)]: castRef.current }; persist();
    setState((s) => ({ ...s, cast: castRef.current }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [d.projectKey]);

  /** Say a short sample in a role's voice. */
  const hear = useCallback((role: string) => {
    session.current?.stop();
    engine().cancel();
    const what = role === "narrator" ? "the narrator" : role === "quote" ? "quoted speech" : role;
    engine().speak(`This is how ${what} sounds.`, { voice: castRef.current[role], rate: rateRef.current }, {
      onend: () => {},
      onerror: (reason) => { if (/\s/.test(reason)) d.notify(reason, "error"); },
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [engines]);

  /** Save engine settings in Python; the open reader is made again with the new engine or server. */
  const changeSpeech = useCallback(async (change: Partial<SpeechPrefs>) => {
    session.current?.stop();
    engine().cancel();
    const r = await api.speechSet(change);
    if (!r.ok) { d.notify(r.error, "error"); return; }
    const info = infoRef.current ? { ...infoRef.current, prefs: r.prefs, endpoint: r.endpoint, openrouter: r.openrouter } : null;
    infoRef.current = info;
    engineId.current = r.prefs.engine;
    setState((s) => ({ ...s, speech: info, engine: r.prefs.engine }));
    if (stateRef.current.open) await load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load]);

  const setEngine = useCallback((id: EngineId) => changeSpeech({ engine: id }), [changeSpeech]);
  const setServer = useCallback((baseUrl: string, model: string) => changeSpeech({ baseUrl, model }), [changeSpeech]);
  const setOpenRouterModel = useCallback((orModel: string) => changeSpeech({ orModel }), [changeSpeech]);

  /** OpenRouter's speech models (one request, when the author chooses that engine). */
  const loadModels = useCallback(async (refresh = false) => {
    const r = await api.speechModels(refresh);
    if (!r.ok) { setState((s) => ({ ...s, orModels: [], message: r.error })); return; }
    if (infoRef.current) infoRef.current = { ...infoRef.current, openrouter: r.openrouter };
    setState((s) => ({ ...s, orModels: r.models, speech: infoRef.current }));
  }, []);

  const setKey = useCallback(async (key: string) => {
    const r = await api.speechSetKey(key);
    if (!r.ok) { d.notify(r.error, "error"); return; }
    if (infoRef.current) infoRef.current = { ...infoRef.current, hasKey: r.hasKey };
    setState((s) => ({ ...s, speech: infoRef.current }));
    d.notify(r.hasKey ? "Key saved in your system's keychain." : "Key removed.");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const downloadJob = useRef<string | null>(null);
  const pollTimer = useRef<number | null>(null);

  /** Download the natural voices from Hugging Face (only ever from this click), then poll until done. */
  const download = useCallback(async (variant: string) => {
    const r = await api.speechDownloadStart(variant);
    if (!r.ok) { d.notify(r.error, "error"); return; }
    downloadJob.current = r.job;
    setState((s) => ({ ...s, download: { state: "running", stage: "Starting", fraction: 0 } }));
    const poll = async () => {
      const job = downloadJob.current;
      if (!job) return;
      const st = await api.speechDownloadStatus(job);
      if (!st.ok) { setState((s) => ({ ...s, download: null })); d.notify(st.error, "error"); return; }
      if (st.state === "running") {
        setState((s) => ({ ...s, download: st }));
        pollTimer.current = window.setTimeout(poll, 500);
        return;
      }
      downloadJob.current = null;
      if (st.state === "done" && st.kokoro && infoRef.current) {
        infoRef.current = { ...infoRef.current, kokoro: st.kokoro };
        setState((s) => ({ ...s, speech: infoRef.current, download: null }));
        d.notify("The natural voices are installed.");
        if (stateRef.current.open && engineId.current === "kokoro") await load();
      } else {
        setState((s) => ({ ...s, download: st.state === "cancelled" ? null : st }));
      }
    };
    pollTimer.current = window.setTimeout(poll, 300);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load]);

  const cancelDownload = useCallback(() => {
    if (downloadJob.current) void api.speechDownloadCancel(downloadJob.current);
  }, []);

  /** Delete the downloaded voices (they can be downloaded again). */
  const removeVoices = useCallback(async () => {
    session.current?.stop();
    engines.kokoro.cancel();
    const r = await api.speechRemove();
    if (!r.ok) { d.notify(r.error, "error"); return; }
    if (infoRef.current) infoRef.current = { ...infoRef.current, kokoro: r.kokoro };
    setState((s) => ({ ...s, speech: infoRef.current }));
    if (stateRef.current.open && engineId.current === "kokoro") await load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [engines, load]);

  /** The author typed: ranges in the plan no longer match the text, so stop and plan again on the next Play. */
  const noteEdited = useCallback(() => {
    if (!planRef.current || stale.current) return;
    stale.current = true;
    if (session.current && session.current.status !== "idle") session.current.stop();
    clearHighlight();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => () => {
    session.current?.stop();
    for (const e of Object.values(engines)) e.cancel();
    if (pollTimer.current) clearTimeout(pollTimer.current);
  }, [engines]);

  return {
    state, open, close, play, toggle, setRate, setOption, setVoice, hear, noteEdited,
    setEngine, setServer, setOpenRouterModel, loadModels, setKey, download, cancelDownload, removeVoices,
    pause: () => session.current?.pause(), resume: () => session.current?.resume(),
    stop: () => session.current?.stop(), next: () => session.current?.next(), prev: () => session.current?.prev(),
    fromStart: () => void play("start"),
  };
}
