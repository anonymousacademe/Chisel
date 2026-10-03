import type { InspirationImage } from "./types";

/** What the Settings and the panel say a picture costs (the default image model's measured price). */
export const IMAGE_COST_NOTE = "about $0.03 per image";

/** The biggest picture the author can add (the core enforces the same limit on the bytes). */
export const UPLOAD_MAX_BYTES = 10 * 1024 * 1024;
const UPLOAD_TYPES = ["image/jpeg", "image/png", "image/webp"];

export interface Shown {
  /** The open item's pinned pictures ("show with this item"), shown large. */
  pinned: InspirationImage[];
  /** The open item's other pictures. With no item open: every picture. */
  rest: InspirationImage[];
  /** Every picture that is not for the open item (the "Show all" grid). Empty with no item open. */
  others: InspirationImage[];
}

/**
 * The panel's groups for the open item (a scene, a character / place / object note or a notebook note;
 * `null` when nothing that can have pictures is open). Its pinned pictures come first (shown large,
 * "on screen while you write"), then its other pictures; `others` is everything else for "Show all".
 * Newest first is the order the core already sends.
 */
export function splitImages(images: InspirationImage[], itemId: string | null): Shown {
  if (!itemId) return { pinned: [], rest: images, others: [] };
  const mine = images.filter((i) => i.for === itemId);
  const pinned = mine.filter((i) => i.pinned);
  return { pinned, rest: mine.filter((i) => !i.pinned), others: images.filter((i) => i.for !== itemId) };
}

/** "Jul 4, 5:53 pm" from the sidecar's ISO local time; the raw text when it cannot be read. */
export function whenText(created: string): string {
  const d = new Date(created);
  if (Number.isNaN(d.getTime())) return created;
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

export const costText = (c: number | null | undefined) => (c == null ? "" : `$${c.toFixed(c < 0.01 ? 4 : 3)}`);

/** What to call the open item in the panel's words. */
export function itemNoun(kind: string | null | undefined): string {
  return kind === "scene" ? "scene" : "note";
}

/** The menu / lightbox pin action for an image ("show with that item"), given the item that is open. */
export function pinAction(img: InspirationImage, itemId: string | null, noun = "scene"): { label: string; pin: boolean; disabled: boolean } {
  if (itemId && img.for === itemId && img.pinned) return { label: `Unpin from this ${noun}`, pin: false, disabled: false };
  return { label: `Pin to this ${noun}`, pin: true, disabled: !itemId };
}

/** Replace the images with the same ids (after an update); keeps order. */
export function replaceImage(images: InspirationImage[], next: InspirationImage): InspirationImage[] {
  return images.map((i) => (i.id === next.id ? next : i));
}

/** The picture was added by the author (it has no prompt, so it cannot be regenerated). */
export const isUpload = (img: InspirationImage) => img.source === "upload";

/** Why a file cannot be added as a picture (null = fine). The core checks the bytes again. */
export function uploadProblem(file: { name: string; type: string; size: number }): string | null {
  if (!UPLOAD_TYPES.includes(file.type)) return `“${file.name}” is not a JPG, PNG or WebP picture.`;
  if (file.size === 0) return `“${file.name}” is empty.`;
  if (file.size > UPLOAD_MAX_BYTES) return `“${file.name}” is larger than ${UPLOAD_MAX_BYTES / (1024 * 1024)} MB.`;
  return null;
}
