import { Fragment, useRef, type KeyboardEvent } from "react";
import {
  FileText, LayoutDashboard, ListTree, Undo2, Redo2, Bold, Italic, Link, MessageSquarePlus,
  Focus, ChevronRight, MessageCircle, Sparkles, type LucideIcon,
} from "lucide-react";
import type { BinderNode, ManuscriptDocument } from "../data/types";
import { Icon, IconButton, SectionLabel, Tag } from "./primitives";

export type ViewMode = "manuscript" | "corkboard" | "outline";

const modes: { id: ViewMode; icon: LucideIcon; label: string }[] = [
  { id: "manuscript", icon: FileText, label: "Manuscript" },
  { id: "corkboard", icon: LayoutDashboard, label: "Corkboard" },
  { id: "outline", icon: ListTree, label: "Outline" },
];

const fmt = (n: number) => n.toLocaleString("en-US");
const exec = (cmd: string) => document.execCommand(cmd);

export function Editor(props: {
  doc: ManuscriptDocument; siblings: BinderNode[]; words: number;
  mode: ViewMode; onMode: (m: ViewMode) => void;
  focus: boolean; onFocus: () => void;
  onParagraph: (id: string, text: string) => void; onAppend: (text: string) => void;
  onSelect: (n: BinderNode) => void; onAskAssistant: () => void;
  commentOpen: boolean; onComment: () => void;
}) {
  const { doc } = props;
  const draftRef = useRef<HTMLDivElement>(null);

  const commitDraft = () => {
    const el = draftRef.current;
    const text = el?.innerText.trim();
    if (el && text) { props.onAppend(text); el.innerText = ""; }
  };
  const onDraftKey = (e: KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); commitDraft(); }
  };

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
          <IconButton icon={Undo2} label="Undo" onMouseDown={(e) => e.preventDefault()} onClick={() => exec("undo")} />
          <IconButton icon={Redo2} label="Redo" onMouseDown={(e) => e.preventDefault()} onClick={() => exec("redo")} />
          <span className="lw-tool-sep" />
          <IconButton icon={Bold} label="Bold" onMouseDown={(e) => e.preventDefault()} onClick={() => exec("bold")} />
          <IconButton icon={Italic} label="Italic" onMouseDown={(e) => e.preventDefault()} onClick={() => exec("italic")} />
          <IconButton icon={Link} label="Link to document" />
          <IconButton icon={MessageSquarePlus} label="Add comment" active={props.commentOpen} onClick={props.onComment} />
          <span className="lw-tool-sep" />
          <IconButton icon={Focus} label="Focus mode" active={props.focus} onClick={props.onFocus} />
        </div>
      </div>

      <div className="lw-editor__context">
        <div className="lw-row lw-gap-6 lw-breadcrumb">
          <span className="lw-faint">{doc.parentTitle}</span>
          <Icon icon={ChevronRight} size={11} stroke={1.5} color="var(--lw-text-faint)" />
          <span className="lw-breadcrumb__current">{doc.shortLabel}</span>
        </div>
        <div className="lw-row lw-gap-6">
          <Tag>{doc.status}</Tag>
          <span className="lw-target">
            <span className={`lw-dot${props.words >= doc.target * 0.75 ? " is-good" : " is-warn"}`} />
            <span className="lw-mono">{fmt(props.words)} / {fmt(doc.target)} words</span>
          </span>
        </div>
      </div>

      <div className="lw-editor__surface">
        {props.mode === "manuscript" && (
          <div className="lw-editor__scroll">
            <article className="lw-page">
              <header className="lw-page__heading">
                <span className="lw-page__number">{doc.number}</span>
                <h1 className="lw-page__title">{doc.title}</h1>
                <span className="lw-page__meta">{doc.sceneMeta}</span>
              </header>
              <span className="lw-page__rule" />
              <div className="lw-prose">
                {doc.paragraphs.map((p) => {
                  const body = (
                    <p key={p.id} className={p.revised ? "is-revised" : undefined} contentEditable suppressContentEditableWarning
                      spellCheck onBlur={(e) => props.onParagraph(p.id, e.currentTarget.innerText)}>{p.text}</p>
                  );
                  return p.revised
                    ? <div key={p.id} className="lw-revision"><span className="lw-revision__marker" />{body}</div>
                    : <Fragment key={p.id}>{body}</Fragment>;
                })}
                <div className="lw-insertion">
                  <span className="lw-caret" />
                  <div ref={draftRef} className="lw-insertion__input" contentEditable suppressContentEditableWarning
                    data-placeholder="Continue the scene…" onKeyDown={onDraftKey} onBlur={commitDraft} aria-label="Continue writing" />
                </div>
              </div>
            </article>
            <div className="lw-annotations" aria-label="Annotations">
              <button className={`lw-marker lw-marker--comment${props.commentOpen ? " is-open" : ""}`} aria-label="Comment on revised passage" onClick={props.onComment}>
                <Icon icon={MessageCircle} size={13} stroke={1.7} />
              </button>
              <button className="lw-marker lw-marker--ai" aria-label="Assistant suggestion" onClick={props.onAskAssistant}>
                <Icon icon={Sparkles} size={13} />
              </button>
            </div>
          </div>
        )}

        {props.mode === "corkboard" && (
          <div className="lw-cork">
            {props.siblings.map((s) => (
              <button key={s.id} className={`lw-card${s.id === doc.id ? " is-active" : ""}`} onClick={() => props.onSelect(s)}>
                <span className="lw-card__title">{s.title}</span>
                <span className="lw-mono lw-faint">{s.meta ?? ""}</span>
              </button>
            ))}
          </div>
        )}

        {props.mode === "outline" && (
          <ol className="lw-outline">
            {props.siblings.map((s) => (
              <li key={s.id}>
                <button className={s.id === doc.id ? "is-active" : undefined} onClick={() => props.onSelect(s)}>
                  <span>{s.title}</span><span className="lw-mono lw-faint">{s.meta ?? ""}</span>
                </button>
              </li>
            ))}
          </ol>
        )}
      </div>

      <div className="lw-divider" />
      <footer className="lw-inspector">
        {doc.inspector.map((m, i) => (
          <Fragment key={m.label}>
            {i > 0 && <span className="lw-inspector__divider" />}
            <div className="lw-metric">
              <SectionLabel>{m.label}</SectionLabel>
              <span className={`lw-metric__value${m.accent ? " is-accent" : ""}`}>{m.value}</span>
            </div>
          </Fragment>
        ))}
      </footer>
    </main>
  );
}
