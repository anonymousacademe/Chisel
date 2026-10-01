import { useMemo, useState } from "react";
import { Check, FileText, MessageSquareText, NotebookText, Trash2, UserRound, BookMarked } from "lucide-react";
import type { AttachItem, AttachKind, ChatSummary } from "../data/types";
import { attachKey, type Attachment } from "../data/chat";
import { Icon, IconButton } from "./primitives";
import { ConfirmDialog, Modal } from "./Dialogs";

const KIND_LABEL: Record<AttachKind, string> = { scene: "Scenes", comments: "Comments", note: "Notes", research: "Research" };
const KIND_ORDER: AttachKind[] = ["scene", "comments", "note", "research"];
const KIND_ICON = { scene: FileText, comments: MessageSquareText, note: UserRound, research: BookMarked } as const;
const fmtWords = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n));

/** Pick scenes, notes, research notes and comments to add to the chat's context (capped, removable). */
export function AttachDialog({ items, current, maxWords, maxItems, onSave, onClose }: {
  items: AttachItem[]; current: Attachment[]; maxWords: number; maxItems: number;
  onSave: (picked: Attachment[]) => void; onClose: () => void;
}) {
  const [picked, setPicked] = useState(() => new Map(current.map((a) => [attachKey(a), a])));
  const [query, setQuery] = useState("");
  const total = [...picked.values()].reduce((n, a) => n + a.words, 0);
  const over = total > maxWords || picked.size > maxItems;
  const q = query.trim().toLowerCase();
  const shown = useMemo(() => items.filter((i) => !q || i.title.toLowerCase().includes(q)), [items, q]);
  const flip = (i: AttachItem) => setPicked((m) => {
    const n = new Map(m);
    const key = attachKey(i);
    if (n.has(key)) n.delete(key); else n.set(key, { kind: i.kind, id: i.id, title: i.title, words: i.words });
    return n;
  });
  return (
    <Modal title="Attach to this chat" wide onClose={onClose}>
      <p className="lw-dialog__message">The assistant reads what you attach, along with the question. Comments are shared only this way.</p>
      <input autoFocus className="lw-launch__input" placeholder="Filter…" aria-label="Filter attachments" value={query} onChange={(e) => setQuery(e.target.value)} />
      <div className="lw-picklist lw-picklist--tall" role="group" aria-label="Attachable items">
        {shown.length === 0 && <p className="lw-empty">Nothing matches.</p>}
        {KIND_ORDER.map((kind) => {
          const rows = shown.filter((i) => i.kind === kind);
          if (!rows.length) return null;
          return (
            <div key={kind} className="lw-attach-group">
              <span className="lw-attach-group__label">{KIND_LABEL[kind]}</span>
              {rows.map((i) => (
                <label key={attachKey(i)} className="lw-picklist__row lw-collections__check">
                  <input type="checkbox" checked={picked.has(attachKey(i))} onChange={() => flip(i)} />
                  <Icon icon={KIND_ICON[kind]} size={13} stroke={1.5} />
                  <span className="lw-picklist__main">{i.title}{kind === "comments" && i.count ? ` · ${i.count} open` : ""}</span>
                  <span className="lw-mono lw-faint">{fmtWords(i.words)} words</span>
                </label>
              ))}
            </div>
          );
        })}
      </div>
      <p className={`lw-dialog__message${over ? " lw-details__error" : " lw-faint"}`}>
        {picked.size} attached · about {fmtWords(total)} of {fmtWords(maxWords)} words{over ? ". Too much: remove something (at most " + maxItems + " items)." : ""}
      </p>
      <div className="lw-dialog__buttons">
        <button className="lw-btn" onClick={onClose}>Cancel</button>
        <button className="lw-btn lw-btn--primary" disabled={over} onClick={() => onSave([...picked.values()])}>Attach</button>
      </div>
    </Modal>
  );
}

const when = (iso: string) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
};

/** Past conversations: open, rename, delete; or start a new one. */
export function ChatHistoryDialog({ chats, currentId, onOpen, onNew, onRename, onDelete, onClose }: {
  chats: ChatSummary[] | null; currentId: string | null;
  onOpen: (id: string) => void; onNew: () => void;
  onRename: (id: string, title: string) => Promise<boolean>; onDelete: (id: string) => Promise<boolean>; onClose: () => void;
}) {
  const [editing, setEditing] = useState<{ id: string; value: string } | null>(null);
  const [ask, setAsk] = useState<ChatSummary | null>(null);
  const commit = async () => {
    if (!editing) return;
    const row = chats?.find((c) => c.id === editing.id);
    if (!editing.value.trim() || editing.value.trim() === row?.title || (await onRename(editing.id, editing.value.trim()))) setEditing(null);
  };
  if (ask) {
    return (
      <ConfirmDialog title="Delete conversation" confirm="Delete conversation"
        message={<>Delete “{ask.title}” ({ask.count} messages)? Replies you saved to notes stay in your research notes.</>}
        onConfirm={() => { const c = ask; setAsk(null); void onDelete(c.id); }} onClose={() => setAsk(null)} />
    );
  }
  return (
    <Modal title="Conversations" wide onClose={onClose}>
      <p className="lw-dialog__message">Your assistant chats are kept with the project (<code>.assistant/chats/</code>).</p>
      <div className="lw-picklist lw-picklist--tall">
        {chats === null && <p className="lw-empty">Loading…</p>}
        {chats?.length === 0 && <p className="lw-empty">No saved conversations yet. A chat is saved after the assistant answers.</p>}
        {chats?.map((c) => (
          <div key={c.id} className={`lw-picklist__row lw-picklist__row--static${c.id === currentId ? " is-current" : ""}`}>
            <span className="lw-picklist__main">
              {editing?.id === c.id ? (
                <input autoFocus className="lw-launch__input" aria-label={`New title for ${c.title}`} value={editing.value}
                  onChange={(e) => setEditing({ id: c.id, value: e.target.value })}
                  onKeyDown={(e) => { if (e.key === "Enter") void commit(); else if (e.key === "Escape") { e.stopPropagation(); setEditing(null); } }}
                  onBlur={() => void commit()} />
              ) : (
                <button className="lw-link lw-collections__name" title="Open this conversation" onClick={() => onOpen(c.id)}>{c.title}</button>
              )}
              <span className="lw-faint">{when(c.updated)} · {c.count} messages{c.id === currentId ? " · open now" : ""}</span>
            </span>
            <span className="lw-row lw-gap-6">
              <button className="lw-btn" onClick={() => setEditing({ id: c.id, value: c.title })}>Rename</button>
              <IconButton icon={Trash2} label={`Delete ${c.title}`} onClick={() => setAsk(c)} />
            </span>
          </div>
        ))}
      </div>
      <div className="lw-dialog__buttons lw-dialog__buttons--split">
        <button className="lw-btn" onClick={onNew}><Icon icon={NotebookText} size={13} stroke={1.8} /> New chat</button>
        <button className="lw-btn" autoFocus onClick={onClose}><Icon icon={Check} size={13} stroke={1.8} /> Close</button>
      </div>
    </Modal>
  );
}
