import type { LucideIcon } from "lucide-react";
import { placeholderProps } from "./placeholder";
import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";

/** Wrap a designed-but-unimplemented element (layout-neutral wrapper). */
export function Placeholder({ children, className = "", ...rest }: { children: ReactNode } & HTMLAttributes<HTMLSpanElement>) {
  return <span className={`lw-ph ${className}`} {...placeholderProps} {...rest}>{children}</span>;
}

/** Lucide icon with the design's pixel stroke widths (Figma strokes are absolute px). */
export function Icon({ icon: I, size, stroke = 1.6, color, className }:
  { icon: LucideIcon; size: number; stroke?: number; color?: string; className?: string }) {
  return <I size={size} strokeWidth={stroke} absoluteStrokeWidth color={color ?? "currentColor"} className={className} aria-hidden />;
}

/** 30×30 (or 26×26) ghost icon button — "Icon action" in the design. */
export function IconButton({ icon, label, active, small, stroke, placeholder, className = "", ...rest }:
  { icon: LucideIcon; label: string; active?: boolean; small?: boolean; stroke?: number; placeholder?: boolean } & ButtonHTMLAttributes<HTMLButtonElement>) {
  const extra = placeholder ? { ...placeholderProps, onClick: undefined, onMouseDown: undefined } : {};
  return (
    <button type="button" aria-label={label} title={label} aria-pressed={active}
      className={`lw-icon-btn${small ? " lw-icon-btn--sm" : ""}${active ? " is-active" : ""} ${className}`} {...rest} {...extra}>
      <Icon icon={icon} size={16} stroke={stroke ?? 1.6} />
    </button>
  );
}

export function Tag({ children, tone = "accent", placeholder }: { children: ReactNode; tone?: "accent" | "success"; placeholder?: boolean }) {
  return <span className={`lw-tag lw-tag--${tone}`} {...(placeholder ? placeholderProps : {})}>{children}</span>;
}

export function SectionLabel({ children, accent }: { children: ReactNode; accent?: boolean }) {
  return <span className={`lw-section-label${accent ? " is-accent" : ""}`}>{children}</span>;
}
