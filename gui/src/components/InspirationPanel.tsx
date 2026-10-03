import { useCallback, useEffect, useRef, useState } from "react";
import { Copy, Ellipsis, FolderOpen, ImagePlus, ImageUp, Pin, PinOff, RefreshCw, Sparkles, Trash2, X } from "lucide-react";
import { api, type AiKind } from "../backend/api";
import { IMAGE_COST_NOTE, costText, isUpload, itemNoun, pinAction, replaceImage, splitImages, uploadProblem, whenText } from "../data/inspiration";
import type { InspirationImage } from "../data/types";
import { ConfirmDialog, Menu, Modal, type MenuItem } from "./Dialogs";
import { Icon, IconButton, SectionLabel } from "./primitives";
import "../styles/inspiration.css";

/** Data URLs by image id for the session (a picture never changes under its id). */
const urls = new Map<string, string>();

function Picture({ img, className, onClick }: { img: InspirationImage; className?: string; onClick?: () => void }) {
  const [fetched, setFetched] = useState<{ id: string; url: string } | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  useEffect(() => {
    if (urls.has(img.id)) return;
    let live = true;
    void api.inspirationImage(img.id).then((r) => {
      if (!live) return;
      if (r.ok) { urls.set(img.id, r.dataUrl); setFetched({ id: img.id, url: r.dataUrl }); } else setFailed(img.id);
    });
    return () => { live = false; };
  }, [img.id]);
  const src = urls.get(img.id) ?? (fetched?.id === img.id ? fetched.url : null);
  const alt = img.label;
  if (failed === img.id) return <div className={`lw-insp__img lw-insp__img--missing ${className ?? ""}`}>Picture file missing</div>;
  if (!src) return <div className={`lw-insp__img lw-pulse ${className ?? ""}`} aria-label="Loading picture" />;
  return onClick
    ? <button type="button" className={`lw-insp__imgbtn ${className ?? ""}`} onClick={onClick} aria-label={`Open “${alt}” large`}><img className="lw-insp__img" src={src} alt={alt} draggable={false} /></button>
    : <img className={`lw-insp__img ${className ?? ""}`} src={src} alt={alt} draggable={false} />;
}

type Busy = "describe" | "generate" | null;

/** The file's bytes as a data URL (the core checks them; the browser's type is only a hint). */
const readDataUrl = (file: File) => new Promise<string>((resolve, reject) => {
  const reader = new FileReader();
  reader.onload = () => resolve(String(reader.result));
  reader.onerror = () => reject(reader.error ?? new Error("could not read the file"));
  reader.readAsDataURL(file);
});

/**
 * The Inspiration tab: describe a setting, get a picture or add your own, keep it beside the writing.
 * Reference only - nothing here touches the prose and no picture is ever sent to an AI. It works for whatever is
 * open: a scene, a character / place / object note or a notebook note. That item's pinned pictures are shown
 * large at the top and follow the item; "Show all" lists everything else.
 */
export function InspirationPanel(props: {
  /** The open item (null when nothing that can have pictures is open). */
  itemId: string | null; itemTitle: string;
  /** "scene" | "entity" | "research" | ...: a scene is described from the passage at the cursor, a note from its text. */
  itemKind: string | null;
  /** Bumped by the app when something outside changed the pictures (Trash restore). */
  rev: number;
  getEditor: () => { text: string; cursor: number } | null;
  /** Runs an AI job through the app (one at a time): progress strip, Stop, status-bar item. null = failed or stopped. */
  job: <X,>(label: string, verb: string, kind: AiKind, args: Record<string, unknown>) => Promise<(X & { ok: true }) | null>;
  requireAi: () => boolean; notify: (text: string, tone?: "info" | "error") => void;
  /** Refresh the status bar's AI spend. */
  onSpent: () => void;
}) {
  const { itemId, notify } = props;
  const noun = itemNoun(props.itemKind);
  const isScene = props.itemKind === "scene";
  const [images, setImages] = useState<InspirationImage[] | null>(null);
  const [prompt, setPrompt] = useState("");
  const [pin, setPin] = useState(true);
  const [all, setAll] = useState(false);
  const [busy, setBusy] = useState<Busy>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [menu, setMenu] = useState<{ anchor: HTMLElement; img: InspirationImage } | null>(null);
  const [editing, setEditing] = useState<InspirationImage | null>(null);
  const [trashing, setTrashing] = useState<InspirationImage | null>(null);
  const [model, setModel] = useState("");
  const [dropping, setDropping] = useState(false);
  const [adding, setAdding] = useState(false);
  const busyRef = useRef<Busy>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const show = useCallback((r: Awaited<ReturnType<typeof api.listInspiration>>) => {
    if (r.ok) { setImages(r.images); setModel(r.model); } else { setImages([]); notify(r.error, "error"); }
  }, [notify]);
  const load = useCallback(async () => { show(await api.listInspiration()); }, [show]);
  // reload when the app says so, and when the open item changes (renames and moves rewrite the links)
  useEffect(() => {
    let live = true;
    void api.listInspiration().then((r) => { if (live) show(r); });
    return () => { live = false; };
  }, [show, props.rev, itemId]);

  const run = async <T,>(kind: Exclude<Busy, null>, fn: () => Promise<T | null>): Promise<T | null> => {
    if (busyRef.current) { notify("Wait for the current request to finish."); return null; }
    busyRef.current = kind; setBusy(kind);
    try { return await fn(); } finally { busyRef.current = null; setBusy(null); props.onSpent(); }
  };

  const describe = async () => {
    if (!itemId) return notify("Open a scene or a note to describe it.");
    const ed = isScene ? props.getEditor() : null;
    if (isScene && !ed) return notify("Open a scene to describe it.");
    if (!props.requireAi()) return;
    const label = isScene ? "the scene" : "the note";
    const r = await run("describe", () => props.job<{ prompt: string; model: string; cost: number | null }>(
      `Describing ${label}…`, `describing ${label}`, "describe_scene", { doc_id: itemId, text: ed?.text ?? null, cursor: ed?.cursor ?? 0 }));
    if (r) { setPrompt(r.prompt); notify("Edit the description if you like, then press Generate."); }
  };
  const generate = async () => {
    const text = prompt.trim();
    if (!text) return notify("Describe the picture first.");
    if (!props.requireAi()) return;
    const r = await run("generate", () => props.job<{ images: InspirationImage[]; cost: number | null }>(
      "Making the picture…", "making a picture", "image", { prompt: text, doc_id: itemId, pin: pin && !!itemId }));
    if (!r) return;
    await load();
    notify(`${r.images.length === 1 ? "Picture" : `${r.images.length} pictures`} saved to inspiration/${r.cost != null ? ` (AI ${costText(r.cost)})` : ""}.`);
  };
  const regenerate = async (img: InspirationImage) => {
    if (isUpload(img)) return notify("A picture you added has no prompt, so it cannot be regenerated.");
    if (!props.requireAi()) return;
    const r = await run("generate", () => props.job<{ images: InspirationImage[]; cost: number | null }>(
      "Making another picture…", "making a picture", "image_regenerate", { image_id: img.id }));
    if (!r) return;
    await load();
    notify(`Another picture saved${r.cost != null ? ` (AI ${costText(r.cost)})` : ""}. The first is still there.`);
  };
  /** Add the author's own pictures (file picker or drag-and-drop). Nothing is sent to an AI. */
  const addFiles = async (files: File[]) => {
    if (!files.length) return;
    setAdding(true);
    let added = 0;
    try {
      for (const f of files) {
        const problem = uploadProblem(f);
        if (problem) { notify(problem, "error"); continue; }
        let r;
        try { r = await api.uploadInspiration(f.name, await readDataUrl(f), itemId); } catch { notify(`Could not read “${f.name}”.`, "error"); continue; }
        if (!r.ok) { notify(r.error, "error"); continue; }
        added++;
      }
    } finally { setAdding(false); }
    if (added) {
      await load();
      notify(`${added === 1 ? "Picture" : `${added} pictures`} added to inspiration/${itemId ? ` for ${props.itemTitle || `this ${noun}`}` : ""}.`);
    }
  };
  const setPinned = async (img: InspirationImage, on: boolean) => {
    const r = await api.updateInspiration(img.id, on ? { pinned: true, for: itemId ?? img.for } : { pinned: false });
    if (!r.ok) return notify(r.error, "error");
    setImages((l) => (l ? replaceImage(l, r.image) : l));
  };
  const saveDetails = async (img: InspirationImage, title: string, notes: string) => {
    const r = await api.updateInspiration(img.id, { title, notes });
    if (!r.ok) return notify(r.error, "error");
    setImages((l) => (l ? replaceImage(l, r.image) : l));
    setEditing(null);
  };
  const trash = async (img: InspirationImage) => {
    setTrashing(null); setOpen(null);
    const r = await api.deleteInspiration(img.id);
    if (!r.ok) return notify(r.error, "error");
    notify("Moved the picture to the Trash.");
    await load();
  };
  const copyPrompt = async (img: InspirationImage) => {
    try { await navigator.clipboard.writeText(img.prompt); notify("Prompt copied."); } catch { notify("Could not copy; select the prompt in the large view.", "error"); }
  };
  const reveal = async (img: InspirationImage) => {
    const r = await api.revealInspiration(img.id);
    if (!r.ok) return notify(r.error, "error");
    notify(r.opened ? "Opened the folder." : `File: ${r.path}`);
  };

  const menuItems = (img: InspirationImage): MenuItem[] => {
    const pa = pinAction(img, itemId, noun);
    const up = isUpload(img);
    return [
      { label: "Open large", onSelect: () => setOpen(img.id) },
      { label: pa.label, disabled: pa.disabled, onSelect: () => void setPinned(img, pa.pin) },
      { label: up ? "Regenerate (not for added pictures)" : "Regenerate (about $0.03)", disabled: up, onSelect: () => void regenerate(img) },
      { label: "Rename / notes…", onSelect: () => setEditing(img) },
      { label: "Copy prompt", disabled: up, onSelect: () => void copyPrompt(img) },
      { label: "Reveal file", onSelect: () => void reveal(img) },
      { separator: true, label: "", onSelect: () => {} },
      { label: "Move to Trash", danger: true, onSelect: () => setTrashing(img) },
    ];
  };

  const shown = splitImages(images ?? [], itemId);
  const opened = images?.find((i) => i.id === open) ?? null;
  const card = (img: InspirationImage, large: boolean) => (
    <figure key={img.id} className={`lw-insp__card${large ? " lw-insp__card--large" : ""}`}>
      <Picture img={img} onClick={() => setOpen(img.id)} />
      <figcaption className="lw-insp__cap">
        <span className="lw-insp__label" title={img.prompt || img.label}>
          {img.pinned && <Icon icon={Pin} size={11} stroke={1.8} />}{" "}
          {isUpload(img) && <span className="lw-insp__badge" title="Added by you; never sent to an AI">uploaded</span>}
          {img.unlinked && <span className="lw-insp__badge lw-insp__badge--warn" title={`Its ${img.for} is gone (renamed away or in the Trash). Restoring it reconnects the picture.`}>Unlinked</span>}
          {img.label}
        </span>
        <IconButton small icon={Ellipsis} label={`Actions for ${img.label}`} onClick={(e) => setMenu({ anchor: e.currentTarget, img })} />
      </figcaption>
    </figure>
  );
  const dropProps = {
    onDragOver: (e: React.DragEvent) => { if (e.dataTransfer.types.includes("Files")) { e.preventDefault(); setDropping(true); } },
    onDragLeave: (e: React.DragEvent) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDropping(false); },
    onDrop: (e: React.DragEvent) => {
      setDropping(false);
      if (!e.dataTransfer.files.length) return;
      e.preventDefault();
      void addFiles(Array.from(e.dataTransfer.files));
    },
  };

  return (
    <section className={`lw-insp${dropping ? " lw-insp--drop" : ""}`} aria-label="Inspiration pictures" {...dropProps}>
      <p className="lw-insp__lead">Pictures to keep beside you while you write. They are reference only: they never go into your prose and are never sent to an AI. Drop a JPG, PNG or WebP here, or use Add picture.</p>
      <div className="lw-insp__compose">
        <textarea className="lw-insp__prompt" rows={4} value={prompt} placeholder="A dark subway platform at night, flickering fluorescent lights…"
          aria-label="Picture description" onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); void generate(); } }} />
        <div className="lw-insp__actions">
          <button className="lw-btn" disabled={!itemId || busy !== null} onClick={() => void describe()}
            title={itemId ? (isScene ? "Write the description from the passage around your cursor" : "Write the description from this note's text") : "Open a scene or a note first"}>
            <Icon icon={Sparkles} size={14} stroke={1.8} /> {busy === "describe" ? "Describing…" : isScene ? "Describe this scene" : "Describe this note"}
          </button>
          <button className="lw-btn lw-btn--primary" disabled={!prompt.trim() || busy !== null} onClick={() => void generate()}>
            <Icon icon={ImagePlus} size={14} stroke={1.8} /> {busy === "generate" ? "Generating…" : "Generate"}
          </button>
        </div>
        <div className="lw-insp__meta">
          <label className="lw-check lw-insp__pin">
            <input type="checkbox" checked={pin && !!itemId} disabled={!itemId} onChange={(e) => setPin(e.target.checked)} />
            Pin to this {noun}
          </label>
          <span className="lw-faint" title={model}>{IMAGE_COST_NOTE}</span>
        </div>
        {busy === "generate" && <p className="lw-empty lw-pulse">Making the picture; this takes a few seconds…</p>}
        <div className="lw-insp__actions">
          <button className="lw-btn" disabled={adding} onClick={() => fileRef.current?.click()}
            title={`Add a JPG, PNG or WebP of your own${itemId ? ` for this ${noun}` : ""}; it stays on your computer`}>
            <Icon icon={ImageUp} size={14} stroke={1.8} /> {adding ? "Adding…" : "Add picture"}
          </button>
          <input ref={fileRef} type="file" hidden multiple accept="image/jpeg,image/png,image/webp" aria-label="Add picture"
            onChange={(e) => { const files = Array.from(e.target.files ?? []); e.target.value = ""; void addFiles(files); }} />
        </div>
      </div>

      {images === null && <p className="lw-empty lw-pulse">Loading pictures…</p>}

      {shown.pinned.length > 0 && (
        <>
          <SectionLabel accent>Pinned to {props.itemTitle || `this ${noun}`}</SectionLabel>
          <div className="lw-insp__pinned">{shown.pinned.map((i) => card(i, true))}</div>
        </>
      )}

      {images !== null && (
        <>
          <div className="lw-insp__bar">
            <SectionLabel>{itemId ? `This ${noun}` : "All pictures"} · {itemId ? shown.rest.length + shown.pinned.length : shown.rest.length}</SectionLabel>
            {itemId && shown.others.length > 0 && (
              <button className="lw-chip lw-chip--pick" aria-pressed={all} onClick={() => setAll((a) => !a)}>
                {all ? "Hide the others" : `Show all · ${shown.others.length} more`}
              </button>
            )}
          </div>
          {shown.rest.length === 0 && shown.pinned.length === 0 && (
            <p className="lw-empty">{images.length === 0
              ? "No pictures yet. Describe a place above and press Generate, or add one of your own; they are saved in your project's inspiration folder."
              : itemId ? `No pictures for this ${noun} yet.${shown.others.length ? " Use Show all to see the others." : ""}` : "Nothing to show."}</p>
          )}
          <div className="lw-insp__grid">{shown.rest.map((i) => card(i, false))}</div>
          {itemId && all && shown.others.length > 0 && (
            <>
              <SectionLabel>All other pictures · {shown.others.length}</SectionLabel>
              <div className="lw-insp__grid">{shown.others.map((i) => card(i, false))}</div>
            </>
          )}
        </>
      )}

      {menu && <Menu anchor={menu.anchor} items={menuItems(menu.img)} onClose={() => setMenu(null)} />}
      {opened && (
        <Lightbox img={opened} itemId={itemId} noun={noun} onClose={() => setOpen(null)}
          onPin={(on) => void setPinned(opened, on)} onRegenerate={() => void regenerate(opened)} onCopy={() => void copyPrompt(opened)}
          onEdit={() => setEditing(opened)} onReveal={() => void reveal(opened)} onTrash={() => setTrashing(opened)} />
      )}
      {editing && <DetailsDialog img={editing} onClose={() => setEditing(null)} onSave={(t, n) => void saveDetails(editing, t, n)} />}
      {trashing && (
        <ConfirmDialog title="Move picture to the Trash" confirm="Move to Trash"
          message={<>Move “{trashing.label}” to the Trash? You can restore it from the Trash later.</>}
          onConfirm={() => void trash(trashing)} onClose={() => setTrashing(null)} />
      )}
    </section>
  );
}

function Lightbox({ img, itemId, noun, onClose, onPin, onRegenerate, onCopy, onEdit, onReveal, onTrash }: {
  img: InspirationImage; itemId: string | null; noun: string; onClose: () => void; onPin: (on: boolean) => void;
  onRegenerate: () => void; onCopy: () => void; onEdit: () => void; onReveal: () => void; onTrash: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape" && !e.defaultPrevented) { e.preventDefault(); onClose(); } };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  const pa = pinAction(img, itemId, noun);
  const up = isUpload(img);
  return (
    <div className="lw-overlay lw-overlay--center lw-insp__lightbox" onMouseDown={onClose}>
      <div className="lw-insp__lbbox" role="dialog" aria-label={img.label} onMouseDown={(e) => e.stopPropagation()}>
        <div className="lw-insp__lbtop">
          <strong className="lw-insp__lbtitle">{img.label}</strong>
          <IconButton icon={X} label="Close" onClick={onClose} />
        </div>
        <Picture img={img} className="lw-insp__lbimg" />
        {up ? <p className="lw-insp__lbprompt lw-faint">Added by you. It is not sent to any AI and has no prompt.</p> : <p className="lw-insp__lbprompt">{img.prompt}</p>}
        {img.notes && <p className="lw-insp__lbnotes">{img.notes}</p>}
        <p className="lw-faint lw-insp__lbmeta">{whenText(img.created)}{up ? " · uploaded" : ` · ${img.model}`}{img.cost != null ? ` · ${costText(img.cost)}` : ""}{img.for ? ` · ${img.for}${img.unlinked ? " (unlinked)" : ""}` : ""}</p>
        <div className="lw-insp__lbbuttons">
          <button className="lw-btn" disabled={pa.disabled} onClick={() => onPin(pa.pin)}><Icon icon={pa.pin ? Pin : PinOff} size={14} stroke={1.8} /> {pa.label}</button>
          <button className="lw-btn" disabled={up} title={up ? "A picture you added has no prompt to regenerate from" : undefined} onClick={onRegenerate}><Icon icon={RefreshCw} size={14} stroke={1.8} /> Regenerate</button>
          <button className="lw-btn" disabled={up} onClick={onCopy}><Icon icon={Copy} size={14} stroke={1.8} /> Copy prompt</button>
          <button className="lw-btn" onClick={onEdit}>Rename / notes…</button>
          <button className="lw-btn" onClick={onReveal}><Icon icon={FolderOpen} size={14} stroke={1.8} /> Reveal file</button>
          <button className="lw-btn lw-btn--danger" onClick={onTrash}><Icon icon={Trash2} size={14} stroke={1.8} /> Move to Trash</button>
        </div>
      </div>
    </div>
  );
}

function DetailsDialog({ img, onClose, onSave }: { img: InspirationImage; onClose: () => void; onSave: (title: string, notes: string) => void }) {
  const [title, setTitle] = useState(img.title);
  const [notes, setNotes] = useState(img.notes);
  return (
    <Modal title="Picture details" onClose={onClose}>
      <label className="lw-dialog__label">Name <span className="lw-faint">(shown instead of the prompt)</span>
        <input className="lw-launch__input" value={title} maxLength={120} placeholder={img.prompt.slice(0, 60)} autoFocus onChange={(e) => setTitle(e.target.value)} />
      </label>
      <label className="lw-dialog__label">Notes
        <textarea className="lw-insp__prompt" rows={5} value={notes} onChange={(e) => setNotes(e.target.value)} />
      </label>
      <div className="lw-dialog__buttons">
        <button className="lw-btn" onClick={onClose}>Cancel</button>
        <button className="lw-btn lw-btn--primary" onClick={() => onSave(title, notes)}>Save</button>
      </div>
    </Modal>
  );
}
