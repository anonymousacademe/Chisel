import { useState } from "react";
import { Pause, Play, Trash2 } from "lucide-react";
import { api } from "../backend/api";
import { BUILTIN_PACKS, CUSTOM_PREFIX, LAYERS, activeCount, validStationUrl, type Station } from "../data/atmosphere";
import { atmosphere, useAtmosphere } from "../audio/store";
import { previewTyping } from "../audio/typing";
import { Modal } from "./Dialogs";
import { Icon } from "./primitives";

type Notify = (text: string, tone?: "info" | "error") => void;

const Slider = ({ value, onChange, label }: { value: number; onChange: (v: number) => void; label: string }) => (
  <input type="range" className="lw-slider" min={0} max={1} step={0.05} value={value} aria-label={label}
    onChange={(e) => onChange(Number(e.target.value))} />
);

/** Typing-sound controls; used by the panel and by Settings. */
export function TypingControls({ notify }: { notify: Notify }) {
  const { info } = useAtmosphere();
  const t = info.prefs.typing;
  const custom = t.pack.startsWith(CUSTOM_PREFIX);
  const report = (msg: string) => { if (msg) notify(msg, /^(Imported|Saved)/.test(msg) ? "info" : "error"); };
  return (
    <div className="lw-atmo__block">
      <label className="lw-check">
        <input type="checkbox" checked={t.on} onChange={(e) => atmosphere.setTyping({ on: e.target.checked })} />
        Play a sound as I type <span className="lw-faint">(only in the editor; off by default)</span>
      </label>
      <div className="lw-row lw-gap-8">
        <label className="lw-dialog__label lw-atmo__grow">Sound pack
          <select className="lw-launch__input" value={t.pack} aria-label="Typing sound pack" onChange={(e) => atmosphere.setTyping({ pack: e.target.value })}>
            {BUILTIN_PACKS.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            {info.packs.map((p) => <option key={p.id} value={CUSTOM_PREFIX + p.id}>{p.name} (yours)</option>)}
            {custom && !info.packs.some((p) => CUSTOM_PREFIX + p.id === t.pack) && <option value={t.pack}>{t.pack.slice(CUSTOM_PREFIX.length)} (missing)</option>}
          </select>
        </label>
        <button className="lw-btn" onClick={previewTyping}>Try it</button>
      </div>
      <div className="lw-row lw-gap-8"><span className="lw-dialog__label">Volume</span>
        <Slider label="Typing volume" value={t.volume} onChange={(v) => atmosphere.setTyping({ volume: v })} /></div>
      <div className="lw-row lw-gap-8 lw-atmo__wrap">
        <button className="lw-btn" onClick={() => void atmosphere.importPack().then(report)}>Import sound pack…</button>
        <button className="lw-btn" disabled={!custom} title={custom ? "Save this pack as a .zip to share" : "Only packs you added can be exported"}
          onClick={() => void atmosphere.exportPack(t.pack.slice(CUSTOM_PREFIX.length)).then(report)}>Export pack…</button>
        <button className="lw-btn" onClick={() => void api.openSoundsFolder("sounds").then((r) => { if (r.ok) { void atmosphere.refreshPacks(); if (!r.opened) notify(`Sound packs live in ${r.path}`); } })}>Open sounds folder</button>
      </div>
    </div>
  );
}

function StationRow({ s, active, status, onPlay, onRemove, onOpen }: {
  s: Station; active: boolean; status: string; onPlay: () => void; onRemove: () => void; onOpen: (url: string) => void;
}) {
  return (
    <div className={`lw-atmo__station${active ? " is-on" : ""}`}>
      <div className="lw-row lw-gap-8">
        <button className="lw-btn" onClick={onPlay} aria-label={`${active ? "Stop" : "Play"} ${s.name}`} aria-pressed={active}>
          <Icon icon={active ? Pause : Play} size={13} stroke={1.8} />
        </button>
        <span className="lw-atmo__grow">{s.name}{active && status && <span className="lw-faint"> · {status}</span>}</span>
        <button className="lw-btn" onClick={onRemove} aria-label={`Remove ${s.name}`}><Icon icon={Trash2} size={13} stroke={1.6} /></button>
      </div>
      {s.attribution && (
        <div className="lw-faint lw-atmo__via">{s.attribution.text}{" "}
          <a href={s.attribution.link} onClick={(e) => { e.preventDefault(); onOpen(s.attribution!.link); }}>somafm.com/support</a></div>
      )}
    </div>
  );
}

/** The mixer: typing sounds, generated ambience layers, loop files and internet radio. */
export function AtmospherePanel({ onClose, notify }: { onClose: () => void; notify: Notify }) {
  const st = useAtmosphere();
  const a = st.info.prefs.ambience;
  const [preset, setPreset] = useState("");
  const [presetName, setPresetName] = useState("");
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const stations = st.info.stations;
  const open = (u: string) => void api.openExternal(u).then((r) => { if (!r.ok) notify(r.error, "error"); });
  const statusText = st.station === "loading" ? "connecting…" : st.station === "playing" ? "playing" : st.station === "error" ? st.stationDetail || "could not play" : "";
  const saveStations = async (rows: Station[] | null) => { const err = await atmosphere.saveStations(rows); if (err) notify(err, "error"); };
  const addStation = () => {
    const valid = validStationUrl(url);
    if (!name.trim()) return notify("Give the station a name.", "error");
    if (!valid) return notify("A station address must start with http:// or https://", "error");
    void saveStations([...stations, { name: name.trim(), url: valid }]).then(() => { setName(""); setUrl(""); });
  };
  return (
    <Modal title="Sound" wide onClose={onClose}>
      <div className="lw-settings lw-atmo">
        <section className="lw-settings__section">
          <h3>Typing sounds</h3>
          <TypingControls notify={notify} />
        </section>

        <section className="lw-settings__section">
          <h3>Ambience</h3>
          <div className="lw-row lw-gap-8">
            <button className="lw-btn" onClick={() => atmosphere.play(!st.playing)} disabled={!st.playing && activeCount(a) === 0}
              title={activeCount(a) === 0 ? "Raise a layer to start" : st.playing ? "Pause the layers" : "Play the layers"}>
              <Icon icon={st.playing ? Pause : Play} size={13} stroke={1.8} /> {st.playing ? "Pause" : "Play"}
            </button>
            <span className="lw-dialog__label">Master</span>
            <Slider label="Ambience volume" value={a.volume} onChange={(v) => atmosphere.setAmbience({ volume: v })} />
          </div>
          <p className="lw-faint lw-atmo__note">Made on your computer, offline. Move a slider to start that sound.</p>
          {LAYERS.map((l) => (
            <div key={l.id} className="lw-row lw-gap-8 lw-atmo__layer">
              <span className="lw-atmo__label">{l.name}</span>
              <Slider label={l.name} value={a.layers[l.id] ?? 0} onChange={(v) => atmosphere.setLayer(l.id, v)} />
            </div>
          ))}
          {st.info.loops.map((l) => (
            <div key={l.id} className="lw-row lw-gap-8 lw-atmo__layer">
              <span className="lw-atmo__label" title={l.id}>{l.name} <span className="lw-faint">(your file)</span></span>
              <Slider label={l.name} value={a.loops[l.id] ?? 0} onChange={(v) => atmosphere.setLoop(l.id, v)} />
            </div>
          ))}
          <div className="lw-row lw-gap-8 lw-atmo__wrap">
            <select className="lw-launch__input lw-atmo__grow" value={preset} aria-label="Saved mixes" onChange={(e) => { setPreset(e.target.value); if (e.target.value) atmosphere.loadPreset(e.target.value); }}>
              <option value="">Saved mixes…</option>
              {Object.keys(a.presets).map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
            <button className="lw-btn" disabled={!preset} onClick={() => { atmosphere.deletePreset(preset); setPreset(""); }}>Delete mix</button>
          </div>
          <div className="lw-row lw-gap-8">
            <input className="lw-launch__input" value={presetName} maxLength={40} placeholder="Name this mix (e.g. Rainy café)" aria-label="Mix name"
              onChange={(e) => setPresetName(e.target.value)} />
            <button className="lw-btn" disabled={!presetName.trim() || Object.keys(a.layers).length === 0}
              onClick={() => { atmosphere.savePreset(presetName); setPreset(presetName.trim()); setPresetName(""); }}>Save mix</button>
          </div>
          <div className="lw-row lw-gap-8">
            <button className="lw-btn" onClick={() => void api.openSoundsFolder("ambience").then((r) => { if (r.ok) { void atmosphere.refreshPacks(); if (!r.opened) notify(`Put loop files (wav, ogg, mp3, flac) in ${r.path}`); } })}>Open ambience folder</button>
            <span className="lw-faint lw-atmo__note">Your own loops go here and are listed above.</span>
          </div>
        </section>

        <section className="lw-settings__section">
          <h3>Internet radio</h3>
          <p className="lw-faint lw-atmo__note">Uses the internet, and nothing plays until you pick a station. No account, no tracking from LoreWriter. Addresses must start with http:// or https://.</p>
          {stations.map((s) => (
            <StationRow key={s.url} s={s} active={a.station === s.url && st.station !== "idle"} status={statusText}
              onPlay={() => (a.station === s.url && st.station !== "idle" ? atmosphere.stopStation() : atmosphere.pickStation(s.url))}
              onRemove={() => { if (a.station === s.url) atmosphere.stopStation(); void saveStations(stations.filter((x) => x.url !== s.url)); }}
              onOpen={open} />
          ))}
          {stations.length === 0 && <p className="lw-empty">No stations. Add one below, or restore the defaults.</p>}
          <div className="lw-row lw-gap-8"><span className="lw-dialog__label">Radio volume</span>
            <Slider label="Radio volume" value={a.stationVolume} onChange={(v) => atmosphere.setAmbience({ stationVolume: v })} /></div>
          <div className="lw-row lw-gap-8 lw-atmo__wrap">
            <input className="lw-launch__input" value={name} maxLength={60} placeholder="Station name" aria-label="Station name" onChange={(e) => setName(e.target.value)} />
            <input className="lw-launch__input lw-atmo__grow" value={url} placeholder="https://… stream address" aria-label="Station address" spellCheck={false}
              onChange={(e) => setUrl(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") addStation(); }} />
            <button className="lw-btn" onClick={addStation}>Add</button>
            <button className="lw-btn" onClick={() => { atmosphere.stopStation(); void saveStations(null); }}>Restore defaults</button>
          </div>
        </section>
      </div>
      <div className="lw-dialog__buttons">
        <button className="lw-btn" onClick={() => atmosphere.pauseAll()} disabled={!st.playing && st.station === "idle"}>Silence everything</button>
        <button className="lw-btn lw-btn--primary" onClick={onClose}>Done</button>
      </div>
    </Modal>
  );
}
