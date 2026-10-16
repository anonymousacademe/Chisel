// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { LaunchTitleBar } from "./TitleBar";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

describe("LaunchTitleBar", () => {
  it("lets the launch screen's frameless window be dragged and closed", () => {
    const host = document.createElement("div");
    document.body.appendChild(host);
    const onClose = vi.fn();
    const root = createRoot(host);
    act(() => root.render(<LaunchTitleBar onClose={onClose} />));
    expect(host.querySelector(".pywebview-drag-region")).not.toBeNull();
    const close = host.querySelector<HTMLButtonElement>('[aria-label="Close window"]');
    expect(close).not.toBeNull();
    act(() => close!.click());
    expect(onClose).toHaveBeenCalledOnce();
    act(() => root.unmount());
    host.remove();
  });
});
