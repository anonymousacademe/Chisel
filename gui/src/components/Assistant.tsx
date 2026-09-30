import { useEffect, useRef, useState } from "react";
import {
  Sparkles, History, PanelRightClose, Lightbulb, WandSparkles, ScanSearch, BookSearch, LocateFixed, Copy,
  RefreshCw, ThumbsUp, UserRound, FileText, ArrowUpRight, Paperclip, ArrowUp, Ellipsis, TextCursorInput,
  type LucideIcon,
} from "lucide-react";
import type { ChatMessage, EntityInfo, Issue, SceneMention } from "../data/types";
import { NotesPanel } from "./NotesPanel";
import { Icon, IconButton, SectionLabel, Tag } from "./primitives";
import { placeholderProps } from "./placeholder";

export type AssistantTab = "assistant" | "context" | "notes";
export type QuickAction = "rewrite" | "continuity";
type Tab = AssistantTab;
const isMac = typeof navigator !== "undefined" && /Mac/.test(navigator.platform);

const tools: { icon: LucideIcon; title: string; detail: string; action?: QuickAction }[] = [
  { icon: Lightbulb, title: "Brainstorm", detail: "Plot, character, image" },
  { icon: WandSparkles, title: "Rewrite", detail: "Tone, clarity, rhythm", action: "rewrite" },
  { icon: ScanSearch, title: "Continuity", detail: "Facts, timeline, logic", action: "continuity" },
  { icon: BookSearch, title: "Research", detail: "Project + web library" },
];

const TYPE_LABEL: Record<string, string> = {
  physical_attribute: "Physical attribute", timeline: "Timeline", character_knowledge: "Character knowledge",
  object_custody: "Object custody", present_absent: "Present / absent", spelling_drift: "Spelling drift",
};

export function Assistant(props: {
  tab: AssistantTab; onTab: (t: AssistantTab) => void;
  mentions: SceneMention[]; onPickEntity: (name: string) => void;
  note: EntityInfo | null; missingTarget: string | null;
  onOpenNote: (id: string) => void; onAddAlias: (name: string, alias: string) => void;
  onCreateNote: (target: string) => void; onOpenBacklink: (sourceId: string, row: number) => void;
  issues: Issue[]; onReviewIssue: (i: Issue) => void; onDismissIssue: (i: Issue) => void;
  messages: ChatMessage[]; busy: string | null; aiReady: boolean;
  scope: "scene" | "project"; onScope: () => void;
  onSend: (text: string) => void; onRegenerate: (id: string) => void; onInsertDraft: (id: string) => void;
  onQuick: (a: QuickAction) => void; onMenu: (anchor: HTMLElement) => void; onClose: () => void;
  canInsert: boolean;
}) {
  const { tab, onTab: setTab } = props;
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const logRef = useRef<HTMLDivElement>(null);
  const busy = props.busy !== null;

  // Ctrl/⌘ J focuses the composer (unless the editor used it to open a note).
  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.defaultPrevented) return;
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "j") { e.preventDefault(); setTab("assistant"); inputRef.current?.focus(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setTab]);
  useEffect(() => { logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" }); }, [props.messages.length]);

  const send = () => {
    const t = draft.trim();
    if (!t || busy) return;
    props.onSend(t); setDraft(""); if (inputRef.current) inputRef.current.style.height = "15px";
  };

  return (
    <aside className="lw-assistant" aria-label="AI writing assistant">
      <div className="lw-assistant__header">
        <div className="lw-row lw-gap-8">
          <span className="lw-mark lw-mark--lg"><Icon icon={Sparkles} size={14} stroke={1.8} /></span>
          <h2>LoreWriter</h2>
          <Tag tone="success">Project aware</Tag>
        </div>
        <div className="lw-row lw-gap-4">
          <IconButton icon={Ellipsis} label="More AI actions" onClick={(e) => props.onMenu(e.currentTarget)} />
          <IconButton icon={History} label="Conversation history" placeholder />
          <IconButton icon={PanelRightClose} label="Close panel" onClick={props.onClose} />
        </div>
      </div>
      <div className="lw-divider" />
      <div className="lw-tabs" role="tablist">
        {(["assistant", "context", "notes"] as Tab[]).map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} className={`lw-tab${tab === t ? " is-active" : ""}`} onClick={() => setTab(t)}>
            {t[0].toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      <div className="lw-assistant__body" ref={logRef}>
        {tab === "assistant" && (
          <>
            <section className="lw-quick">
              <div className="lw-quick__heading">
                <SectionLabel accent>Quick actions</SectionLabel>
                <span className="lw-mono lw-faint">{isMac ? "⌘ J" : "Ctrl J"}</span>
              </div>
              <div className="lw-quick__grid">
                {tools.map((t) => (
                  <button key={t.title} className="lw-tool" disabled={!!t.action && (busy || !props.aiReady)}
                    {...(t.action ? { onClick: () => props.onQuick(t.action!) } : placeholderProps)}>
                    <span className="lw-row lw-gap-6">
                      <Icon icon={t.icon} size={13} stroke={1.7} color="var(--lw-accent-text)" />
                      <span className="lw-tool__title">{t.title}</span>
                    </span>
                    <span className="lw-tool__detail">{t.detail}</span>
                  </button>
                ))}
              </div>
              {!props.aiReady && <p className="lw-empty">AI features are off until an OpenRouter API key is set (Settings).</p>}
            </section>
            <div className="lw-divider" />

            {props.issues.length > 1 && <SectionLabel>{props.issues.length} issues in this scene</SectionLabel>}
            {props.issues.map((it) => (
              <section key={it.key} className="lw-insight">
                <div className="lw-insight__heading">
                  <span className="lw-row lw-gap-6">
                    <Icon icon={ScanSearch} size={14} stroke={1.7} color="var(--lw-accent-text)" />
                    <strong>Continuity check</strong>
                  </span>
                  <Tag>1 conflict</Tag>
                </div>
                <p className="lw-insight__kind">{TYPE_LABEL[it.type] ?? it.type} · {it.entity}</p>
                <p className="lw-insight__quote">“{it.evidence}”</p>
                {it.fix && <p>{it.fix}</p>}
                <div className="lw-row lw-gap-8">
                  <button className="lw-btn lw-btn--grow" onClick={() => props.onReviewIssue(it)}>
                    <Icon icon={LocateFixed} size={14} stroke={1.8} /> Review passage
                  </button>
                  <button className="lw-btn" onClick={() => props.onDismissIssue(it)} title="Waive this issue: it will not be reported again">Dismiss</button>
                </div>
              </section>
            ))}

            {props.messages.map((m) => m.role === "user" ? (
              <div key={m.id} className="lw-msg-user"><div className="lw-bubble">{m.text}</div></div>
            ) : (
              <div key={m.id} className="lw-msg-ai">
                <span className="lw-mark"><Icon icon={Sparkles} size={12} stroke={1.7} /></span>
                <div className="lw-msg-ai__body">
                  <p className={`lw-msg-ai__text${m.error ? " is-error" : ""}`}>{m.text}</p>
                  {!m.error && (
                    <div className="lw-row lw-gap-4">
                      <IconButton icon={Copy} label="Copy" onClick={() => navigator.clipboard?.writeText(m.text)} />
                      <IconButton icon={RefreshCw} label="Regenerate" disabled={busy} onClick={() => props.onRegenerate(m.id)} />
                      <IconButton icon={TextCursorInput} label="Insert as a draft at the cursor" disabled={!props.canInsert || busy} onClick={() => props.onInsertDraft(m.id)} />
                      <IconButton icon={ThumbsUp} label="Helpful" placeholder />
                    </div>
                  )}
                </div>
              </div>
            ))}
            {busy && <div className="lw-msg-ai"><span className="lw-mark"><Icon icon={Sparkles} size={12} stroke={1.7} /></span><p className="lw-msg-ai__intro lw-pulse">{props.busy}</p></div>}

            <Sources mentions={props.mentions} onPick={props.onPickEntity} />
          </>
        )}
        {tab === "context" && <Sources mentions={props.mentions} onPick={props.onPickEntity} />}
        {tab === "notes" && (
          <NotesPanel note={props.note} missingTarget={props.missingTarget} onOpenNote={props.onOpenNote}
            onAddAlias={props.onAddAlias} onCreateNote={props.onCreateNote} onOpenBacklink={props.onOpenBacklink} />
        )}
      </div>

      <div className="lw-composer-region">
        <div className="lw-composer">
          <textarea ref={inputRef} rows={1} value={draft} disabled={!props.aiReady} placeholder="Ask about this scene or your project…"
            onChange={(e) => { setDraft(e.target.value); const t = e.currentTarget; t.style.height = "15px"; t.style.height = `${t.scrollHeight}px`; }}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} />
          <div className="lw-composer__controls">
            <div className="lw-row lw-gap-4">
              <IconButton icon={Paperclip} label="Attach context" small placeholder />
              <button className="lw-tag lw-tag--accent lw-tag--button" onClick={props.onScope}
                title="What the assistant reads: this scene, or scene titles and notes for the whole project">
                {props.scope === "scene" ? "Current scene" : "Project"}
              </button>
            </div>
            <button className="lw-send" aria-label="Send" onClick={send} disabled={!draft.trim() || busy || !props.aiReady}>
              <Icon icon={ArrowUp} size={14} stroke={2} />
            </button>
          </div>
        </div>
        <p className="lw-disclaimer">LoreWriter can be wrong. Review changes before applying.</p>
      </div>
    </aside>
  );
}

function Sources({ mentions, onPick }: { mentions: SceneMention[]; onPick: (name: string) => void }) {
  return (
    <section className="lw-sources">
      <SectionLabel>Retrieved context</SectionLabel>
      {mentions.length === 0 && <p className="lw-empty">No notes are mentioned in this scene yet.</p>}
      {mentions.map((m) => (
        <button key={m.name} className="lw-source" onClick={() => onPick(m.name)}>
          <span className="lw-source__icon"><Icon icon={m.type === "character" ? UserRound : FileText} size={14} stroke={1.5} /></span>
          <span className="lw-source__details">
            <span className="lw-source__title">{m.name} — {m.type}</span>
            <span className="lw-source__meta">{m.count}× in this scene · {m.backlinks} line{m.backlinks === 1 ? "" : "s"} in the project</span>
          </span>
          <Icon icon={ArrowUpRight} size={13} stroke={1.5} color="var(--lw-text-faint)" />
        </button>
      ))}
    </section>
  );
}
