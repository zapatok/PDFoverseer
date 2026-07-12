// @vitest-environment jsdom
//
// A8 — search/activeOrigins filters must reset on a GENUINE cell change (a
// filter left on from a previous sigla silently hides files in the next one,
// with only the "N de M" footer as a cue). A same-cell re-render (e.g. a
// per-file save bumping the store's cellFiles entry) must leave them intact.
import { describe, it, expect, vi, afterEach } from "vitest";
import React, { act } from "react";
import { createRoot } from "react-dom/client";

vi.mock("../lib/api", () => ({
  api: {
    getScanInfo: vi.fn(async () => ({ count_type: "documents", kind: "filename_glob" })),
  },
}));

import FileList from "./FileList";
import { useSessionStore } from "../store/session";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function mount(ui) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => root.render(ui));
  return {
    container,
    rerender: (next) => act(() => root.render(next)),
    unmount: () => act(() => root.unmount()),
  };
}

async function flush() {
  await act(async () => {});
}

function makeFile(name, overrides = {}) {
  return { name, page_count: 3, effective_count: 1, origin: "R1", ...overrides };
}

function typeInto(input, value) {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
  act(() => {
    setter.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

function searchInput(container) {
  return container.querySelector('input[placeholder="Buscar archivo…"]');
}

function originChip(container, label) {
  return [...container.querySelectorAll('[role="group"] button')].find(
    (b) => b.textContent === label,
  );
}

describe("FileList — A8: reset de búsqueda/filtros al cambiar de celda", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("búsqueda activa + cambio de celda → search vacío", async () => {
    useSessionStore.setState({
      session: { session_id: "2026-06", cells: { HPV: { odi: {}, art: {} } } },
      cellFiles: {
        "HPV|odi": { files: [makeFile("a.pdf"), makeFile("b.pdf")], error: null },
        "HPV|art": { files: [makeFile("c.pdf")], error: null },
      },
      presence: [],
    });
    const view = mount(<FileList hospital="HPV" sigla="odi" />);
    await flush();

    const input = searchInput(view.container);
    typeInto(input, "a.pdf");
    expect(searchInput(view.container).value).toBe("a.pdf");

    // Cambio de celda genuino.
    view.rerender(<FileList hospital="HPV" sigla="art" />);
    await flush();

    expect(searchInput(view.container).value).toBe("");
    view.unmount();
  });

  it("chip de origen activo + cambio de celda → activeOrigins vacío", async () => {
    useSessionStore.setState({
      session: { session_id: "2026-06", cells: { HPV: { odi: {}, art: {} } } },
      cellFiles: {
        "HPV|odi": { files: [makeFile("a.pdf"), makeFile("b.pdf", { origin: "OCR" })], error: null },
        "HPV|art": { files: [makeFile("c.pdf")], error: null },
      },
      presence: [],
    });
    const view = mount(<FileList hospital="HPV" sigla="odi" />);
    await flush();

    const chip = originChip(view.container, "OCR");
    act(() => chip.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    expect(originChip(view.container, "OCR").getAttribute("aria-pressed")).toBe("true");

    view.rerender(<FileList hospital="HPV" sigla="art" />);
    await flush();

    expect(originChip(view.container, "OCR").getAttribute("aria-pressed")).toBe("false");
    view.unmount();
  });

  it("un re-render de la MISMA celda (ej. un save que actualiza cellFiles) NO resetea los filtros", async () => {
    useSessionStore.setState({
      session: { session_id: "2026-06", cells: { HPV: { odi: {} } } },
      cellFiles: {
        "HPV|odi": { files: [makeFile("a.pdf"), makeFile("b.pdf")], error: null },
      },
      presence: [],
    });
    const view = mount(<FileList hospital="HPV" sigla="odi" />);
    await flush();

    typeInto(searchInput(view.container), "a.pdf");
    expect(searchInput(view.container).value).toBe("a.pdf");

    // Simula el refresco SWR de la MISMA celda (un save cambia el contenido
    // cacheado, pero hospital/sigla no cambian).
    act(() => {
      useSessionStore.setState({
        cellFiles: {
          "HPV|odi": {
            files: [makeFile("a.pdf", { effective_count: 2, origin: "Manual" }), makeFile("b.pdf")],
            error: null,
          },
        },
      });
    });
    view.rerender(<FileList hospital="HPV" sigla="odi" />);
    await flush();

    expect(searchInput(view.container).value).toBe("a.pdf");
    view.unmount();
  });
});
