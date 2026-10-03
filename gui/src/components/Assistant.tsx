import { useEffect, useRef, useState } from "react";
import {
  Sparkles, History, PanelRightClose, Lightbulb, WandSparkles, ScanSearch, BookSearch, LocateFixed, Copy,
  RefreshCw, BookmarkPlus, UserRound, X, FileText, ArrowUpRight, Paperclip, ArrowUp, Ellipsis, TextCursorInput, Feather,
  type LucideIcon,
} from "lucide-react";
import type { ChatMessage, EntityInfo, Issue, SceneMention, SentReport as Report, StyleStatus } from "../data/types";
import { SentReport } from "./SentReport";
import { NotesPanel } from "./NotesPanel";
import { attachKey, type Attachment } from "../data/chat";
import type { Subject } from "../data/subject";
import { Icon, IconButton, SectionLabel, Tag } from "./primitives";
import { placeholderProps } from "./placeholder";
import { Markdown } from "./Markdown";
import { StopButton } from "./AiProgress";
import { stopOnEsc, useElapsed, secs, type AiRunView } from "./aiRun";

export type AssistantTab = "assistant" | "context" | "notes" | "inspiration";
import { ASK_NOTEBOOK_HINT } from "../data/notebook";
export type QuickAction = "brainstorm" | "rewrite" | "continuity" | "research";
type Tab = AssistantTab;
const isMac = typeof navigator !== "undefined" && /Mac/.test(navigator.platform);

const tools: { icon: LucideIcon; title: string; detail: string; action?: QuickAction }[] = [
  { icon: Lightbulb, title: "Brainstorm", detail: "Plot, character, image", action: "brainstorm" },
  { icon: WandSparkles, title: "Rewrite", detail: "Tone, clarity, rhythm", action: "rewrite" },
  { icon: ScanSearch, title: "Continuity", detail: "Facts, timeline, logic", action: "continuity" },
  { icon: BookSearch, title: "Ask my notebook", detail: ASK_NOTEBOOK_HINT, action: "research" },
];

const TYPE_LABEL: Record<string, string> = {
  physical_attribute: "Physical attribute", timeline: "Timeline", character_knowledge: "Character knowledge",
  object_custody: "Object custody", present_absent: "Present / absent", spelling_drift: "Spelling drift",
};

export function Assistant(props: {
  tab: AssistantTab; onTab: (t: AssistantTab) => void;
  mentions: SceneMention[]; onPickEntity: (name: string) => void;
  note: EntityInfo | null; missingTarget: string | null;
  onOpenNote: (id: string) => void; onAddAlias: (name: string, alias: string) => void; onSetBorn: (name: string, born: string) => void; onRename: (name: string, aliases: string[]) => void;
  onCreateNote: (target: string) => void; onOpenBacklink: (sourceId: string, row: number) => void;
  issues: Issue[]; onReviewIssue: (i: Issue) => void; onDismissIssue: (i: Issue) => void;
  /** What the last continuity check sent (shown under its issues). */
  issuesSent?: Report | null;
  messages: ChatMessage[]; busy: string | null; aiReady: boolean;
  /** The running AI job (chat replies type in live while it runs); onStop cancels it. */
  run: AiRunView | null; onStop: () => void;
  scope: "scene" | "project"; onScope: () => void;
  /** What the assistant reads now (the scope control's label). */
  scopeText: string;
  /** The open item the questions are about ("About: Mara (character)"); null = none is sent. The author can remove it for this chat. */
  subject: Subject | null; onRemoveSubject: () => void;
  /** Set when the author removed the chip and an item that could be the subject is open. */
  onRestoreSubject?: () => void;
  onSend: (text: string) => void; onRegenerate: (id: string) => void; onInsertDraft: (id: string) => void;
  /** Ask-my-notebook mode: the next question is answered from the notebook notes (and canon), citing them. */
  researchMode: boolean; onOpenSource: (id: string) => void;
  /** Conversation history, attach and Save to notes (Wave 3.4). */
  onHistory: () => void; onAttach: () => void; attachments: Attachment[]; onRemoveAttachment: (a: Attachment) => void;
  onSaveReply: (id: string) => void;
  /** Brainstorm ideas: write from one (opens the draft prompt prefilled) or keep it in the notes. */
  onDraftIdea: (idea: string) => void; onSaveIdea: (idea: string) => void;
  onQuick: (a: QuickAction) => void; onMenu: (anchor: HTMLElement) => void; onClose: () => void;
  canInsert: boolean;
  /** Shown under the note in the Notes tab (the scene's comments). */
  notesExtra?: React.ReactNode;
  /** The Inspiration tab. Kept mounted (hidden) so a half-written description survives a tab switch. */
  inspiration?: React.ReactNode;
  style: StyleStatus | null; onLearnStyle: () => void; onOpenStyle: () => void;
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
          <h2>Chisel</h2>
          <Tag tone="success">Project aware</Tag>
        </div>
        <div className="lw-row lw-gap-4">
          <IconButton icon={Ellipsis} label="More AI actions" onClick={(e) => props.onMenu(e.currentTarget)} />
          <IconButton icon={History} label="Conversation history" onClick={props.onHistory} />
          <IconButton icon={PanelRightClose} label="Close panel" onClick={props.onClose} />
        </div>
      </div>
      {(props.subject || props.onRestoreSubject) && (
        <div className="lw-about">
          {props.subject ? (
            <span className="lw-chip lw-chip--attached lw-chip--about" aria-label="The assistant is told about this item"
              title="Your question and Brainstorm also send this item's text to the AI. Remove it to stop for this chat.">
              <span className="lw-chip__text">{props.subject.label}</span>
              <button aria-label={`Stop sending ${props.subject.label.replace(/^About: /, "")}`} onClick={props.onRemoveSubject}><Icon icon={X} size={11} stroke={2} /></button>
            </span>
          ) : (
            <button className="lw-link" onClick={props.onRestoreSubject}
              title="Tell the assistant about the item that is open now (its text is sent with your question)">Use the open item again</button>
          )}
        </div>
      )}
      <div className="lw-divider" />
      <div className="lw-tabs" role="tablist">
        {(["assistant", "context", "notes", "inspiration"] as Tab[]).map((t) => (
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
                  <button key={t.title} className={`lw-tool${t.action === "research" && props.researchMode ? " is-on" : ""}`} aria-pressed={t.action === "research" ? props.researchMode : undefined}
                    disabled={!!t.action && (busy || !props.aiReady)}
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
            {props.style && <StyleCard style={props.style} busy={busy} aiReady={props.aiReady}
              onLearn={props.onLearnStyle} onOpen={props.onOpenStyle} />}
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
            {props.issuesSent && <SentReport report={props.issuesSent} />}

            {props.messages.map((m) => m.role === "user" ? (
              <div key={m.id} className="lw-msg-user"><div className="lw-bubble">{m.text}</div></div>
            ) : (
              <div key={m.id} className="lw-msg-ai">
                <span className="lw-mark"><Icon icon={Sparkles} size={12} stroke={1.7} /></span>
                <div className="lw-msg-ai__body">
                  {m.ideas && m.ideas.length > 0 ? (
                    <ol className="lw-ideas" aria-label="Brainstorm ideas">
                      {m.ideas.map((idea, i) => (
                        <li key={i} className="lw-idea">
                          <p>{idea}</p>
                          <div className="lw-row lw-gap-6">
                            <button className="lw-btn" disabled={!props.canInsert || busy} onClick={() => props.onDraftIdea(idea)}
                              title="Open the draft prompt with this idea filled in">
                              <Icon icon={Feather} size={13} stroke={1.8} /> Draft from this
                            </button>
                            <button className="lw-btn" onClick={() => props.onSaveIdea(idea)}
                              title="Add this idea to notebook/assistant-notes.md">
                              <Icon icon={BookmarkPlus} size={13} stroke={1.8} /> Save to notes
                            </button>
                          </div>
                        </li>
                      ))}
                    </ol>
                  ) : (
                    m.error ? <p className={`lw-msg-ai__text${m.stopped ? " is-stopped" : " is-error"}`}>{m.text}</p>
                      : <Markdown text={m.text} />
                  )}
                  {m.sources && m.sources.length > 0 && (
                    <div className="lw-sources-line" aria-label="Notebook notes used">
                      <span className="lw-faint">Notes:</span>
                      {m.sources.map((s, i) => (
                        <button key={s.id} className="lw-chip lw-chip--source" title={`Open ${s.title}`} onClick={() => props.onOpenSource(s.id)}>[{i + 1}] {s.title}</button>
                      ))}
                    </div>
                  )}
                  {!m.error && <SentReport report={m.sent} />}
                  {!m.error && (
                    <div className="lw-row lw-gap-4">
                      <IconButton icon={Copy} label="Copy" onClick={() => navigator.clipboard?.writeText(m.text)} />
                      <IconButton icon={RefreshCw} label="Regenerate" disabled={busy} onClick={() => props.onRegenerate(m.id)} />
                      {!m.ideas && <IconButton icon={TextCursorInput} label="Insert as a draft at the cursor" disabled={!props.canInsert || busy} onClick={() => props.onInsertDraft(m.id)} />}
                      <IconButton icon={BookmarkPlus} label={m.ideas ? "Save all the ideas to notes (notebook/assistant-notes.md)" : "Save to notes (notebook/assistant-notes.md)"} onClick={() => props.onSaveReply(m.id)} />
                    </div>
                  )}
                </div>
              </div>
            ))}
            {props.run?.mode === "chat" && <LiveReply run={props.run} onStop={props.onStop} />}

            <Sources mentions={props.mentions} onPick={props.onPickEntity} />
          </>
        )}
        {tab === "context" && <Sources mentions={props.mentions} onPick={props.onPickEntity} />}
        {tab === "notes" && (
          <NotesPanel note={props.note} missingTarget={props.missingTarget} onOpenNote={props.onOpenNote}
            onAddAlias={props.onAddAlias} onSetBorn={props.onSetBorn} onRename={props.onRename} onCreateNote={props.onCreateNote} onOpenBacklink={props.onOpenBacklink} />
        )}
        {tab === "notes" && props.notesExtra}
        <div hidden={tab !== "inspiration"}>{props.inspiration}</div>
      </div>

      <div className="lw-composer-region">
        {props.attachments.length > 0 && (
          <div className="lw-attachments" aria-label="Attached to this chat">
            {props.attachments.map((a) => (
              <span key={attachKey(a)} className="lw-chip lw-chip--attached" title={`${a.kind}: ${a.title}`}>
                {a.kind === "comments" ? `Comments · ${a.title}` : a.title}
                <button aria-label={`Remove ${a.title}`} onClick={() => props.onRemoveAttachment(a)}><Icon icon={X} size={11} stroke={2} /></button>
              </span>
            ))}
          </div>
        )}
        <div className="lw-composer">
          <textarea ref={inputRef} rows={1} value={draft} disabled={!props.aiReady} placeholder={props.researchMode ? "Ask a question your notebook can answer…" : "Ask about this scene or your project…"}
            onChange={(e) => { setDraft(e.target.value); const t = e.currentTarget; t.style.height = "15px"; t.style.height = `${t.scrollHeight}px`; }}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} />
          <div className="lw-composer__controls">
            <div className="lw-row lw-gap-4">
              <IconButton icon={Paperclip} label="Attach scenes, notes, notebook notes or comments" small onClick={props.onAttach} />
              <button className="lw-tag lw-tag--accent lw-tag--button" onClick={props.onScope}
                title="What the assistant reads: the open scene (or scene titles and notes for the whole project) plus the open note, when it is shown above">
                {props.scopeText}
              </button>
              {props.researchMode && <span className="lw-tag lw-tag--success">Notebook</span>}
            </div>
            <button className="lw-send" aria-label="Send" onClick={send} disabled={!draft.trim() || busy || !props.aiReady}>
              <Icon icon={ArrowUp} size={14} stroke={2} />
            </button>
          </div>
        </div>
        <p className="lw-disclaimer">Chisel can be wrong. Review changes before applying.</p>
      </div>
    </aside>
  );
}

/** The reply as it is written: Markdown typing in, with the elapsed time and Stop. */
function LiveReply({ run, onStop }: { run: AiRunView; onStop: () => void }) {
  const elapsed = useElapsed(run.startedAt, run.elapsed);
  return (
    <div className="lw-msg-ai" tabIndex={0} aria-label="AI is replying" onKeyDown={stopOnEsc(onStop)}>
      <span className="lw-mark"><Icon icon={Sparkles} size={12} stroke={1.7} /></span>
      <div className="lw-msg-ai__body">
        {run.text ? <Markdown text={run.text} /> : <p className="lw-msg-ai__intro lw-pulse">{run.label}</p>}
        <div className="lw-row lw-gap-8"><StopButton onStop={onStop} small /><span className="lw-faint lw-mono">{secs(elapsed)}</span></div>
      </div>
    </div>
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

const fmtDate = (iso: string) =>
  new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });

/** "Your style": learn the author's voice from their own scenes, in one click. */
function StyleCard(props: { style: StyleStatus; busy: boolean; aiReady: boolean; onLearn: () => void; onOpen: () => void }) {
  const { style } = props;
  const enough = style.manuscriptWords >= 300;
  let line: string;
  if (style.learned && style.sampledWords !== null) {
    line = `Learned ${fmtDate(style.learned)} from ${style.sampledWords.toLocaleString()} words of your prose.`;
    if (style.stale) line += ` Your manuscript has grown to ${style.manuscriptWords.toLocaleString()} words since; relearn to keep up.`;
  } else if (style.exists) {
    line = "You have a style guide. Relearn it from your scenes, or edit it by hand.";
  } else {
    line = enough
      ? "Chisel writes in a generic voice until it learns yours from your scenes."
      : "Write a few hundred words first; then Chisel can learn your voice from them.";
  }
  return (
    <section className={"lw-insight" + (style.stale || !style.exists ? " lw-insight--nudge" : "")} aria-label="Your style">
      <div className="lw-insight__heading">
        <span className="lw-row lw-gap-6">
          <Icon icon={Feather} size={14} stroke={1.7} color="var(--lw-accent-text)" />
          <strong>Your style</strong>
        </span>
        {style.stale && <Tag>Out of date</Tag>}
      </div>
      <p>{line}</p>
      <div className="lw-row lw-gap-8">
        <button className="lw-btn lw-btn--grow" disabled={props.busy || !props.aiReady || !enough} onClick={props.onLearn}
          title="Read your scenes and propose a style guide; nothing is saved until you review it">
          <Icon icon={Feather} size={14} stroke={1.8} /> {style.learned || style.exists ? "Relearn my style" : "Learn my style"}
        </button>
        {style.exists && <button className="lw-btn" onClick={props.onOpen}>Open guide</button>}
      </div>
    </section>
  );
}
