import type { AttachKind } from "./types";

/** A chat attachment as the composer shows it. */
export interface Attachment { kind: AttachKind; id: string; title: string; words: number }
export const attachKey = (a: { kind: AttachKind; id: string }) => `${a.kind}:${a.id}`;
