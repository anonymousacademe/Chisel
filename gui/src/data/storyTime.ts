import type { WhenInfo } from "./types";

/**
 * The faint "inherits 2187" hint under an empty Story time field. Python
 * (core/timeline.py) decides what is inherited; this only words it. Shown while
 * the field is blank and the scene had no `when:` of its own when it was loaded.
 */
export function inheritedHint(info: WhenInfo | undefined, typed: string): string {
  if (!info || typed.trim() !== "" || info.raw !== "" || info.source !== "inherited") return "";
  return `inherits ${info.label}`;
}

/** The helper line under the field: the problem if the text is not a story time, else the rule. */
export function whenHelp(typed: string, valid: boolean | null): string {
  if (typed.trim() !== "" && valid === false) {
    return "Not a story time. Use a year, like 2187, or 2187-03 or 2187-03-14. It is kept as text.";
  }
  return "Optional. Leave blank to use reading order.";
}
