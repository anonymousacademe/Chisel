// @vitest-environment jsdom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { describe, expect, it, vi } from "vitest";
import { RelationshipsReviewDialog } from "./ReviewDialogs";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const items = [
  { target: "Mara Voss", label: "mentor of" },
  { target: "The Spire", label: "" },
];

async function rendered(onApply: (picked: typeof items) => void) {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root: Root = createRoot(host);
  await act(async () => {
    root.render(<RelationshipsReviewDialog name="Juno" items={items} onApply={onApply} onClose={() => {}} />);
  });
  return { host, root };
}

describe("RelationshipsReviewDialog", () => {
  it("ticks everything to start and applies only what stays ticked", async () => {
    const onApply = vi.fn();
    const { host, root } = await rendered(onApply);
    const boxes = host.querySelectorAll<HTMLInputElement>('input[type="checkbox"]');
    expect(boxes.length).toBe(2);
    expect(boxes[0].checked).toBe(true);
    expect(boxes[1].checked).toBe(true);
    expect(host.querySelector(".lw-dialog")?.textContent).toContain("mentor of — Mara Voss");
    expect(host.querySelector(".lw-dialog")?.textContent).toContain("The Spire");

    await act(async () => { boxes[1].click(); });
    const confirm = [...host.querySelectorAll("button")].find((b) => b.textContent === "Add 1 relationship");
    expect(confirm).toBeTruthy();
    await act(async () => { confirm!.click(); });
    expect(onApply).toHaveBeenCalledTimes(1);
    expect(onApply).toHaveBeenCalledWith([items[0]]);
    await act(async () => { root.unmount(); });
    host.remove();
  });
});
