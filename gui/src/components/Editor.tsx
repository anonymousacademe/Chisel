import { Fragment, type RefObject } from "react";
import {
  FileText, LayoutDashboard, ListTree, Undo2, Redo2, Bold, Italic, Link, MessageSquarePlus,
  Focus, ChevronRight, type LucideIcon,
} from "lucide-react";
import type { DocumentPayload, SceneMention, SceneSummary } from "../data/types";
import { fmt } from "../data/tree";
import { Icon, IconButton, SectionLabel, Tag } from "./primitives";
import { EditorPane, type EditorHandle } from "./EditorPane";
import type { Card, CursorInfo } from "../editor/cm";
import type { Span } from "../editor/spans";
import { titleLine } from "../editor/spans";
import type { SaveState } from "../editor/saveController";
import { placeholderProps } from "./placeholder";

export type ViewMode = "manuscript" | "corkboard" | "outline";

const modes: { id: ViewMode; icon: LucideIcon; label: string }[] = [
  { id: "manuscript", icon: FileText, label: "Manuscript" },
  { id: "corkboard", icon: LayoutDashboard, label: "Corkboard" },
  { id: "outline", icon: ListTree, label: "Outline" },
];

export function Editor(props: {
  doc: DocumentPayload | null; scenes: SceneSummary[]; words: number; mentions: SceneMention[]; reflow: boolean;
  sessionWords: number; sessionMinutes: number;
  mode: ViewMode; onMode: (m: ViewMode) => void;
  focus: boolean; onFocus: () => void; onOpen: (id: string) => void;
  // editing
  editorRef: RefObject<EditorHandle | null>; docRev: number; spansVersion: number;
  cursor: CursorInfo; saveState: SaveState;
  onChange: (text: string) => void; onCursor: (c: CursorInfo) => void; onBlur: () => void; onSaveNow: () => void;
  onReload: () => void; onKeepMine: () => void; onMakeNote: () => void;
  getCard: (span: Span) => Promise<Card | null>; onOpenEntity: (span: Span) => void;
  onResolveDraft: (index: number, accept: boolean) => void;
  extraKeys?: { key: string; run: () => boolean }[];
}) {
  const { doc } = props;
  const names = props.mentions.map((m) => m.name);
  const meta = names.length > 4 ? `${names.slice(0, 4).join(" · ")} · +${names.length - 4}` : names.join(" · ");
  const session = `${props.sessionWords >= 0 ? "+" : "−"}${fmt(Math.abs(props.sessionWords))} words · ${props.sessionMinutes} min`;

  return (
    <main className="lw-editor">
      <div className="lw-editor__toolbar">
        <div className="lw-row lw-gap-4" role="tablist" aria-label="View mode">
          {modes.map((m) => (
            <button key={m.id} role="tab" aria-selected={props.mode === m.id}
              className={`lw-viewmode${props.mode === m.id ? " is-active" : ""}`} onClick={() => props.onMode(m.id)}>
              <Icon icon={m.icon} size={14} />
              <span>{m.label}</span>
            </button>
          ))}
        </div>
        <div className="lw-row lw-gap-4">
          <IconButton icon={Undo2} label="Undo" disabled={!doc || !props.cursor.canUndo} onMouseDown={(e) => e.preventDefault()} onClick={() => props.editorRef.current?.undo()} />
          <IconButton icon={Redo2} label="Redo" disabled={!doc || !props.cursor.canRedo} onMouseDown={(e) => e.preventDefault()} onClick={() => props.editorRef.current?.redo()} />
          <span className="lw-tool-sep" />
          <IconButton icon={Bold} label="Bold (Markdown **)" disabled={!doc} onMouseDown={(e) => e.preventDefault()} onClick={() => props.editorRef.current?.bold()} />
          <IconButton icon={Italic} label="Italic (Markdown *)" disabled={!doc} onMouseDown={(e) => e.preventDefault()} onClick={() => props.editorRef.current?.italic()} />
          <IconButton icon={Link} label="Make a note from the selection (Ctrl J)" disabled={doc?.kind !== "scene"} onMouseDown={(e) => e.preventDefault()} onClick={props.onMakeNote} />
          <IconButton icon={MessageSquarePlus} label="Add comment" placeholder />
          <span className="lw-tool-sep" />
          <IconButton icon={Focus} label="Focus mode" active={props.focus} onClick={props.onFocus} />
        </div>
      </div>

      <div className="lw-editor__context">
        <div className="lw-row lw-gap-6 lw-breadcrumb">
          {doc && <>
            <span className="lw-faint">{doc.parent}</span>
            <Icon icon={ChevronRight} size={11} stroke={1.5} color="var(--lw-text-faint)" />
            <span className="lw-breadcrumb__current">{doc.kind === "scene" ? doc.kicker.replace("SCENE", "Scene") : doc.title}</span>
          </>}
        </div>
        <div className="lw-row lw-gap-6">
          <Tag placeholder>No status</Tag>
          {doc?.kind === "scene" && (
            <span className="lw-target">
              <span className="lw-dot" />
              <span className="lw-mono">{fmt(props.words)} words <span {...placeholderProps}>/ —</span></span>
            </span>
          )}
        </div>
      </div>

      {props.saveState === "conflict" && (
        <div className="lw-conflict" role="alert">
          <span>This file changed on disk while you were editing it (the terminal app may be open on the same project).</span>
          <button className="lw-btn" onClick={props.onReload}>Reload from disk</button>
          <button className="lw-btn" onClick={props.onKeepMine}>Keep my version</button>
        </div>
      )}
      <div className="lw-editor__surface">
        {props.mode === "manuscript" && (
          <div className="lw-editor__scroll">
            {doc ? (
              <article className="lw-page">
                <header className="lw-page__heading">
                  <span className="lw-page__number">{doc.kicker}</span>
                  {(doc.kind === "entity" || !titleLine(doc.text)) && (
                    <>
                      <h1 className="lw-page__title">{doc.title}</h1>
                      {meta && <span className="lw-page__meta">{meta}</span>}
                      <span className="lw-page__rule" />
                    </>
                  )}
                </header>
                <EditorPane key={`${doc.id}:${props.docRev}`} ref={props.editorRef} docId={doc.id} kind={doc.kind}
                  initialText={doc.text} meta={meta} reflow={props.reflow} spansVersion={props.spansVersion}
                  onChange={props.onChange} onCursor={props.onCursor} onBlur={props.onBlur} onSaveNow={props.onSaveNow}
                  getCard={props.getCard} onOpenEntity={props.onOpenEntity} onResolveDraft={props.onResolveDraft} extraKeys={props.extraKeys} />
              </article>
            ) : <p className="lw-empty lw-empty--page">Open a scene from the binder to start writing.</p>}
          </div>
        )}

        {props.mode === "corkboard" && (
          <div className="lw-cork">
            <p className="lw-cork__hint" {...placeholderProps}>Drag cards to reorder (use the binder menu to move a scene for now)</p>
            {props.scenes.map((s) => (
              <button key={s.id} className={`lw-card${s.id === doc?.id ? " is-active" : ""}`} onClick={() => props.onOpen(s.id)}>
                <span className="lw-card__kicker">{s.number ? `SCENE ${s.number}` : "SCENE"}</span>
                <span className="lw-card__title">{s.title}</span>
                <span className="lw-card__excerpt">{s.excerpt}</span>
                <span className="lw-mono lw-faint">{fmt(s.words)} words</span>
              </button>
            ))}
            {props.scenes.length === 0 && <p className="lw-empty">No scenes yet.</p>}
          </div>
        )}

        {props.mode === "outline" && (
          <ol className="lw-outline">
            {props.scenes.map((s) => (
              <li key={s.id}>
                <button className={s.id === doc?.id ? "is-active" : undefined} onClick={() => props.onOpen(s.id)}>
                  <span>{s.number ? `${s.number}  ` : ""}{s.title}</span><span className="lw-mono lw-faint">{fmt(s.words)}</span>
                </button>
                {s.headings.length > 0 && (
                  <ul className="lw-outline__headings">
                    {s.headings.map((h, i) => <li key={i}>{h}</li>)}
                  </ul>
                )}
              </li>
            ))}
            {props.scenes.length === 0 && <p className="lw-empty">No scenes yet.</p>}
          </ol>
        )}
      </div>

      <div className="lw-divider" />
      <footer className="lw-inspector">
        {[
          { label: "Status", value: "—", ph: true },
          { label: "POV / Place", value: "—", ph: true },
          { label: "Scene purpose", value: "—", ph: true },
          { label: "Session", value: session, accent: true },
        ].map((m, i) => (
          <Fragment key={m.label}>
            {i > 0 && <span className="lw-inspector__divider" />}
            <div className="lw-metric" {...(m.ph ? placeholderProps : {})}>
              <SectionLabel>{m.label}</SectionLabel>
              <span className={`lw-metric__value${m.accent ? " is-accent" : ""}`}>{m.value}</span>
            </div>
          </Fragment>
        ))}
      </footer>
    </main>
  );
}
