import {
  FilePlus2, Ellipsis, ChevronDown, ChevronRight, BookOpen, Folder, FolderOpen, FileText,
  FilePenLine, FileClock, Users, Globe2, BookMarked, Inbox, Trash2, type LucideIcon,
} from "lucide-react";
import { useState } from "react";
import type { BinderNode, Collection } from "../data/types";
import { Icon, IconButton, SectionLabel } from "./primitives";

function nodeIcon(node: BinderNode, open: boolean, active: boolean): LucideIcon {
  if (active) return FilePenLine;
  switch (node.kind) {
    case "project": return BookOpen;
    case "folder": return open ? FolderOpen : Folder;
    case "notes": return FileClock;
    case "characters": return Users;
    case "world": return Globe2;
    case "research": return BookMarked;
    case "inbox": return Inbox;
    case "trash": return Trash2;
    default: return FileText;
  }
}

function Row({ node, depth, activeId, expanded, onToggle, onSelect }: {
  node: BinderNode; depth: number; activeId: string;
  expanded: Set<string>; onToggle: (id: string) => void; onSelect: (n: BinderNode) => void;
}) {
  const hasChildren = node.children !== undefined;
  const open = expanded.has(node.id);
  const active = node.id === activeId;
  const cls = `lw-binder__item${active ? " is-active" : ""}${node.muted ? " is-muted" : ""}`;
  return (
    <>
      <div role="treeitem" aria-selected={active} aria-expanded={hasChildren ? open : undefined}
        tabIndex={active ? 0 : -1} className={cls} style={{ paddingLeft: 8 + depth * 16 }}
        onClick={() => (node.kind === "document" || node.kind === "notes" ? onSelect(node) : hasChildren && onToggle(node.id))}
        onKeyDown={(e) => {
          if (e.key === "Enter") node.kind === "document" || node.kind === "notes" ? onSelect(node) : onToggle(node.id);
          if (e.key === "ArrowRight" && hasChildren && !open) onToggle(node.id);
          if (e.key === "ArrowLeft" && hasChildren && open) onToggle(node.id);
        }}>
        {hasChildren ? (
          <button className="lw-binder__disclosure" aria-label={open ? "Collapse" : "Expand"}
            onClick={(e) => { e.stopPropagation(); onToggle(node.id); }}>
            <Icon icon={open ? ChevronDown : ChevronRight} size={11} stroke={1.8} />
          </button>
        ) : <span className="lw-binder__disclosure" aria-hidden />}
        <Icon icon={nodeIcon(node, open, active)} size={14} stroke={1.5} className="lw-binder__icon" />
        <span className="lw-binder__title" title={node.title}>{node.title}</span>
        {node.meta && <span className="lw-binder__meta">{node.meta}</span>}
      </div>
      {hasChildren && open && node.children!.map((c) => (
        <Row key={c.id} node={c} depth={depth + 1} activeId={activeId} expanded={expanded} onToggle={onToggle} onSelect={onSelect} />
      ))}
    </>
  );
}

function filterTree(nodes: BinderNode[], q: string): BinderNode[] {
  return nodes.flatMap((n) => {
    const kids = n.children ? filterTree(n.children, q) : undefined;
    if (n.title.toLowerCase().includes(q) || (kids && kids.length)) return [{ ...n, children: n.children ? kids : undefined }];
    return [];
  });
}
function allIds(nodes: BinderNode[], out = new Set<string>()) {
  for (const n of nodes) { out.add(n.id); if (n.children) allIds(n.children, out); }
  return out;
}

export function Binder({ nodes, collections, count, activeId, expanded, onToggle, onSelect, onNew, searching }: {
  searching: boolean;
  nodes: BinderNode[]; collections: Collection[]; count: number; activeId: string;
  expanded: Set<string>; onToggle: (id: string) => void; onSelect: (n: BinderNode) => void; onNew: () => void;
}) {
  const [query, setQuery] = useState("");
  const q = searching ? query.trim().toLowerCase() : "";
  const shown = q ? filterTree(nodes, q) : nodes;
  const open = q ? allIds(shown) : expanded;
  return (
    <aside className="lw-binder" aria-label="Manuscript binder">
      <div className="lw-binder__header">
        <div className="lw-binder__heading">
          <h2>Binder</h2>
          <span className="lw-mono lw-faint">{count}</span>
        </div>
        <div className="lw-row lw-gap-4">
          <IconButton icon={FilePlus2} label="New document" onClick={onNew} />
          <IconButton icon={Ellipsis} label="Binder options" />
        </div>
      </div>
      <div className="lw-divider" />
      {searching && (
        <div className="lw-binder__search">
          <input autoFocus value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Filter binder…" aria-label="Filter binder" />
        </div>
      )}
      <div className="lw-binder__tree" role="tree">
        {shown.map((n) => (
          <Row key={n.id} node={n} depth={0} activeId={activeId} expanded={open} onToggle={onToggle} onSelect={onSelect} />
        ))}
      </div>
      <div className="lw-divider" />
      <section className="lw-collections">
        <div className="lw-collections__heading">
          <SectionLabel>Collections</SectionLabel>
          <button className="lw-link">Edit</button>
        </div>
        {collections.map((c) => (
          <button key={c.id} className="lw-collections__row">
            <span className="lw-collections__swatch" style={{ background: c.color }} />
            <span className="lw-collections__title">{c.title}</span>
            <span className="lw-mono lw-faint">{c.count}</span>
          </button>
        ))}
      </section>
    </aside>
  );
}
