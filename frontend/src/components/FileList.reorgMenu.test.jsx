// @vitest-environment jsdom
//
// §A3 — ReorgMenu becomes a portalized Radix Popover instead of a <details>
// absolutely positioned inside the virtualized <ul> (where it used to clip
// in low rows, and scrolling with the menu open would unmount the row and
// silently drop whatever was typed). ReorgMenu isn't exported on its own, so
// this drives it through the real FileList row. Follows the DOM-mount
// pattern of FileList.test.jsx (react-dom/client + act, real Zustand store).
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import * as RadixTooltip from "@radix-ui/react-tooltip";

vi.mock("../lib/api", () => ({
  api: {
    getScanInfo: vi.fn(async () => ({ count_type: "documents", kind: "filename_glob" })),
  },
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import FileList from "./FileList";
import { useSessionStore } from "../store/session";
import { toast } from "sonner";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

// jsdom has no ResizeObserver; Radix's Popper positioning touches it.
if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

function mount(ui) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  // FileList's lock notice renders PresenceBadge, which uses ui/Tooltip —
  // that needs a RadixTooltip.Provider ancestor (App.jsx supplies it in the
  // real app; tests must supply their own, per DetailPanel.nearMatchNav.test.jsx).
  act(() => root.render(<RadixTooltip.Provider delayDuration={300}>{ui}</RadixTooltip.Provider>));
  return { container, unmount: () => act(() => root.unmount()) };
}

async function flush() {
  await act(async () => {});
}

const addReorgOp = vi.fn(async () => {});

function seed() {
  useSessionStore.setState({
    session: { session_id: "2026-06", cells: { HPV: { odi: {} } } },
    cellFiles: {
      "HPV|odi": {
        files: [{ name: "a.pdf", page_count: 3, effective_count: 1, origin: "R1" }],
        error: null,
      },
    },
    presence: [],
    addReorgOp,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  seed();
});

afterEach(() => {
  document.body.innerHTML = "";
});

function findTrigger(container) {
  return Array.from(container.querySelectorAll("button")).find(
    (b) => b.getAttribute("aria-label") === "Reorganizar archivo",
  );
}

function openMenu(container) {
  const trigger = findTrigger(container);
  act(() => trigger.dispatchEvent(new MouseEvent("click", { bubbles: true })));
  return trigger;
}

describe("FileList ReorgMenu — portalized popover (§A3)", () => {
  it("opens on trigger click and portals its content OUTSIDE the <ul>", async () => {
    const view = mount(<FileList hospital="HPV" sigla="odi" />);
    await flush();
    expect(findTrigger(view.container)).toBeTruthy();
    openMenu(view.container);
    // Content reaches the document (portalled to body) ...
    expect(document.body.textContent).toContain("Crear op.");
    // ... but is NOT a descendant of the virtualized <ul> — the whole point:
    // a deep scroll can no longer unmount/clip it mid-edit.
    const ul = view.container.querySelector("ul");
    expect(ul.textContent).not.toContain("Crear op.");
    view.unmount();
  });

  it("focus enters the popover content on open", async () => {
    const view = mount(<FileList hospital="HPV" sigla="odi" />);
    await flush();
    const trigger = openMenu(view.container);
    expect(document.activeElement).not.toBe(trigger);
    expect(document.body.contains(document.activeElement)).toBe(true);
    view.unmount();
  });

  it("Escape closes the popover", async () => {
    const view = mount(<FileList hospital="HPV" sigla="odi" />);
    await flush();
    openMenu(view.container);
    expect(document.body.textContent).toContain("Crear op.");
    act(() => {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    });
    expect(document.body.textContent).not.toContain("Crear op.");
    view.unmount();
  });

  it("submitting the form creates the reorg op (same shape as before the migration)", async () => {
    const view = mount(<FileList hospital="HPV" sigla="odi" />);
    await flush();
    openMenu(view.container);
    const form = document.querySelector("form");
    expect(form).toBeTruthy();
    await act(async () => {
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    });
    expect(addReorgOp).toHaveBeenCalledTimes(1);
    expect(addReorgOp).toHaveBeenCalledWith(
      "2026-06",
      "HPV",
      "odi",
      expect.objectContaining({ op_type: "move_file", source: { file: "a.pdf" } }),
    );
    expect(toast.success).toHaveBeenCalled();
    // Submitting closes the popover.
    expect(document.body.textContent).not.toContain("Crear op.");
    view.unmount();
  });

  it("a locked cell disables the trigger — the popover never opens", async () => {
    useSessionStore.setState({
      presence: [
        {
          participant_id: "other-participant",
          name: "Carla",
          color: "#ef4444",
          mode: "editor",
          focused_cell: "HPV|odi",
          kind: "human",
        },
      ],
    });
    const view = mount(<FileList hospital="HPV" sigla="odi" />);
    await flush();
    const trigger = findTrigger(view.container);
    expect(trigger.disabled).toBe(true);
    act(() => trigger.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    expect(document.body.textContent).not.toContain("Crear op.");
    view.unmount();
  });
});
