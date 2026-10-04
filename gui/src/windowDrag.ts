/** Frameless-window dragging (Windows). pywebview's built-in drag moves the
 *  window with a SetWindowPos call per mousemove and applies the DPI scale to
 *  physical screen coordinates a second time, so on scaled displays the window
 *  overshoots and flickers (the recorded "screen jitter"). Instead, the first
 *  mouse down on the title bar hands the drag to the OS (begin_window_drag);
 *  Windows moves the window itself until the mouse goes up. The capture-phase
 *  listener also keeps pywebview's own body-level drag handler from firing.
 *  Buttons and fields inside the title bar stay clickable: the native move
 *  loop swallows the mouse-up, so they never hand the drag off. */
import { IS_WINDOWS } from "./data/platform";
import { api } from "./backend/api";

const INTERACTIVE = "button, a, input, select, textarea, label";

export function installWindowDrag(): void {
  if (!IS_WINDOWS) return;
  document.addEventListener(
    "mousedown",
    (ev) => {
      if (ev.button !== 0) return;
      let target: EventTarget | null = ev.target;
      while (target instanceof Element && target !== document.body && target !== document.documentElement) {
        if (target.matches(INTERACTIVE)) return;
        if (target.classList.contains("pywebview-drag-region")) {
          ev.stopPropagation();
          ev.preventDefault();
          void api.beginWindowDrag();
          return;
        }
        target = target.parentElement;
      }
    },
    { capture: true },
  );
}
