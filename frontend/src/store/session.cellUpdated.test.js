import { describe, it, expect, beforeEach } from "vitest";
import { useSessionStore } from "./session";

function seedSession() {
  useSessionStore.setState({
    session: {
      session_id: "2026-04",
      cells: { HPV: { odi: { user_override: 1, note: "vieja", per_file: { "a.pdf": 1 } } } },
    },
    filesTick: {},
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
