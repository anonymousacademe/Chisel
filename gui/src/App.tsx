import { useEffect, useMemo, useState } from "react";
import { backend } from "./backend";
import type { BinderNode, ChatMessage, ManuscriptDocument, Workspace } from "./data/types";
import { placeholderDocument } from "./data/mock";
import { TitleBar } from "./components/TitleBar";
import { ActivityRail, type RailView } from "./components/ActivityRail";
import { Binder } from "./components/Binder";
import { Editor, type ViewMode } from "./components/Editor";
import { Assistant } from "./components/Assistant";
import { StatusBar } from "./components/StatusBar";

const countWords = (d: ManuscriptDocument) =>
  d.paragraphs.reduce((n, p) => n + (p.text.trim() ? p.text.trim().split(/\s+/).length : 0), 0);

function collectExpanded(nodes: BinderNode[], out = new Set<string>()) {
  for (const n of nodes) { if (n.expanded) out.add(n.id); if (n.children) collectExpanded(n.children, out); }
  return out;
}
function findParent(nodes: BinderNode[], id: string, parent?: BinderNode): BinderNode | undefined {
  for (const n of nodes) {
    if (n.id === id) return parent;
    const hit = n.children && findParent(n.children, id, n);
    if (hit) return hit;
  }
}
function findNode(nodes: BinderNode[], id: string): BinderNode | undefined {
  for (const n of nodes) { if (n.id === id) return n; const h = n.children && findNode(n.children, id); if (h) return h; }
}

const ZOOMS = [90, 100, 110, 125];

export default function App() {
  const [ws, setWs] = useState<Workspace | null>(null);
  const [baseline, setBaseline] = useState<Record<string, number>>({});
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [rail, setRail] = useState<RailView>("binder");
  const [assistantOpen, setAssistantOpen] = useState(true);
  const [focus, setFocus] = useState(false);
  const [mode, setMode] = useState<ViewMode>("manuscript");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(true);
  const [badge, setBadge] = useState(3);
  const [commentOpen, setCommentOpen] = useState(true);
  const [caret, setCaret] = useState({ line: 68, col: 1 });
  const [zoom, setZoom] = useState(100);

  useEffect(() => {
    backend.getWorkspace().then((w) => {
      setWs(w);
      setExpanded(collectExpanded(w.binder));
      setBaseline(Object.fromEntries(Object.values(w.documents).map((d) => [d.id, countWords(d)])));
    });
  }, []);

  // Line/column of the caret, counted in paragraphs for the prose editor.
  useEffect(() => {
    const onSel = () => {
      const sel = document.getSelection();
      const p = sel?.anchorNode?.parentElement?.closest(".lw-prose p");
      if (!p || !sel) return;
      const all = Array.from(document.querySelectorAll(".lw-prose p"));
      setCaret({ line: all.indexOf(p) + 1, col: sel.anchorOffset + 1 });
    };
    document.addEventListener("selectionchange", onSel);
    return () => document.removeEventListener("selectionchange", onSel);
  }, []);

  const doc = useMemo(() => {
    if (!ws) return null;
    const existing = ws.documents[ws.activeDocumentId];
    if (existing) return existing;
    const node = findNode(ws.binder, ws.activeDocumentId)!;
    return placeholderDocument(node, findParent(ws.binder, node.id)?.title ?? ws.project.title);
  }, [ws]);

  if (!ws || !doc) return <div className="lw-app lw-loading">Loading project…</div>;

  const delta = countWords(doc) - (baseline[doc.id] ?? 0);
  const allDelta = Object.values(ws.documents).reduce((n, d) => n + countWords(d) - (baseline[d.id] ?? countWords(d)), 0);
  const siblings = findParent(ws.binder, doc.id)?.children?.filter((c) => c.kind === "document" || c.kind === "notes") ?? [];

  const updateDoc = (fn: (d: ManuscriptDocument) => ManuscriptDocument) => {
    const next = fn(doc);
    setWs({ ...ws, documents: { ...ws.documents, [next.id]: next } });
    setSaved(false);
    backend.saveDocument(next.id, next.paragraphs.map((p) => p.text)).then(() => setSaved(true));
  };
  const select = (n: BinderNode) => { setWs({ ...ws, activeDocumentId: n.id }); setCaret({ line: 1, col: 1 }); };
  const toggle = (id: string) => setExpanded((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });

  const send = async (text: string, replaceId?: string) => {
    const user: ChatMessage = { id: crypto.randomUUID(), role: "user", text };
    setWs((w) => w && ({ ...w, assistant: { ...w.assistant, messages: replaceId ? w.assistant.messages.filter((m) => m.id !== replaceId) : [...w.assistant.messages, user] } }));
    setBusy(true);
    const reply = await backend.askAssistant(text, "current-scene");
    setBusy(false);
    setWs((w) => w && ({ ...w, assistant: { ...w.assistant, messages: [...w.assistant.messages, { id: crypto.randomUUID(), role: "assistant", text: reply }] } }));
  };
  const regenerate = (id: string) => {
    const msgs = ws.assistant.messages;
    const i = msgs.findIndex((m) => m.id === id);
    const prompt = [...msgs.slice(0, i)].reverse().find((m) => m.role === "user");
    if (prompt) send(prompt.text, id);
  };
  const reviewInsight = () => {
    setMode("manuscript");
    requestAnimationFrame(() => {
      const el = document.querySelector(".lw-revision");
      el?.scrollIntoView({ behavior: "smooth", block: "center" });
      el?.classList.add("is-flash");
      setTimeout(() => el?.classList.remove("is-flash"), 1400);
    });
  };
  const onRail = (v: RailView) => {
    if (v === "assistant") { setAssistantOpen((o) => !o); setBadge(0); return; }
    if (v === "research") setExpanded((s) => new Set(s).add("research"));
    setRail(v); setFocus(false);
  };

  const showBinder = !focus;
  const showAssistant = assistantOpen && !focus;

  return (
    <div className="lw-app" style={{ ["--lw-zoom" as string]: zoom / 100 }}>
      <TitleBar projectTitle={ws.project.title} documentLabel={`${doc.shortLabel} · ${doc.title}`} draft={ws.project.draft}
        saved={saved} assistantOpen={showAssistant} onToggleAssistant={() => { setAssistantOpen((o) => !o); setBadge(0); }}
        onSearch={() => onRail("search")} />
      <div className="lw-workspace">
        <ActivityRail view={showAssistant && rail === "assistant" ? "assistant" : rail} onView={onRail} badge={showAssistant ? 0 : badge} initials={ws.project.initials} />
        {showBinder && (
          <Binder nodes={ws.binder} collections={ws.collections} count={ws.project.documentCount} activeId={doc.id}
            expanded={expanded} onToggle={toggle} onSelect={select} searching={rail === "search"} onNew={() => { /* backend: create document */ }} />
        )}
        <Editor doc={doc} siblings={siblings} words={doc.words + delta} mode={mode} onMode={setMode}
          focus={focus} onFocus={() => setFocus((f) => !f)}
          onParagraph={(id, text) => updateDoc((d) => ({ ...d, paragraphs: d.paragraphs.map((p) => p.id === id ? { ...p, text } : p) }))}
          onAppend={(text) => updateDoc((d) => ({ ...d, paragraphs: [...d.paragraphs, { id: crypto.randomUUID(), text }] }))}
          onSelect={select} onAskAssistant={() => { setAssistantOpen(true); setFocus(false); }}
          commentOpen={commentOpen} onComment={() => setCommentOpen((c) => !c)} />
        {showAssistant && (
          <Assistant insight={ws.assistant.insight} messages={ws.assistant.messages} sources={ws.assistant.sources} busy={busy}
            onSend={(t) => send(t)} onClose={() => setAssistantOpen(false)} onRegenerate={regenerate}
            onReviewInsight={reviewInsight}
            onDismissInsight={() => setWs({ ...ws, assistant: { ...ws.assistant, insight: undefined } })} />
        )}
      </div>
      <StatusBar draft={ws.project.draft} snapshot={ws.status.snapshot} synced={ws.status.synced} streak={ws.status.streakDays}
        sessionWords={ws.status.sessionWords + allDelta} sessionTarget={ws.status.sessionTarget}
        projectWords={ws.status.projectWords + allDelta} line={caret.line} col={caret.col}
        zoom={zoom} onZoom={() => setZoom((z) => ZOOMS[(ZOOMS.indexOf(z) + 1) % ZOOMS.length])} />
    </div>
  );
}
