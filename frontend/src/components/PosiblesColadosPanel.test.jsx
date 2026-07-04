// @vitest-environment jsdom
//
// Anti-colados V1: the POSIBLES COLADOS panel surfaces misfiled-document
// suspects and offers "Crear op de reorg" (prefilled) + "Descartar". Follows
// the react-dom/client + act mount pattern (no testing-library here).
import { describe, it, expect, afterEach, beforeEach, vi } from "vitest";
import { act } from "react";
import { createRoot } from "react-dom/client";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import PosiblesColadosPanel from "./PosiblesColadosPanel";
import { useSessionStore } from "../store/session";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function mount(ui) {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => root.render(ui));
  return { container, unmount: () => act(() => root.unmount()) };
}

const _filename = (over = {}) => ({
  id: "cs_a",
  kind: "filename",
  file: "2026-05_odi_x.pdf",
  evidence: "odi",
  suggested_sigla: "odi",
  page_range: null,
  counted: false,
  ...over,
});

beforeEach(() => vi.clearAllMocks());
afterEach(() => {
  document.body.innerHTML = "";
});

describe("PosiblesColadosPanel", () => {
  it("renders null when there are no suspects", () => {
    const { container } = mount(
      <PosiblesColadosPanel hospital="HRB" sigla="art" cell={{}} sessionId="2026-04" />,
    );
    expect(container.textContent).toBe("");
  });

  it("lists a filename suspect with the Archivo chip, evidence, suggested sigla and both actions", () => {
    const cell = { colado_suspects: [_filename()] };
    const { container } = mount(
      <PosiblesColadosPanel hospital="HRB" sigla="art" cell={cell} sessionId="2026-04" />,
    );
    const text = container.textContent;
    expect(text).toContain("Archivo");
    expect(text).toContain("2026-05_odi_x.pdf");
    expect(text).toContain("token: odi");
    expect(text).toContain("ODI Visitas"); // SIGLA_LABELS[odi]
    expect(text).toContain("Crear op de reorg");
    expect(text).toContain("Descartar");
  });

  it("renders a code suspect with a Páginas range chip and código evidence", () => {
    const cell = {
      colado_suspects: [
        _filename({ id: "cs_c", kind: "code", page_range: [2, 4], evidence: "F-CRS-ART-01", suggested_sigla: "art", counted: true }),
      ],
    };
    const { container } = mount(
      <PosiblesColadosPanel hospital="HRB" sigla="odi" cell={cell} sessionId="2026-04" />,
    );
    const text = container.textContent;
    expect(text).toContain("Páginas 2–4");
    expect(text).toContain("código: F-CRS-ART-01");
  });

  it("disables 'Crear op de reorg' for an ambiguous (suggested_sigla=null) suspect", () => {
    const cell = { colado_suspects: [_filename({ suggested_sigla: null, evidence: "odi, reunion" })] };
    const { container } = mount(
      <PosiblesColadosPanel hospital="HRB" sigla="art" cell={cell} sessionId="2026-04" />,
    );
    const crear = [...container.querySelectorAll("button")].find(
      (b) => b.textContent.trim() === "Crear op de reorg",
    );
    expect(crear.disabled).toBe(true);
    expect(container.textContent).toContain("elige el destino");
  });

  it("disables both actions when the cell is locked by another participant", () => {
    const cell = { colado_suspects: [_filename()] };
    const { container } = mount(
      <PosiblesColadosPanel hospital="HRB" sigla="art" cell={cell} sessionId="2026-04" locked />,
    );
    for (const b of container.querySelectorAll("button")) expect(b.disabled).toBe(true);
  });

  it("Descartar calls dismissColadoSuspect with the suspect id", async () => {
    const dismissMock = vi.fn(async () => {});
    useSessionStore.setState({ dismissColadoSuspect: dismissMock });
    const cell = { colado_suspects: [_filename()] };
    const { container } = mount(
      <PosiblesColadosPanel hospital="HRB" sigla="art" cell={cell} sessionId="2026-04" />,
    );
    const descartar = [...container.querySelectorAll("button")].find(
      (b) => b.textContent.trim() === "Descartar",
    );
    await act(async () => descartar.click());
    expect(dismissMock).toHaveBeenCalledWith("2026-04", "HRB", "art", "cs_a");
  });

  it("Crear op de reorg prefills a move_file op with doc_count 0 for an uncounted suspect", async () => {
    const addMock = vi.fn(async () => {});
    useSessionStore.setState({ addReorgOp: addMock });
    const cell = { colado_suspects: [_filename({ counted: false })] };
    const { container } = mount(
      <PosiblesColadosPanel hospital="HRB" sigla="art" cell={cell} sessionId="2026-04" />,
    );
    const crear = [...container.querySelectorAll("button")].find(
      (b) => b.textContent.trim() === "Crear op de reorg",
    );
    await act(async () => crear.click());
    expect(addMock).toHaveBeenCalledTimes(1);
    const [, hosp, sig, draft] = addMock.mock.calls[0];
    expect(hosp).toBe("HRB");
    expect(sig).toBe("art");
    expect(draft.op_type).toBe("move_file");
    expect(draft.source).toEqual({ file: "2026-05_odi_x.pdf", page_range: null });
    expect(draft.dest).toEqual({ hospital: "HRB", sigla: "odi" });
    expect(draft.doc_count).toBe(0); // uncounted → explicit 0 (§6 divergence)
  });

  it("Crear op de reorg OMITS doc_count for a counted suspect (backend default)", async () => {
    const addMock = vi.fn(async () => {});
    useSessionStore.setState({ addReorgOp: addMock });
    const cell = {
      colado_suspects: [
        _filename({ id: "cs_p", kind: "code", page_range: [3, 5], counted: true, suggested_sigla: "art" }),
      ],
    };
    const { container } = mount(
      <PosiblesColadosPanel hospital="HRB" sigla="odi" cell={cell} sessionId="2026-04" />,
    );
    const crear = [...container.querySelectorAll("button")].find(
      (b) => b.textContent.trim() === "Crear op de reorg",
    );
    await act(async () => crear.click());
    const [, , , draft] = addMock.mock.calls[0];
    expect(draft.op_type).toBe("extract_pages");
    expect(draft.source).toEqual({ file: "2026-05_odi_x.pdf", page_range: [3, 5] });
    expect("doc_count" in draft).toBe(false); // counted → omit → backend default
  });
});
