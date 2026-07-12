// @vitest-environment jsdom
//
// §A7 — CategoryRow is the central selection loop of the app (choose a
// category → its files/detail render), but it was a plain <div onClick>
// with no tabIndex/role/onKeyDown — no keyboard path at all. Follows the
// DOM-mount pattern of FileList.reorgMenu.test.jsx (react-dom/client + act,
// real Zustand store, RadixTooltip.Provider wrapper — the row's sigla label
// uses ui/Tooltip unconditionally).
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import * as RadixTooltip from "@radix-ui/react-tooltip";

import CategoryRow from "./CategoryRow";
import { useSessionStore } from "../store/session";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function mount(ui) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => root.render(<RadixTooltip.Provider delayDuration={300}>{ui}</RadixTooltip.Provider>));
  return { container, unmount: () => act(() => root.unmount()) };
}

beforeEach(() => {
  useSessionStore.setState({
    session: { session_id: "2026-06", cells: { HPV: { odi: {} } } },
    scanningCells: new Set(),
    pendingSaves: {},
    presence: [],
  });
});

afterEach(() => {
  document.body.innerHTML = "";
});

describe("CategoryRow — keyboard operability (§A7)", () => {
  it("the row is a tab stop (role=button, tabIndex=0)", () => {
    const onSelect = vi.fn();
    const view = mount(
      <CategoryRow hospital="HPV" sigla="odi" cell={{}} selected={false} onSelect={onSelect} checked={false} onCheckChange={() => {}} />,
    );
    const row = view.container.querySelector('[role="button"]');
    expect(row).toBeTruthy();
    expect(row.getAttribute("tabindex")).toBe("0");
    view.unmount();
  });

  it("Enter on the focused row selects it", () => {
    const onSelect = vi.fn();
    const view = mount(
      <CategoryRow hospital="HPV" sigla="odi" cell={{}} selected={false} onSelect={onSelect} checked={false} onCheckChange={() => {}} />,
    );
    const row = view.container.querySelector('[role="button"]');
    act(() => row.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })));
    expect(onSelect).toHaveBeenCalledTimes(1);
    view.unmount();
  });

  it("Space on the focused row selects it", () => {
    const onSelect = vi.fn();
    const view = mount(
      <CategoryRow hospital="HPV" sigla="odi" cell={{}} selected={false} onSelect={onSelect} checked={false} onCheckChange={() => {}} />,
    );
    const row = view.container.querySelector('[role="button"]');
    act(() => row.dispatchEvent(new KeyboardEvent("keydown", { key: " ", bubbles: true })));
    expect(onSelect).toHaveBeenCalledTimes(1);
    view.unmount();
  });

  it("Space on the nested checkbox does NOT also trigger row selection", () => {
    const onSelect = vi.fn();
    const onCheckChange = vi.fn();
    const view = mount(
      <CategoryRow hospital="HPV" sigla="odi" cell={{}} selected={false} onSelect={onSelect} checked={false} onCheckChange={onCheckChange} />,
    );
    const checkbox = view.container.querySelector('input[type="checkbox"]');
    act(() => checkbox.dispatchEvent(new KeyboardEvent("keydown", { key: " ", bubbles: true })));
    expect(onSelect).not.toHaveBeenCalled();
    view.unmount();
  });
});
