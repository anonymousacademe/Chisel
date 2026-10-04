/** Which window-control layout the title bar draws: macOS keeps the coloured dots on the left,
 *  Windows and Linux get flat minimize / maximize / close buttons on the right. */
export function isMacPlatform(platform: string): boolean {
  return /Mac/.test(platform);
}

export const IS_MAC = typeof navigator !== "undefined" && isMacPlatform(navigator.platform);

/** Windows only: the frameless window is dragged with the native move loop
 *  (begin_window_drag); everywhere else pywebview's own drag handling runs. */
export const IS_WINDOWS = typeof navigator !== "undefined" && /Win/.test(navigator.platform);
