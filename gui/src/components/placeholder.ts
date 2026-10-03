/** The one tooltip every not-yet-implemented control shows. */
export const PLACEHOLDER_TIP = "Not in Chisel yet";

/**
 * Spread onto any element to give it the shared placeholder treatment: drawn
 * as designed but dimmed, `aria-disabled`, tooltip, and (by convention) no
 * click handler. Never fake data that looks real; never a silent button.
 */
export const placeholderProps = {
  title: PLACEHOLDER_TIP, "aria-disabled": true, "data-placeholder": "",
} as const;

