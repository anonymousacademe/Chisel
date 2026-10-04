import type { AttachItem, AttachKind, ChatMessage, SavedChat } from "./types";

/** A chat attachment as the composer shows it. */
export interface Attachment { kind: AttachKind; id: string; title: string; words: number }
export const attachKey = (a: { kind: AttachKind; id: string }) => `${a.kind}:${a.id}`;

/** A saved conversation's messages as the panel shows them (error flags are never stored, so never restored). */
export function savedToMessages(saved: SavedChat["messages"]): ChatMessage[] {
  return saved.map((m) => (m.role === "user"
    ? { id: m.id, role: "user" as const, text: m.text }
    : { id: m.id, role: "assistant" as const, text: m.text, ...(m.sources ? { sources: m.sources } : {}), ...(m.ideas ? { ideas: m.ideas } : {}) }));
}

/** A saved chat's attachments that still exist (`known` is keyed by attachKey); `missing` says some were left off. */
export function restoreAttachments(saved: SavedChat["attachments"], known: Map<string, AttachItem>): { attachments: Attachment[]; missing: boolean } {
  const attachments = saved.flatMap((a) => {
    const hit = known.get(attachKey(a));
    return hit ? [{ kind: a.kind, id: a.id, title: hit.title, words: hit.words }] : [];
  });
  return { attachments, missing: saved.length > 0 && attachments.length < saved.length };
}
