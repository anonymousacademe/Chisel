// Read aloud (docs/dev/plan-read-aloud.md). Python decides what is read and in which voice (core/reader.py);
// this side only speaks it. These mirror Api.read_plan.

export interface ReadUtterance {
  kind: string;        // title, heading, scene-heading, narration, quote, dialogue, direction, transition
  voice: string;       // "narrator", "quote", or a script speaker's name
  text: string;        // as shown
  say: string;         // as spoken: markup removed, names respelled
  start: number;       // source range in the editor text, UTF-16
  end: number;
  row: number;
  seconds: number;     // estimated at rate 1
  /** continues the previous utterance's paragraph: spoken together with it when the voice is the same */
  joins?: boolean;
}

export interface ReadPlan {
  mode: string;        // script | story | research | note
  utterances: ReadUtterance[];
  words: number;
  seconds: number;
  voices: { voice: string; count: number }[];
}

export interface ReadOptions {
  titles: boolean; headings: boolean; directions: boolean; transitions: boolean; citations: boolean;
}

export const DEFAULT_READ_OPTIONS: ReadOptions = { titles: true, headings: true, directions: false, transitions: false, citations: false };

/** A voice an engine offers. *rank*: suggested order (natural voices; lower first); *label*: name with details. */
export interface VoiceInfo { id: string; name: string; lang: string; local: boolean; rank?: number; label?: string }

/** Who speaks: the system's voices (played by the window) or clips rendered by Python (chisel/speech/). */
export type EngineId = "browser" | "kokoro" | "endpoint" | "openrouter";

/** *orModel*: the OpenRouter speech model (openrouter engine). */
export interface SpeechPrefs { engine: EngineId; baseUrl: string; model: string; orModel: string }

/** An OpenRouter speech model (python: speech/openrouter.py); prices are null when OpenRouter does not price it
 * per character. */
export interface OpenRouterModel { id: string; name: string; voices: string[]; pricePerMillion: number | null; perHour: number | null }

export interface KokoroStatus {
  installed: boolean; variant: string; bytes: number; voices: VoiceInfo[]; licence: string; source: string;
  revision: string; variants: { id: string; bytes: number; label: string }[];
  /** the local engine's Python package is installed; *hint* says what to do when it is not */
  engine: boolean;
  hint: string;
}

/** Cost facts for the speech server: local (free), else the published price when known. */
export interface EndpointCost { local: boolean; pricePerMillion: number | null; perHour: number | null }

export interface SpeechInfo {
  prefs: SpeechPrefs; hasKey: boolean; kokoro: KokoroStatus; endpoint: EndpointCost;
  openrouter: EndpointCost; hasOpenRouterKey: boolean;
}

export interface DownloadStatus {
  state: "running" | "done" | "error" | "cancelled"; stage: string; fraction: number; error?: string; kokoro?: KokoroStatus;
}
