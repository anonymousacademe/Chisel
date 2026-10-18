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

/** A voice the system offers. */
export interface VoiceInfo { id: string; name: string; lang: string; local: boolean }
