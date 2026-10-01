import { useState } from "react";
import { GripVertical } from "lucide-react";
import type { SceneSummary } from "../data/types";
import { kickerOf, wordsLabel } from "../data/sceneFacts";
import { planMove, type Drop, type Group, type MovePlan } from "../data/reorder";
import { Icon } from "./primitives";

/** Status, POV and words/target of a scene on a card or outline row. */
function Facts({ s }: { s: SceneSummary }) {
  const d = s.details;
  return (
    <span className="lw-facts">
      {d.status && <span className="lw-tag lw-tag--accent lw-facts__status">{d.status}</span>}
      {d.pov && <span className="lw-facts__pov" title="POV">{d.pov}</span>}
      <span className="lw-mono lw-faint lw-facts__words">{wordsLabel(s)} words</span>
    </span>
  );
}

/** Drag-and-drop shared by the corkboard and the outline. The drop only asks the host to
 * move (and confirm); nothing here touches files. */
function useReorder(groups: Group[], onMove: (plan: MovePlan) => void) {
  const [dragId, setDragId] = useState<string | null>(null);
  const [over, setOver] = useState<string | null>(null);   // "before:<id>" | "end:<groupKey>"
  const accept = (e: React.DragEvent, key: string) => {
    if (!dragId) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    if (over !== key) setOver(key);
  };
  const drop = (e: React.DragEvent, target: Drop) => {
    e.preventDefault();
    const id = dragId;
    setDragId(null); setOver(null);
    if (!id) return;
    const plan = planMove(groups, id, target);
    if (plan) onMove(plan);
  };
  const dragProps = (id: string) => ({
    draggable: true,
    onDragStart: (e: React.DragEvent) => {
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", id);
      setDragId(id);
    },
    onDragEnd: () => { setDragId(null); setOver(null); },
  });
  return { dragId, over, accept, drop, dragProps };
}

export function Corkboard({ groups, activeId, unit, onOpen, onMove }: {
  groups: Group[]; activeId: string | null; unit: string; onOpen: (id: string) => void; onMove: (plan: MovePlan) => void;
}) {
  const r = useReorder(groups, onMove);
  const total = groups.reduce((n, g) => n + g.scenes.length, 0);
  return (
    <div className="lw-cork-wrap">
      <p className="lw-cork__hint">Drag a card to reorder it, or onto another part. You will be asked to confirm.</p>
      {groups.map((g) => (
        <section key={g.key} className={`lw-cork-group${g.frontMatter ? " is-muted" : ""}`} aria-label={g.title || "Scenes"}>
          {g.title && <h3 className="lw-cork-group__title">{g.title}<span className="lw-mono lw-faint">{g.scenes.length}</span></h3>}
          <div className="lw-cork">
            {g.scenes.map((s) => (
              <button key={s.id} {...r.dragProps(s.id)} data-scene={s.id}
                className={`lw-card${s.id === activeId ? " is-active" : ""}${r.dragId === s.id ? " is-dragging" : ""}${r.over === `before:${s.id}` ? " is-over" : ""}`}
                onClick={() => onOpen(s.id)}
                onDragOver={(e) => r.accept(e, `before:${s.id}`)}
                onDrop={(e) => r.drop(e, { kind: "before", sceneId: s.id })}>
                <span className="lw-card__kicker">{kickerOf(s, unit)}</span>
                <span className="lw-card__title">{s.title}</span>
                <span className="lw-card__excerpt">{s.excerpt}</span>
                <Facts s={s} />
              </button>
            ))}
            <div className={`lw-cork__end${r.over === `end:${g.key}` ? " is-over" : ""}${g.scenes.length === 0 ? " is-empty" : ""}`}
              data-end={g.key}
              onDragOver={(e) => r.accept(e, `end:${g.key}`)} onDrop={(e) => r.drop(e, { kind: "end", groupKey: g.key })}>
              {r.dragId ? `Drop here to put it at the end of ${g.title || "the book"}` : g.scenes.length === 0 ? `No ${unit}s here yet` : ""}
            </div>
          </div>
        </section>
      ))}
      {total === 0 && <p className="lw-empty">No {unit}s yet.</p>}
    </div>
  );
}

export function Outline({ groups, activeId, unit, onOpen, onMove }: {
  groups: Group[]; activeId: string | null; unit: string; onOpen: (id: string) => void; onMove: (plan: MovePlan) => void;
}) {
  const r = useReorder(groups, onMove);
  const total = groups.reduce((n, g) => n + g.scenes.length, 0);
  return (
    <div className="lw-outline-wrap">
      {groups.map((g) => (
        <section key={g.key} className={`lw-outline-group${g.frontMatter ? " is-muted" : ""}`} aria-label={g.title || "Scenes"}>
          {g.title && <h3 className="lw-cork-group__title">{g.title}<span className="lw-mono lw-faint">{g.scenes.length}</span></h3>}
          <ol className="lw-outline">
            {g.scenes.map((s) => (
              <li key={s.id} data-scene={s.id} className={`${r.dragId === s.id ? "is-dragging" : ""}${r.over === `before:${s.id}` ? " is-over" : ""}`}
                onDragOver={(e) => r.accept(e, `before:${s.id}`)} onDrop={(e) => r.drop(e, { kind: "before", sceneId: s.id })}>
                <div className="lw-outline__row">
                  <span className="lw-outline__handle" {...r.dragProps(s.id)} title={`Drag to move this ${unit}`} aria-label={`Drag “${s.title}” to reorder`}>
                    <Icon icon={GripVertical} size={14} stroke={1.5} />
                  </span>
                  <button className={s.id === activeId ? "is-active" : undefined} onClick={() => onOpen(s.id)}>
                    <span className="lw-outline__title">{s.number ? `${s.number}  ` : ""}{s.title}</span>
                    <Facts s={s} />
                  </button>
                </div>
                {s.headings.length > 0 && (
                  <ul className="lw-outline__headings">
                    {s.headings.map((h, i) => <li key={i}>{h}</li>)}
                  </ul>
                )}
              </li>
            ))}
            <li className={`lw-outline__end${r.over === `end:${g.key}` ? " is-over" : ""}${r.dragId ? " is-visible" : ""}`} data-end={g.key}
              onDragOver={(e) => r.accept(e, `end:${g.key}`)} onDrop={(e) => r.drop(e, { kind: "end", groupKey: g.key })}>
              {r.dragId ? `Drop here to put it at the end of ${g.title || "the book"}` : ""}
            </li>
          </ol>
        </section>
      ))}
      {total === 0 && <p className="lw-empty">No {unit}s yet.</p>}
    </div>
  );
}

