import { useEffect, useRef, useState } from "react";
import { Check, CornerUpLeft, MessageSquareText, Trash2 } from "lucide-react";
import type { CommentRow } from "../data/types";
import { Icon, IconButton, SectionLabel } from "./primitives";
import { ConfirmDialog, Modal } from "./Dialogs";

const when = (iso: string) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
};
const snippet = (s: string, n = 90) => { const t = s.replace(/\s+/g, " ").trim(); return t.length <= n ? t : `${t.slice(0, n - 1)}…`; };

/** Write a new comment on the selected passage. Comments live beside the scene, never in its text. */
export function AddCommentDialog({ quote, onAdd, onClose }: { quote: string; onAdd: (body: string) => void; onClose: () => void }) {
  const [body, setBody] = useState("");
  const submit = () => { if (body.trim()) onAdd(body.trim()); };
  return (
    <Modal title="Add comment" onClose={onClose}>
      <p className="lw-comment-quote">“{snippet(quote, 160)}”</p>
      <label className="lw-dialog__label">Your note
        <textarea autoFocus className="lw-launch__input lw-details__purpose" rows={4} value={body} placeholder="A note to yourself about this passage"
          onChange={(e) => setBody(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submit(); }} />
      </label>
      <p className="lw-dialog__message lw-faint">Saved in <code>.comments/</code> next to the scene. It is not part of the text, is not spell-checked and is not sent to the AI unless you attach it to a chat.</p>
      <div className="lw-dialog__buttons">
        <button className="lw-btn" onClick={onClose}>Cancel</button>
        <button className="lw-btn lw-btn--primary" disabled={!body.trim()} onClick={submit}>Add comment</button>
      </div>
    </Modal>
  );
}

/** The popover for one comment: edit, resolve / reopen, delete. */
export function CommentPopover({ comment, x, y, onSave, onResolve, onDelete, onClose }: {
  comment: CommentRow; x: number; y: number;
  onSave: (body: string) => void; onResolve: (resolved: boolean) => void; onDelete: () => void; onClose: () => void;
}) {
  const [body, setBody] = useState(comment.body);
  const [ask, setAsk] = useState(false);
  const area = useRef<HTMLTextAreaElement>(null);
  useEffect(() => { area.current?.focus(); }, []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape" && !ask) onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, ask]);
  const dirty = body.trim() !== comment.body && body.trim() !== "";
  const top = Math.max(8, Math.min(y + 8, window.innerHeight - 260));
  const left = Math.max(8, Math.min(x, window.innerWidth - 340));
  if (ask) {
    return (
      <ConfirmDialog title="Delete comment" confirm="Delete comment" message="Delete this comment? The text it is about is not touched."
        onConfirm={onDelete} onClose={() => setAsk(false)} />
    );
  }
  return (
    <div className="lw-overlay lw-overlay--clear" onMouseDown={() => { if (dirty) onSave(body.trim()); else onClose(); }}>
      <div className="lw-comment-pop" role="dialog" aria-label="Comment" style={{ top, left }} onMouseDown={(e) => e.stopPropagation()}>
        <div className="lw-comment-pop__head">
          <span className="lw-row lw-gap-6"><Icon icon={MessageSquareText} size={13} stroke={1.7} color="var(--lw-warning)" />
            <strong>Comment</strong><span className="lw-faint">{when(comment.created)}{comment.resolved ? " · resolved" : ""}</span></span>
        </div>
        <p className="lw-comment-quote">“{snippet(comment.quote, 140)}”</p>
        <textarea ref={area} className="lw-launch__input lw-details__purpose" rows={4} value={body} aria-label="Comment text"
          onChange={(e) => setBody(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && dirty) onSave(body.trim()); }} />
        <div className="lw-row lw-gap-6 lw-comment-pop__buttons">
          <button className="lw-btn lw-btn--primary" disabled={!dirty} onClick={() => onSave(body.trim())}>Save</button>
          <button className="lw-btn" onClick={() => onResolve(!comment.resolved)}>
            <Icon icon={comment.resolved ? CornerUpLeft : Check} size={13} stroke={1.8} /> {comment.resolved ? "Reopen" : "Resolve"}
          </button>
          <span className="lw-grow" />
          <IconButton icon={Trash2} label="Delete comment" onClick={() => setAsk(true)} />
        </div>
      </div>
    </div>
  );
}

/** The Notes tab's comments list: detached first, then top to bottom; resolved ones folded below. */
export function CommentsPanel({ comments, onOpen, onResolve }: {
  comments: CommentRow[] | null; onOpen: (c: CommentRow) => void; onResolve: (c: CommentRow, resolved: boolean) => void;
}) {
  const [showDone, setShowDone] = useState(false);
  if (comments === null) return null;
  const open = comments.filter((c) => !c.resolved);
  const done = comments.filter((c) => c.resolved);
  const row = (c: CommentRow) => (
    <div key={c.id} className={`lw-commentrow${c.detached ? " is-detached" : ""}${c.resolved ? " is-done" : ""}`}>
      <button className="lw-commentrow__main" onClick={() => onOpen(c)}
        title={c.detached ? "The passage is no longer in the text" : "Jump to the passage"}>
        <span className="lw-commentrow__quote">{c.detached && <em>Detached · </em>}“{snippet(c.quote, 70)}”</span>
        <span className="lw-commentrow__body">{snippet(c.body, 160)}</span>
        <span className="lw-mono lw-faint">{when(c.created)}{c.row !== null ? ` · line ${c.row + 1}` : ""}</span>
      </button>
      <IconButton icon={c.resolved ? CornerUpLeft : Check} label={c.resolved ? "Reopen" : "Resolve"} small onClick={() => onResolve(c, !c.resolved)} />
    </div>
  );
  return (
    <section className="lw-comments" aria-label="Comments">
      <SectionLabel>Comments · {open.length}</SectionLabel>
      {open.length === 0 && <p className="lw-empty">No comments on this scene. Select a passage and use the comment button above the page.</p>}
      {open.map(row)}
      {done.length > 0 && (
        <>
          <button className="lw-link" onClick={() => setShowDone((s) => !s)}>{showDone ? "Hide" : "Show"} resolved ({done.length})</button>
          {showDone && done.map(row)}
        </>
      )}
    </section>
  );
}
