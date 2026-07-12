// @vitest-environment jsdom
//
// §A10 — ReorgHud used to default destHospital/destSigla to HOSPITALS[0]/
// SIGLAS[0] (always HPV·reunion), inviting an extract_pages into the wrong
// cell. Defaults must be the SOURCE cell instead — the existing destino≠
// origen guard already blocks submit until the operator deliberately picks
// a different destination (same as FileList's ReorgMenu). Follows the
// DOM-mount pattern used across this project's component tests.
import { describe, it, expect, vi, afterEach } from "vitest";
import React, { act } from "react";
import { createRoot } from "react-dom/client";

// WorkerCountViewer.jsx imports usePdfDocument → lib/pdf (pdfjs-dist worker
// setup) at module load time, which needs DOMMatrix (absent in jsdom) — stub
// it so importing just the ReorgHud named export stays light (same pattern
// as DetailPanel.reorgLoop.test.jsx / usePdfDocument.test.jsx).
vi.mock("../lib/pdf", () => ({ pdfjsLib: {} }));

import { ReorgHud } from "./WorkerCountViewer";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function mount(ui) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => root.render(ui));
  return { container, unmount: () => act(() => root.unmount()) };
}

afterEach(() => {
  document.body.innerHTML = "";
});

function baseProps(overrides = {}) {
  return {
    currentPage: 1,
    pageCount: 10,
    reorgStart: 2,
    reorgEnd: 4,
    onMarkStart: vi.fn(),
    onMarkEnd: vi.fn(),
    onClearRange: vi.fn(),
    onCreateOp: vi.fn(async () => {}),
    currentFile: "a.pdf",
    sourceHospital: "HRB",
    sourceSigla: "odi",
    ...overrides,
  };
}

function findButton(container, label) {
  return Array.from(container.querySelectorAll("button")).find((b) => b.textContent === label);
}

describe("ReorgHud — destination defaults to the source cell (§A10)", () => {
  it("defaults destHospital/destSigla selects to the source cell, not HOSPITALS[0]/SIGLAS[0]", () => {
    const view = mount(<ReorgHud {...baseProps()} />);
    const selects = view.container.querySelectorAll("select");
    // selects[0] = opType, selects[1] = dest hospital, selects[2] = dest sigla
    // (opType defaults to "extract_pages", which renders the destino selects).
    expect(selects[1].value).toBe("HRB");
    expect(selects[2].value).toBe("odi");
    view.unmount();
  });

  it("the destino≠origen guard still blocks submit while the (now source-defaulted) dest is unchanged", () => {
    const onCreateOp = vi.fn(async () => {});
    const view = mount(<ReorgHud {...baseProps({ onCreateOp })} />);
    expect(view.container.textContent).toContain("El destino debe ser diferente al origen.");
    const createBtn = findButton(view.container, "Crear operación");
    expect(createBtn.disabled).toBe(true);
    view.unmount();
  });

  it("picking a different destination sigla clears the guard and enables submit", () => {
    const view = mount(<ReorgHud {...baseProps()} />);
    const selects = view.container.querySelectorAll("select");
    const destSiglaSelect = selects[2];
    const setter = Object.getOwnPropertyDescriptor(
      window.HTMLSelectElement.prototype,
      "value",
    ).set;
    act(() => {
      setter.call(destSiglaSelect, "art");
      destSiglaSelect.dispatchEvent(new Event("change", { bubbles: true }));
    });
    expect(view.container.textContent).not.toContain("El destino debe ser diferente al origen.");
    const createBtn = findButton(view.container, "Crear operación");
    expect(createBtn.disabled).toBe(false);
    view.unmount();
  });
});
