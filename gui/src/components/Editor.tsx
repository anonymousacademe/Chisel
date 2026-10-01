import { Fragment, type RefObject } from "react";
import {
  FileText, LayoutDashboard, ListTree, Undo2, Redo2, Bold, Italic, Link, MessageSquarePlus,
  Focus, ChevronRight, BookPlus, type LucideIcon,
} from "lucide-react";
import type { DocumentPayload, PartSummary, SceneMention, SceneSummary, Unit } from "../data/types";
import { fmt } from "../data/tree";
import { Icon, IconButton, SectionLabel, Tag } from "./primitives";
import { EditorPane, type EditorHandle } from "./EditorPane";
import type { Card, CursorInfo, SpellTarget } from "../editor/cm";
import type { Span } from "../editor/spans";
import { titleLine } from "../editor/spans";
import type { SaveState } from "../editor/saveController";
import { sceneGroups, type MovePlan } from "../data/reorder";
import { Corkboard, Outline, type BoardFilter } from "./Board";

export type ViewMode = "manuscript" | "corkboard" | "outline";

const modes: { id: ViewMode; icon: LucideIcon; label: string }[] = [
  { id: "manuscript", icon: FileText, label: "Manuscript" },
  { id: "corkboard", icon: LayoutDashboard, label: "Corkboard" },
  { id: "outline", icon: ListTree, label: "Outline" },
];

export function Editor(props: {
  doc: DocumentPayload | null; scenes: SceneSummary[]; parts: PartSummary[]; unit: Unit; words: number; mentions: SceneMention[]; reflow: boolean;
  sessionWords: number; sessionMinutes: number;
  mode: ViewMode; onMode: (m: ViewMode) => void;
  /** Open the scene details dialog (status, POV, place, purpose, target). */
  onEditDetails: () => void;
  /** A card or row was dropped somewhere new: the host confirms and moves it. */
  onMoveRequest: (plan: MovePlan) => void;
  /** Collection filter: only these scenes show on the corkboard and outline. */
  filter: BoardFilter | null;
  /** The open scene's collections (inspector) and the dialog that changes them. */
  onEditCollections: () => void;
  focus: boolean; onFocus: () => void; onOpen: (id: string) => void;
  // editing
  editorRef: RefObject<EditorHandle | null>; docRev: number; spansVersion: number;
  cursor: CursorInfo; saveState: SaveState;
  onChange: (text: string) => void; onCursor: (c: CursorInfo) => void; onBlur: () => void; onSaveNow: () => void;
  onReload: () => void; onKeepMine: () => void; onMakeNote: () => void;
  getCard: (span: Span) => Promise<Card | null>; onOpenEntity: (span: Span) => void;
  onResolveDraft: (index: number, accept: boolean) => void;
  spellVersion: number; onSpellCount: (count: number | null) => void; onSpell: (t: SpellTarget) => void;
  onAddPhrase: () => void;
  extraKeys?: { key: string; run: () => boolean }[];
}) {
  const { doc, editorRef } = props;
  const isScene = doc?.kind === "scene";
  const d = doc?.details;
  const groups = sceneGroups(props.scenes, props.parts, { unplaced: true });
  const sentence = (s: string) => s[0] + s.slice(1).toLowerCase();
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
          <IconButton icon={Undo2} label="Undo" disabled={!doc || !props.cursor.canUndo} onMouseDown={(e) => e.preventDefault()} onClick={() => editorRef.current?.undo()} />
          <IconButton icon={Redo2} label="Redo" disabled={!doc || !props.cursor.canRedo} onMouseDown={(e) => e.preventDefault()} onClick={() => editorRef.current?.redo()} />
          <span className="lw-tool-sep" />
          <IconButton icon={Bold} label="Bold (Markdown **)" disabled={!doc} onMouseDown={(e) => e.preventDefault()} onClick={() => editorRef.current?.bold()} />
          <IconButton icon={Italic} label="Italic (Markdown *)" disabled={!doc} onMouseDown={(e) => e.preventDefault()} onClick={() => editorRef.current?.italic()} />
          <IconButton icon={Link} label="Make a note from the selection (Ctrl J)" disabled={doc?.kind !== "scene"} onMouseDown={(e) => e.preventDefault()} onClick={props.onMakeNote} />
          <IconButton icon={BookPlus} label="Add the selected word or phrase to the dictionary" disabled={doc?.kind !== "scene" || props.cursor.from === props.cursor.to}
            onMouseDown={(e) => e.preventDefault()} onClick={props.onAddPhrase} />
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
            <span className="lw-breadcrumb__current">{doc.kind === "scene" ? sentence(doc.kicker) : doc.title}</span>
          </>}
        </div>
        <div className="lw-row lw-gap-6">
          {isScene && (
            <Tag onClick={props.onEditDetails} title="Edit status and details">{d?.status ? d.status[0].toUpperCase() + d.status.slice(1) : "No status"}</Tag>
          )}
          {isScene && (
            <button className="lw-target lw-target--button" onClick={props.onEditDetails} title="Set the word target">
              <span className="lw-dot" />
              <span className="lw-mono">{d?.target ? `${fmt(props.words)} / ${fmt(d.target)} words` : `${fmt(props.words)} words`}</span>
            </button>
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
                  {(doc.kind === "entity" || !titleLine(doc.text, doc.bodyStart ?? 0)) && (
                    <>
                      <h1 className="lw-page__title">{doc.title}</h1>
                      {meta && <span className="lw-page__meta">{meta}</span>}
                      <span className="lw-page__rule" />
                    </>
                  )}
                </header>
                <EditorPane key={`${doc.id}:${props.docRev}`} ref={editorRef} docId={doc.id} kind={doc.kind}
                  initialText={doc.text} meta={meta} reflow={props.reflow} spansVersion={props.spansVersion}
                  spellVersion={props.spellVersion} onSpellCount={props.onSpellCount} onSpell={props.onSpell}
                  onChange={props.onChange} onCursor={props.onCursor} onBlur={props.onBlur} onSaveNow={props.onSaveNow}
                  getCard={props.getCard} onOpenEntity={props.onOpenEntity} onResolveDraft={props.onResolveDraft} extraKeys={props.extraKeys} />
              </article>
            ) : <p className="lw-empty lw-empty--page">Open a scene from the binder to start writing.</p>}
          </div>
        )}

        {props.mode === "corkboard" && (
          <Corkboard groups={groups} filter={props.filter} activeId={doc?.id ?? null} unit={props.unit} onOpen={props.onOpen} onMove={props.onMoveRequest} />
        )}

        {props.mode === "outline" && (
          <Outline groups={groups} filter={props.filter} activeId={doc?.id ?? null} unit={props.unit} onOpen={props.onOpen} onMove={props.onMoveRequest} />
        )}
      </div>

      <div className="lw-divider" />
      <footer className="lw-inspector">
        {[
          { label: "Status", value: d?.status || "—", edit: props.onEditDetails },
          { label: "POV / Place", value: [d?.pov, d?.place].filter(Boolean).join(" · ") || "—", edit: props.onEditDetails },
          { label: `${props.unit[0].toUpperCase()}${props.unit.slice(1)} purpose`, value: d?.purpose || "—", edit: props.onEditDetails },
          { label: "Collections", value: d?.collections.join(", ") || "—", edit: props.onEditCollections },
          { label: "Session", value: session, accent: true },
        ].map((m, i) => (
          <Fragment key={m.label}>
            {i > 0 && <span className="lw-inspector__divider" />}
            {m.edit && isScene ? (
              <button className="lw-metric lw-metric--button" onClick={m.edit} title={m.label === "Collections" ? "Choose this scene's collections" : "Edit scene details"}>
                <SectionLabel>{m.label}</SectionLabel>
                <span className="lw-metric__value">{m.value}</span>
              </button>
            ) : (
              <div className="lw-metric">
                <SectionLabel>{m.label}</SectionLabel>
                <span className={`lw-metric__value${m.accent ? " is-accent" : ""}`}>{m.edit ? "—" : m.value}</span>
              </div>
            )}
          </Fragment>
        ))}
      </footer>
    </main>
  );
}
