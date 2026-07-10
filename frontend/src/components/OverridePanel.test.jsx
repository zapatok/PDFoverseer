// @vitest-environment jsdom
//
// Over-cap confirmation flow (task 5 + spec-review follow-up): typing a value
// above maxPages surfaces "¿Confirmas N documentos?"; Confirmar saves with
// allowOverPages, Cancelar reverts to the last synced value. The load-bearing
// case is BLUR SURVIVAL: clicking either button blurs the input first
// (mousedown), so the confirmation row must not be torn down by the blur
// resync effect before the click lands.
//
// Follows the DOM-mount pattern of DetailPanel.reorgLoop.test.jsx
// (react-dom/client + act, real Zustand store with setState, no testing-library).
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import React, { act } from "react";
import { createRoot } from "react-dom/client";

vi.mock("../lib/api", () => ({ api: {} }));
vi.mock("../lib/ws", () => ({ createWSClient: () => ({ close: () => {} }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import OverridePanel from "./OverridePanel";
import { useSessionStore } from "../store/session";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function mount(ui) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => root.render(ui));
  return { container, unmount: () => act(() => root.unmount()) };
}

function setInputValue(input, value) {
  const setter = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype,
    "value",
  ).set;
  setter.call(input, value);
  act(() => input.dispatchEvent(new Event("input", { bubbles: true })));
}

function findButton(container, label) {
  return Array.from(container.querySelectorAll("button")).find(
    (b) => b.textContent === label,
  );
}

const saveOverride = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  useSessionStore.setState({
    session: { session_id: "2026-04", cells: { HRB: { odi: { user_override: null } } } },
    pendingSaves: {},
    saveOverride,
  });
});

afterEach(() => {
  document.body.innerHTML = "";
});

// React ≥17 maps onFocus/onBlur to the native focusin/focusout events —
// dispatching plain focus/blur never reaches the component's handlers.
function focusIn(input) {
  act(() => input.dispatchEvent(new FocusEvent("focusin", { bubbles: true })));
}
function focusOut(input) {
  act(() => input.dispatchEvent(new FocusEvent("focusout", { bubbles: true })));
}

function typeOverCap(container) {
  const input = container.querySelector("input");
  // Real sequence: the operator focuses the field and types.
  focusIn(input);
  setInputValue(input, "12");
  return input;
}

describe("OverridePanel — over-cap confirmation", () => {
  it("typing an over-cap value shows the confirmation and does NOT save", () => {
    const { container } = mount(
      <OverridePanel hospital="HRB" sigla="odi" cell={{ user_override: null }} maxPages={6} />,
    );
    typeOverCap(container);
    expect(container.textContent).toContain("¿Confirmas 12 documentos?");
    expect(saveOverride).not.toHaveBeenCalled();
  });

  it("the confirmation row SURVIVES the input blur (mousedown on the button blurs first)", () => {
    const { container } = mount(
      <OverridePanel hospital="HRB" sigla="odi" cell={{ user_override: null }} maxPages={6} />,
    );
    const input = typeOverCap(container);
    // What a real click does before the click event: blur the input.
    focusOut(input);
    expect(findButton(container, "Confirmar")).toBeTruthy();
  });

  it("Confirmar (after the blur) saves with allowOverPages and no manual flag", () => {
    const { container } = mount(
      <OverridePanel hospital="HRB" sigla="odi" cell={{ user_override: null }} maxPages={6} />,
    );
    const input = typeOverCap(container);
    focusOut(input);
    const confirmar = findButton(container, "Confirmar");
    expect(confirmar).toBeTruthy();
    act(() => confirmar.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    expect(saveOverride).toHaveBeenCalledWith("2026-04", "HRB", "odi", 12, {
      allowOverPages: true,
    });
  });

  it("Cancelar (after the blur) saves nothing and resyncs the field to the last value", () => {
    const { container } = mount(
      <OverridePanel hospital="HRB" sigla="odi" cell={{ user_override: 4 }} maxPages={6} />,
    );
    const input = typeOverCap(container);
    focusOut(input);
    const cancelar = findButton(container, "Cancelar");
    expect(cancelar).toBeTruthy();
    act(() => cancelar.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    expect(saveOverride).not.toHaveBeenCalled();
    expect(container.textContent).not.toContain("¿Confirmas 12 documentos?");
    // The field reverts to the stored override, not the refused over-cap text.
    expect(input.value).toBe("4");
  });
});
