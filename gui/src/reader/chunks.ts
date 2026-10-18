// Speech services cut off or stall on long utterances (some engines stop after about fifteen seconds), so
// each utterance is spoken in sentence-sized chunks, one after another.

const SENTENCE = /[^.!?…]+(?:[.!?…]+["”')\]]*)?\s*/g;

/** *text* as chunks of at most *max* characters, cut at sentence ends, else at commas / semicolons, else at
 * spaces. Short sentences are joined up to *max*. Only whitespace is lost; the text is never reworded. */
export function chunkSpeech(text: string, max = 200): string[] {
  const clean = text.replace(/\s+/g, " ").trim();
  if (!clean) return [];
  const pieces: string[] = [];
  for (const s of clean.match(SENTENCE) ?? [clean]) pieces.push(...split(s.trim(), max));
  const out: string[] = [];
  for (const p of pieces) {
    if (out.length && out[out.length - 1].length + 1 + p.length <= max) out[out.length - 1] += ` ${p}`;
    else out.push(p);
  }
  return out;
}

function split(s: string, max: number): string[] {
  if (s.length <= max) return s ? [s] : [];
  for (const mark of [/[,;:](?=\s)/g, /\s/g]) {
    let cut = -1;
    for (const m of s.matchAll(mark)) {
      const at = m.index! + (mark.source.startsWith("[") ? 1 : 0);
      if (at <= max) cut = at; else break;
    }
    if (cut > 0) return [s.slice(0, cut).trim(), ...split(s.slice(cut).trim(), max)].filter(Boolean);
  }
  return [s.slice(0, max), ...split(s.slice(max), max)];   // one unbroken word longer than max
}
