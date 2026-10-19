import { useEffect, useState } from "react";
import { api } from "../backend/api";
import type { useReadAloud } from "../hooks/useReadAloud";
import { costLine, megabytes } from "../reader/format";
import type { EngineId, OpenRouterModel } from "../reader/types";

const ENGINES: { id: EngineId; label: string }[] = [
  { id: "browser", label: "System voices (free)" },
  { id: "kokoro", label: "Natural voices on this computer (free)" },
  { id: "endpoint", label: "Speech server (local or cloud)" },
  { id: "openrouter", label: "OpenRouter (cloud, uses your AI key)" },
];

/** Shortcuts that fill in a well-known speech server (the key is still the author's to add). */
const PRESETS = [
  { label: "OpenAI gpt-4o-mini-tts", baseUrl: "https://api.openai.com/v1", model: "gpt-4o-mini-tts" },
  { label: "OpenAI tts-1", baseUrl: "https://api.openai.com/v1", model: "tts-1" },
];

/** "ElevenLabs Turbo v2.5 · about $1.08/h" */
function modelLabel(m: OpenRouterModel): string {
  return m.perHour === null ? `${m.name} · price per second, see OpenRouter` : `${m.name} · about $${m.perHour.toFixed(2)}/h`;
}

function OpenRouterVoices({ reader }: { reader: ReturnType<typeof useReadAloud> }) {
  const { state: s } = reader;
  const info = s.speech!;
  const models = s.orModels;
  const { loadModels } = reader;
  useEffect(() => { if (models === null) void loadModels(); }, [models, loadModels]);
  const chosen = info.prefs.orModel;
  return (
    <div className="lw-reader__box">
      <p className="lw-reader__muted">Speech models from many services (ElevenLabs, Google, Microsoft, xAI and more), paid from your
        OpenRouter credit with the key you use for AI. Text is sent only when you press Play or Hear.</p>
      <label className="lw-reader__field">Model
        {models === null ? <span>Loading OpenRouter's voices…</span> : (
          <select className="lw-reader__wide" value={chosen} aria-label="OpenRouter speech model" onChange={(e) => void reader.setOpenRouterModel(e.target.value)}>
            {!models.some((m) => m.id === chosen) && <option value={chosen}>{chosen} (not listed now)</option>}
            {models.map((m) => <option key={m.id} value={m.id}>{modelLabel(m)}</option>)}
          </select>
        )}
      </label>
      {models !== null && <div className="lw-reader__actions"><button className="lw-btn" onClick={() => void loadModels(true)}>Refresh the list</button></div>}
      <p className="lw-reader__cost">{costLine(info.openrouter, s.spent)} Some voices ignore the reading speed.</p>
    </div>
  );
}

/** Who reads aloud: the system's voices, the natural voices (downloaded once from Hugging Face) or a speech
 * server the author names. Every network use here is a button the author presses. Rendered with a key of the
 * saved server, so the address fields start again from what was saved. */
export function SpeechSettings({ reader }: { reader: ReturnType<typeof useReadAloud> }) {
  const { state: s } = reader;
  const info = s.speech;
  const [baseUrl, setBaseUrl] = useState(info?.prefs.baseUrl ?? "");
  const [model, setModel] = useState(info?.prefs.model ?? "");
  const [key, setKey] = useState("");
  if (!info) return null;
  const k = info.kokoro;
  const dl = s.download;

  return (
    <div className="lw-reader__engine" role="group" aria-label="Voice engine settings">
      <label className="lw-reader__field">Voice engine
        <select value={s.engine} onChange={(e) => void reader.setEngine(e.target.value as EngineId)} aria-label="Voice engine">
          {ENGINES.map((e) => <option key={e.id} value={e.id}>{e.label}</option>)}
        </select>
      </label>

      {s.engine === "kokoro" && (
        <div className="lw-reader__box">
          {!k.engine ? (
            <p>{k.hint}</p>
          ) : k.installed ? (
            <>
              <p>Kokoro, {k.voices.length} voices, {megabytes(k.bytes)} on this computer. Runs offline, no cost.{" "}
                <span className="lw-reader__muted">Licence {k.licence}, from <a href={k.source} onClick={(e) => { e.preventDefault(); void api.openExternal(k.source); }}>Hugging Face</a>.</span></p>
              <button className="lw-btn" onClick={() => void reader.removeVoices()}>Remove the voices</button>
            </>
          ) : dl && dl.state === "running" ? (
            <>
              <p>{dl.stage} · {Math.round(dl.fraction * 100)}%</p>
              <progress max={1} value={dl.fraction} aria-label="Download progress" />
              <button className="lw-btn" onClick={reader.cancelDownload}>Cancel</button>
            </>
          ) : (
            <>
              <p>Natural-sounding voices (Kokoro, licence {k.licence}) that run on this computer: free and offline once
                downloaded from <a href={k.source} onClick={(e) => { e.preventDefault(); void api.openExternal(k.source); }}>Hugging Face</a>. Nothing is sent anywhere.</p>
              {dl?.state === "error" && <p className="lw-reader__message" role="alert">{dl.error}</p>}
              <div className="lw-reader__actions">
                {k.variants.map((v) => (
                  <button key={v.id} className="lw-btn" onClick={() => void reader.download(v.id)}>
                    Download: {v.label.replace(/,.*$/, "")} ({megabytes(v.bytes)})
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {s.engine === "endpoint" && (
        <div className="lw-reader__box">
          <p className="lw-reader__muted">Any server with the OpenAI speech API: a local one (Kokoro-FastAPI, LocalAI) is free;
            a cloud service charges per character. Text is sent only when you press Play.</p>
          <label className="lw-reader__field">Address
            <input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="http://127.0.0.1:8880/v1" spellCheck={false} />
          </label>
          <label className="lw-reader__field">Model
            <input value={model} onChange={(e) => setModel(e.target.value)} placeholder="kokoro, tts-1" spellCheck={false} />
          </label>
          <div className="lw-reader__actions">
            <button className="lw-btn" disabled={baseUrl === info.prefs.baseUrl && model === info.prefs.model}
              onClick={() => void reader.setServer(baseUrl, model)}>Use this server</button>
            {PRESETS.map((p) => (
              <button key={p.label} className="lw-btn" title={`${p.baseUrl}, model ${p.model}`}
                onClick={() => { setBaseUrl(p.baseUrl); setModel(p.model); void reader.setServer(p.baseUrl, p.model); }}>{p.label}</button>
            ))}
          </div>
          <label className="lw-reader__field">Key
            <input type="password" value={key} onChange={(e) => setKey(e.target.value)} autoComplete="off"
              placeholder={info.hasKey ? "A key is saved" : "Only if the server needs one"} />
          </label>
          <div className="lw-reader__actions">
            <button className="lw-btn" disabled={!key.trim()} onClick={() => { void reader.setKey(key); setKey(""); }}>Save key</button>
            {info.hasKey && <button className="lw-btn" onClick={() => void reader.setKey("")}>Remove key</button>}
          </div>
          <p className="lw-reader__cost">{costLine(info.endpoint, s.spent)}</p>
        </div>
      )}

      {s.engine === "openrouter" && <OpenRouterVoices reader={reader} />}
    </div>
  );
}
