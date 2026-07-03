import { describe, it, expect, beforeEach } from "vitest";
import { useSessionStore } from "./session";

function seedSession() {
  useSessionStore.setState({
    session: {
      session_id: "2026-04",
      cells: { HPV: { odi: { user_override: 1, note: "vieja", per_file: { "a.pdf": 1 } } } },
    },
    filesTick: {},
    _pendingSave: new Map(),
  });
}

describe("_handleWSEvent cell_updated", () => {
  beforeEach(seedSession);

  it("reemplaza la celda ENTERA con el snapshot del evento", () => {
    const newCell = { user_override: 5, note: "nueva", note_status: "resuelto", per_file: { "a.pdf": 2 } };
    useSessionStore.getState()._handleWSEvent({
      type: "cell_updated", hospital: "HPV", sigla: "odi", actor: null, cell: newCell,
    });
    const cell = useSessionStore.getState().session.cells.HPV.odi;
    expect(cell).toEqual(newCell);          // reemplazo total
    expect(cell.note).toBe("nueva");
  });

  it("sube filesTick para que FileList/lightbox re-fetcheen", () => {
    useSessionStore.getState()._handleWSEvent({
      type: "cell_updated", hospital: "HPV", sigla: "odi", actor: null, cell: { per_file: {} },
    });
    expect(useSessionStore.getState().filesTick["HPV|odi"]).toBe(1);
  });

  it("no revienta si no hay sesión", () => {
    useSessionStore.setState({ session: null });
    expect(() =>
      useSessionStore.getState()._handleWSEvent({
        type: "cell_updated", hospital: "HPV", sigla: "odi", cell: {} })
    ).not.toThrow();
  });
});

describe("_handleWSEvent cell_updated defiere a guardados locales en vuelo (F15)", () => {
  beforeEach(seedSession);

  it("no reemplaza la celda si hay un guardado pendiente exacto (hospital|sigla)", () => {
    useSessionStore.setState({
      _pendingSave: new Map([["HPV|odi", { controller: new AbortController() }]]),
    });
    const serverCell = { user_override: 999, note: "servidor", per_file: { "a.pdf": 2 } };
    useSessionStore.getState()._handleWSEvent({
      type: "cell_updated", hospital: "HPV", sigla: "odi", actor: null, cell: serverCell,
    });
    const cell = useSessionStore.getState().session.cells.HPV.odi;
    expect(cell.user_override).toBe(1); // optimistic local value preserved
    expect(cell.note).toBe("vieja");
  });

  it("no reemplaza la celda si hay un guardado pendiente con sufijo (hospital|sigla|campo)", () => {
    useSessionStore.setState({
      _pendingSave: new Map([["HPV|odi|note", { controller: new AbortController() }]]),
    });
    const serverCell = { user_override: 999, note: "servidor", per_file: { "a.pdf": 2 } };
    useSessionStore.getState()._handleWSEvent({
      type: "cell_updated", hospital: "HPV", sigla: "odi", actor: null, cell: serverCell,
    });
    expect(useSessionStore.getState().session.cells.HPV.odi.user_override).toBe(1);
  });

  it("no sube filesTick mientras el guardado está pendiente", () => {
    useSessionStore.setState({
      _pendingSave: new Map([["HPV|odi", { controller: new AbortController() }]]),
    });
    useSessionStore.getState()._handleWSEvent({
      type: "cell_updated", hospital: "HPV", sigla: "odi", actor: null, cell: { per_file: {} },
    });
    expect(useSessionStore.getState().filesTick["HPV|odi"]).toBeUndefined();
  });

  it("aplica el snapshot una vez que el guardado pendiente se resuelve (clave ausente)", () => {
    // Simula el estado tras la resolución de la promesa: la clave ya no está.
    useSessionStore.setState({ _pendingSave: new Map() });
    const serverCell = { user_override: 5, note: "nueva", per_file: { "a.pdf": 2 } };
    useSessionStore.getState()._handleWSEvent({
      type: "cell_updated", hospital: "HPV", sigla: "odi", actor: null, cell: serverCell,
    });
    expect(useSessionStore.getState().session.cells.HPV.odi).toEqual(serverCell);
  });

  it("un guardado pendiente en OTRA celda no bloquea el reemplazo de esta", () => {
    useSessionStore.setState({
      _pendingSave: new Map([["HRB|art", { controller: new AbortController() }]]),
    });
    const serverCell = { user_override: 5, note: "nueva", per_file: { "a.pdf": 2 } };
    useSessionStore.getState()._handleWSEvent({
      type: "cell_updated", hospital: "HPV", sigla: "odi", actor: null, cell: serverCell,
    });
    expect(useSessionStore.getState().session.cells.HPV.odi).toEqual(serverCell);
  });

  it("no colisiona por prefijo: HPV|odi pendiente no bloquea HPV|odiXYZ", () => {
    useSessionStore.setState({
      session: {
        session_id: "2026-04",
        cells: {
          HPV: {
            odi: { user_override: 1, note: "vieja", per_file: { "a.pdf": 1 } },
            odiXYZ: { user_override: 1, note: "vieja-xyz", per_file: {} },
          },
        },
      },
      _pendingSave: new Map([["HPV|odi", { controller: new AbortController() }]]),
    });
    const serverCell = { user_override: 7, note: "nueva-xyz", per_file: {} };
    useSessionStore.getState()._handleWSEvent({
      type: "cell_updated", hospital: "HPV", sigla: "odiXYZ", actor: null, cell: serverCell,
    });
    expect(useSessionStore.getState().session.cells.HPV.odiXYZ).toEqual(serverCell);
  });
});
