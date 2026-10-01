import type { InspirationImage } from "./types";

/** What the Settings and the panel say a picture costs (the default image model's measured price). */
export const IMAGE_COST_NOTE = "about $0.03 per image";

export interface Shown { pinned: InspirationImage[]; rest: InspirationImage[] }

/**
 * The panel's two groups. The open scene's pinned pictures come first (shown large, "on screen while
 * you write"); the rest is this scene's other pictures, or every picture when `all` is on. Newest first
 * is the order the core already sends.
 */
export function splitImages(images: InspirationImage[], sceneId: string | null, all: boolean): Shown {
  const mine = sceneId ? images.filter((i) => i.scene === sceneId) : [];
  const pinned = mine.filter((i) => i.pinned);
  const pool = all || !sceneId ? images : mine;
  return { pinned, rest: pool.filter((i) => !pinned.includes(i)) };
}

/** "Jul 4, 5:53 pm" from the sidecar's ISO local time; the raw text when it cannot be read. */
export function whenText(created: string): string {
  const d = new Date(created);
  if (Number.isNaN(d.getTime())) return created;
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

export const costText = (c: number | null | undefined) => (c == null ? "" : `$${c.toFixed(c < 0.01 ? 4 : 3)}`);

/** The menu / lightbox pin action for an image, given the scene that is open. */
export function pinAction(img: InspirationImage, sceneId: string | null): { label: string; pin: boolean; disabled: boolean } {
  if (sceneId && img.scene === sceneId && img.pinned) return { label: "Unpin from this scene", pin: false, disabled: false };
  return { label: "Pin to this scene", pin: true, disabled: !sceneId };
}

/** Replace the images with the same ids (after an update); keeps order. */
export function replaceImage(images: InspirationImage[], next: InspirationImage): InspirationImage[] {
  return images.map((i) => (i.id === next.id ? next : i));
}
