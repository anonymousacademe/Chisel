import { useState } from "react";
import { Pause, Play, SkipBack, SkipForward, Square, SlidersHorizontal, X, Volume2 } from "lucide-react";
import type { useReadAloud } from "../hooks/useReadAloud";
import { roleLabel } from "../reader/cast";
import type { VoiceInfo } from "../reader/types";
import { SpeechSettings } from "./SpeechSettings";
import { progressLabel, timeLeft } from "../reader/format";
import type { ReadOptions } from "../reader/types";
import { Icon, IconButton } from "./primitives";
import "../styles/reader.css";

const RATES = [0.75, 1, 1.25, 1.5, 2];

const voiceLabel = (v: VoiceInfo) => v.label ?? (v.lang ? `${v.name} (${v.lang})` : v.name);

const OPTION_LABELS: { key: keyof ReadOptions; label: string; modes?: string[] }[] = [
  { key: "titles", label: "Read the title" },
  { key: "headings", label: "Read headings", modes: ["script", "story", "research", "note"] },
  { key: "directions", label: "Read parentheticals (softly)", modes: ["script"] },
  { key: "transitions", label: "Read transitions (cut to)", modes: ["script"] },
  { key: "citations", label: "Say “citation” for citations", modes: ["research"] },
];

/** The read-aloud strip under the editor toolbar: transport, speed, and the voice for each role. */
export function ReaderBar({ reader }: { reader: ReturnType<typeof useReadAloud> }) {
  const { state: s } = reader;
  const [panel, setPanel] = useState(false);
  if (!s.open) return null;
  const list = s.plan?.utterances ?? [];
  const running = s.status === "playing";
  const busyOrEmpty = s.busy || !list.length;
  const voiceRoles = s.plan?.voices ?? [];

  return (
    <section className="lw-reader" aria-label="Read aloud">
      <div className="lw-reader__row">
        <Icon icon={Volume2} size={15} stroke={1.6} color="var(--lw-accent-text)" />
        <IconButton icon={SkipBack} label="Previous passage" disabled={busyOrEmpty || s.index === 0} onClick={reader.prev} />
        <IconButton icon={running ? Pause : Play} label={running ? "Pause" : s.status === "paused" ? "Resume" : "Read aloud from the cursor"}
          active={running} disabled={busyOrEmpty} onClick={reader.toggle} />
        <IconButton icon={SkipForward} label="Next passage" disabled={busyOrEmpty || s.index >= list.length - 1} onClick={reader.next} />
        <IconButton icon={Square} label="Stop" disabled={s.status === "idle" || s.status === "done"} onClick={reader.stop} />
        <button className="lw-btn lw-reader__start" disabled={busyOrEmpty} onClick={reader.fromStart}>From the start</button>
        <span className="lw-reader__status" role="status">
          {s.busy ? "Preparing…" : `${progressLabel(s.status, s.index, list.length)} · ${timeLeft(list, s.status === "idle" ? 0 : s.index, s.rate)}`}
        </span>
        <label className="lw-reader__rate">Speed
          <select value={s.rate} onChange={(e) => reader.setRate(Number(e.target.value))} aria-label="Reading speed">
            {RATES.map((r) => <option key={r} value={r}>{r}×</option>)}
          </select>
        </label>
        <IconButton icon={SlidersHorizontal} label="Voices and options" active={panel} onClick={() => setPanel((p) => !p)} />
        <IconButton icon={X} label="Close read aloud" onClick={reader.close} />
      </div>
      {s.message && <p className="lw-reader__message" role="alert">{s.message}</p>}
      {panel && (
        <div className="lw-reader__panel">
          <SpeechSettings key={`${s.speech?.prefs.baseUrl}|${s.speech?.prefs.model}`} reader={reader} />
          <div className="lw-reader__voices" role="group" aria-label="Voices">
            {voiceRoles.map(({ voice, count }) => (
              <div className="lw-reader__voice" key={voice}>
                <span className="lw-reader__role" title={`${count} passage${count === 1 ? "" : "s"}`}>{roleLabel(voice)}</span>
                <select value={s.cast[voice] ?? ""} aria-label={`Voice for ${roleLabel(voice)}`} onChange={(e) => reader.setVoice(voice, e.target.value)}>
                  {!s.cast[voice] && <option value="">{s.engine === "browser" ? "System default" : "Choose a voice"}</option>}
                  {s.voices.map((v) => <option key={v.id} value={v.id}>{voiceLabel(v)}</option>)}
                </select>
                <button className="lw-btn" onClick={() => reader.hear(voice)}>Hear</button>
              </div>
            ))}
          </div>
          <div className="lw-reader__options" role="group" aria-label="What is read">
            {OPTION_LABELS.filter((o) => !o.modes || o.modes.includes(s.plan?.mode ?? "")).map((o) => (
              <label key={o.key} className="lw-collections__check">
                <input type="checkbox" checked={s.options[o.key]} onChange={(e) => reader.setOption(o.key, e.target.checked)} /> {o.label}
              </label>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
