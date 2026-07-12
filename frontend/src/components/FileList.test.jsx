// @vitest-environment jsdom
//
// §C1 — FileList render contract, pinned post-A1/A8:
//  (1) virtualization mount + spacer geometry invariant (100 files).
//  (2) search finds files OUTSIDE the mounted window (filters pre-slice).
//  (3) shrink-by-filter regression while scrolled deep (hotfix c173468),
//      pinned at the component level (computeWindow itself is already
//      covered in lib/list-window.test.js).
//  (4) SWR: a same-cell store update shows no Skeleton and keeps the <ul>
//      DOM node mounted (no remount → scroll survives); a genuine cell
//      change resets scroll AND filters (A8 — also pinned on its own in
//      FileList.filterReset.test.jsx).
import { describe, it, expect, vi, afterEach } from "vitest";
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { computeWindow } from "../lib/list-window";

vi.mock("../lib/api", () => ({
  api: {
    getScanInfo: vi.fn(async () => ({ count_type: "documents", kind: "filename_glob" })),
  },
}));

import FileList from "./FileList";
import { useSessionStore } from "../store/session";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

// Mirrors FileList.jsx's internal (unexported) constants.
const ROW_H = 40;
const ROW_OVERSCAN = 8;

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

function typeInto(input, value) {
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
  act(() => {
    setter.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

function scrollTo(ul, top) {
  ul.scrollTop = top;
  act(() => ul.dispatchEvent(new Event("scroll", { bubbles: false })));
}

function makeFiles(n, { prefix = "file" } = {}) {
  return Array.from({ length: n }, (_, i) => ({
    name: `${prefix}-${String(i).padStart(3, "0")}.pdf`,
    page_count: 3,
    effective_count: 1,
    origin: "R1",
  }));
}

function seed(cellFiles, extra = {}) {
  useSessionStore.setState({
    session: { session_id: "2026-06", cells: { HPV: { odi: {}, art: {} } } },
    cellFiles,
    presence: [],
    ...extra,
  });
}

describe("FileList — §C1 render contract", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("(1) virtualización: con 100 archivos solo se montan las filas de la ventana + 2 spacers, geometría exacta", async () => {
    Object.defineProperty(window, "innerHeight", { value: 800, writable: true, configurable: true });
    seed({ "HPV|odi": { files: makeFiles(100), error: null } });
    const view = mount(<FileList hospital="HPV" sigla="odi" />);
    await flush();

    const ul = view.container.querySelector("ul");
    // Mid-list scroll so BOTH spacers are non-zero (start > 0 and end < total).
    scrollTo(ul, 1000);
    await flush();

    const viewportH = Math.ceil(800 * 0.6);
    const expected = computeWindow(1000, viewportH, ROW_H, 100, ROW_OVERSCAN);

    const lis = [...ul.children];
    const spacers = lis.filter((li) => li.hasAttribute("aria-hidden"));
    const rows = lis.filter((li) => !li.hasAttribute("aria-hidden"));

    expect(spacers.length).toBe(2); // top AND bottom spacer both present at a mid-scroll
    expect(rows.length).toBe(expected.end - expected.start);
    expect(rows.length).toBeLessThan(100); // proves virtualization, not a full mount

    const topSpacerH = parseFloat(spacers[0].style.height);
    const bottomSpacerH = parseFloat(spacers[1].style.height);
    expect(topSpacerH).toBe(expected.topPad);
    expect(bottomSpacerH).toBe(expected.bottomPad);
    // Geometry invariant: spacers + rendered rows account for the full list height.
    expect(topSpacerH + bottomSpacerH + rows.length * ROW_H).toBe(100 * ROW_H);

    view.unmount();
  });

  it("(2) la búsqueda encuentra archivos FUERA de la ventana montada (filtra antes de recortar)", async () => {
    seed({ "HPV|odi": { files: makeFiles(100), error: null } });
    const view = mount(<FileList hospital="HPV" sigla="odi" />);
    await flush();

    // At scrollTop 0 the mounted window only covers the first ~rows — file-099
    // is nowhere near it, yet the search must still find it (pre-slice filter).
    const input = view.container.querySelector('input[placeholder="Buscar archivo…"]');
    typeInto(input, "file-099");
    await flush();

    expect(view.container.textContent).toContain("file-099.pdf");
    expect(view.container.textContent).toContain("1 de 100");

    view.unmount();
  });

  it("(3) regresión del shrink-por-filtro con scroll profundo (hotfix c173468) a nivel componente", async () => {
    Object.defineProperty(window, "innerHeight", { value: 800, writable: true, configurable: true });
    const files = [
      ...makeFiles(98, { prefix: "noise" }),
      { name: "keep-a.pdf", page_count: 3, effective_count: 1, origin: "R1" },
      { name: "keep-b.pdf", page_count: 3, effective_count: 1, origin: "R1" },
    ];
    seed({ "HPV|odi": { files, error: null } });
    const view = mount(<FileList hospital="HPV" sigla="odi" />);
    await flush();

    const ul = view.container.querySelector("ul");
    scrollTo(ul, 3000); // deep scroll, well past where 2 filtered rows would fit
    await flush();

    const input = view.container.querySelector('input[placeholder="Buscar archivo…"]');
    typeInto(input, "keep-");
    await flush();

    // Without the computeWindow clamp this would render a blank list (start > end).
    expect(view.container.textContent).toContain("keep-a.pdf");
    expect(view.container.textContent).toContain("keep-b.pdf");
    expect(view.container.textContent).toContain("2 de 100");

    view.unmount();
  });

  it("(4a) SWR: un update de la MISMA celda no muestra Skeleton y conserva el <ul> montado (scroll intacto)", async () => {
    seed({
      "HPV|odi": {
        files: [
          { name: "a.pdf", page_count: 3, effective_count: 1, origin: "R1" },
          { name: "b.pdf", page_count: 3, effective_count: 1, origin: "R1" },
        ],
        error: null,
      },
    });
    const view = mount(<FileList hospital="HPV" sigla="odi" />);
    await flush();

    const ulBefore = view.container.querySelector("ul");
    expect(ulBefore).not.toBeNull();
    ulBefore.scrollTop = 15;

    // Simulate what fetchCellFiles' SWR resolve does: the SAME key's entry is
    // replaced in place, hospital/sigla unchanged (mirrors a per-file save).
    act(() => {
      useSessionStore.setState({
        cellFiles: {
          "HPV|odi": {
            files: [
              { name: "a.pdf", page_count: 3, effective_count: 2, origin: "Manual" },
              { name: "b.pdf", page_count: 3, effective_count: 1, origin: "R1" },
            ],
            error: null,
          },
        },
      });
    });
    view.rerender(<FileList hospital="HPV" sigla="odi" />);
    await flush();

    // No Skeleton flash — the row content updated in place.
    expect(view.container.textContent).not.toContain("Sin archivos");
    expect(view.container.querySelectorAll('[class*="animate-pulse"]').length).toBe(0);
    const ulAfter = view.container.querySelector("ul");
    expect(ulAfter).toBe(ulBefore); // same DOM node — never unmounted
    expect(ulAfter.scrollTop).toBe(15); // untouched by the SWR update

    view.unmount();
  });

  it("(4b) un cambio GENUINO de celda resetea scroll y filtros (A8)", async () => {
    seed({
      "HPV|odi": {
        files: [
          { name: "a.pdf", page_count: 3, effective_count: 1, origin: "R1" },
          { name: "b.pdf", page_count: 3, effective_count: 1, origin: "R1" },
        ],
        error: null,
      },
      "HPV|art": { files: [{ name: "c.pdf", page_count: 2, effective_count: 1, origin: "R1" }], error: null },
    });
    const view = mount(<FileList hospital="HPV" sigla="odi" />);
    await flush();

    const ul = view.container.querySelector("ul");
    ul.scrollTop = 30;
    const input = view.container.querySelector('input[placeholder="Buscar archivo…"]');
    typeInto(input, "a.pdf");
    expect(view.container.querySelector('input[placeholder="Buscar archivo…"]').value).toBe("a.pdf");

    view.rerender(<FileList hospital="HPV" sigla="art" />);
    await flush();

    const newUl = view.container.querySelector("ul");
    expect(newUl.scrollTop).toBe(0);
    expect(view.container.querySelector('input[placeholder="Buscar archivo…"]').value).toBe("");

    view.unmount();
  });
});
