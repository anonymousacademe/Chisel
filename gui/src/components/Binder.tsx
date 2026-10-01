import {
  FilePlus2, Ellipsis, ChevronDown, ChevronRight, BookOpen, Folder, FolderOpen, FileText,
  FilePenLine, Users, Globe2, BookMarked, Inbox, Trash2, ScrollText, SpellCheck, type LucideIcon,
} from "lucide-react";
import { useState } from "react";
import type { BinderNode, CollectionSummary } from "../data/types";
import { allIds, filterByIds, filterTree, isActionable, isOpenable } from "../data/tree";
import { memberIds, swatchVar } from "../data/collections";
import { Icon, IconButton, SectionLabel } from "./primitives";
import { placeholderProps } from "./placeholder";

function nodeIcon(node: BinderNode, open: boolean, active: boolean): LucideIcon {
  if (active) return FilePenLine;
  switch (node.kind) {
    case "project": return BookOpen;
    case "folder": case "part": return open ? FolderOpen : Folder;
    case "characters": return Users;
    case "world": return Globe2;
    case "style": return ScrollText;
    case "dictionary": return SpellCheck;
    case "research": return BookMarked;
    case "inbox": return Inbox;
    case "trash": return Trash2;
    default: return FileText;
  }
}

function Row({ node, depth, activeId, focusId, expanded, onToggle, onSelect }: {
  node: BinderNode; depth: number; activeId: string | null; focusId: string | null;
  expanded: Set<string>; onToggle: (id: string) => void; onSelect: (n: BinderNode) => void;
}) {
  const ph = !!node.placeholder;
  const hasChildren = node.children !== undefined && !ph;
  const open = expanded.has(node.id);
  const active = node.id === activeId;
  const cls = `lw-binder__item${active ? " is-active" : ""}${node.muted ? " is-muted" : ""}${node.id === focusId ? " is-focus" : ""}`;
  const activate = () => (isOpenable(node) || isActionable(node) ? onSelect(node) : hasChildren && onToggle(node.id));
  return (
    <>
      <div role="treeitem" aria-selected={active} aria-expanded={hasChildren ? open : undefined}
        tabIndex={ph ? -1 : active ? 0 : -1} className={cls} style={{ paddingLeft: 8 + depth * 16 }}
        {...(ph ? placeholderProps : {
          onClick: activate,
          onKeyDown: (e: React.KeyboardEvent) => {
            if (e.key === "Enter") activate();
            if (e.key === "ArrowRight" && hasChildren && !open) onToggle(node.id);
            if (e.key === "ArrowLeft" && hasChildren && open) onToggle(node.id);
          },
        })}>
        {hasChildren ? (
          <button className="lw-binder__disclosure" aria-label={open ? "Collapse" : "Expand"}
            onClick={(e) => { e.stopPropagation(); onToggle(node.id); }}>
            <Icon icon={open ? ChevronDown : ChevronRight} size={11} stroke={1.8} />
          </button>
        ) : ph && node.kind === "folder"
          ? <span className="lw-binder__disclosure" aria-hidden><Icon icon={ChevronRight} size={11} stroke={1.8} /></span>
          : <span className="lw-binder__disclosure" aria-hidden />}
        <Icon icon={nodeIcon(node, open, active)} size={14} stroke={1.5} className="lw-binder__icon" />
        <span className="lw-binder__title" title={ph ? undefined : node.title}>{node.title}</span>
        {node.meta && <span className="lw-binder__meta">{node.meta}</span>}
      </div>
      {hasChildren && open && node.children!.map((c) => (
        <Row key={c.id} node={c} depth={depth + 1} activeId={activeId} focusId={focusId} expanded={expanded} onToggle={onToggle} onSelect={onSelect} />
      ))}
    </>
  );
}

const LIBRARY_KINDS = new Set(["characters", "world", "style", "dictionary"]);

export function Binder({ nodes, count, activeId, focusId, unit, expanded, onToggle, onSelect, onNew, onMenu, searching, library, canNew, canMenu, collections, activeCollection, onCollection, onEditCollections }: {
  searching: boolean; library: boolean; canNew: boolean; canMenu: boolean;
  collections: CollectionSummary[]; activeCollection: string | null;
  /** Click a collection to show only its scenes; click it again (or Show all) to clear. */
  onCollection: (name: string | null) => void; onEditCollections: () => void;
  nodes: BinderNode[]; count: number; activeId: string | null;
  /** The part folder last clicked: part actions in the menu apply to it. */
  focusId: string | null; unit: string;
  expanded: Set<string>; onToggle: (id: string) => void; onSelect: (n: BinderNode) => void;
  onNew: () => void; onMenu: (anchor: HTMLElement) => void;
}) {
  const [query, setQuery] = useState("");
  const q = searching ? query.trim().toLowerCase() : "";
  const members = library ? null : memberIds(collections, activeCollection);
  const all = library ? nodes.filter((n) => LIBRARY_KINDS.has(n.kind)) : nodes;
  const base = members ? filterByIds(all, members) : all;
  const shown = q ? filterTree(base, q) : base;
  const open = q || members ? allIds(shown) : library ? new Set([...expanded, ...allIds(base)]) : expanded;
  return (
    <aside className="lw-binder" aria-label={library ? "Library" : "Manuscript binder"}>
      <div className="lw-binder__header">
        <div className="lw-binder__heading">
          <h2>{library ? "Library" : "Binder"}</h2>
          <span className="lw-mono lw-faint">{count}</span>
        </div>
        <div className="lw-row lw-gap-4">
          <IconButton icon={FilePlus2} label={library ? "New note" : `New ${unit}`} onClick={onNew} disabled={!canNew} />
          <IconButton icon={Ellipsis} label={`${unit[0].toUpperCase()}${unit.slice(1)} and part options`} onClick={(e) => onMenu(e.currentTarget)} disabled={!canMenu} />
        </div>
      </div>
      <div className="lw-divider" />
      {searching && (
        <div className="lw-binder__search">
          <input autoFocus value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Filter binder…" aria-label="Filter binder" />
        </div>
      )}
      {members && (
        <div className="lw-binder__filter">
          <span>Only “{activeCollection}” · {members.size}</span>
          <button className="lw-link" onClick={() => onCollection(null)}>Show all</button>
        </div>
      )}
      <div className="lw-binder__tree" role="tree">
        {shown.map((n) => (
          <Row key={n.id} node={n} depth={0} activeId={activeId} focusId={focusId} expanded={open} onToggle={onToggle} onSelect={onSelect} />
        ))}
        {q && shown.length === 0 && <p className="lw-empty">Nothing matches “{query}”.</p>}
      </div>
      <div className="lw-divider" />
      <section className="lw-collections">
        <div className="lw-collections__heading">
          <SectionLabel>Collections</SectionLabel>
          <button className="lw-link" onClick={onEditCollections}>Edit</button>
        </div>
        {collections.length === 0 && <p className="lw-empty">No collections yet.</p>}
        {collections.map((c) => (
          <button key={c.name} className={`lw-collections__row${c.name === activeCollection ? " is-active" : ""}`} aria-pressed={c.name === activeCollection}
            title={c.name === activeCollection ? "Show all again" : `Show only the ${unit}s in “${c.name}”`}
            onClick={() => onCollection(c.name === activeCollection ? null : c.name)}>
            <span className="lw-collections__swatch" style={{ background: swatchVar(c.color) }} />
            <span className="lw-collections__title">{c.name}</span>
            <span className="lw-mono lw-faint">{c.count}</span>
          </button>
        ))}
      </section>
    </aside>
  );
}
