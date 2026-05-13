import { useSessionStore } from "../store/session";

export default function ScanControls({ hospital, selectedSiglas }) {
  const { session, scanOcr, scanningCells } = useSessionStore();
  const busy = scanningCells.size > 0;

  const onSelected = () => {
    if (!session || selectedSiglas.length === 0) return;
    const pairs = selectedSiglas.map((s) => [hospital, s]);
    scanOcr(session.session_id, pairs);
  };

  const onSuspects = () => {
    if (!session) return;
    const cells = session.cells?.[hospital] || {};
    const suspectSiglas = Object.entries(cells)
      .filter(([, c]) => (c.flags || []).includes("compilation_suspect"))
      .map(([s]) => s);
    if (suspectSiglas.length === 0) return;
    scanOcr(session.session_id, suspectSiglas.map((s) => [hospital, s]));
  };

  return (
    <div className="flex items-center gap-2 text-sm">
      <button
        onClick={onSelected}
        disabled={busy || selectedSiglas.length === 0}
        className="px-3 py-1 rounded bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 disabled:text-slate-500"
      >
        OCR {selectedSiglas.length} seleccionadas
      </button>
      <button
        onClick={onSuspects}
        disabled={busy}
        className="px-3 py-1 rounded bg-slate-700 hover:bg-slate-600 disabled:opacity-50"
      >
        OCR suspects de {hospital}
      </button>
    </div>
  );
}
