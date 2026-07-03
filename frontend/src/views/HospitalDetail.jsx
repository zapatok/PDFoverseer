import { useState, useEffect } from "react";
import { ArrowLeft } from "lucide-react";
import { useSessionStore } from "../store/session";
import CategoryGroup from "../components/CategoryGroup";
import CategoryBulkActions from "../components/CategoryBulkActions";
import FileList from "../components/FileList";
import DetailPanel from "../components/DetailPanel";
import ScanControls from "../components/ScanControls";
import { SIGLAS } from "../lib/sigla-labels";
import { computeCellCount } from "../lib/cellCount";
import { countTypeFor } from "../lib/sigla-info";

export default function HospitalDetail({ hospital, onBack }) {
  // PF4: one selector per field — never a bare useSessionStore() destructure.
  const session = useSessionStore((s) => s.session);
  const hospitalMode = useSessionStore((s) => s.hospitalMode);
  const focusSigla = useSessionStore((s) => s.focusSigla);
  const [selected, setSelected] = useState(null);
  const [selectedSet, setSelectedSet] = useState(new Set());

  const setFocus = useSessionStore((s) => s.setFocus);

  // Keep store focus in sync with the locally-selected cell.
  useEffect(() => {
    setFocus(selected ? `${hospital}|${selected}` : null);
    return () => setFocus(null); // clear on unmount / hospital change
  }, [hospital, selected, setFocus]);

  const cells = session?.cells?.[hospital] || {};
  const total = Object.entries(cells).reduce((s, [sig, c]) => s + computeCellCount(c, countTypeFor(sig)), 0);

  // One list, folder order (1-18). No Normalizadas/Compilaciones split — the
  // dot already says listo/pendiente and compilation_suspect is just a chip.
  const ordered =
    hospitalMode === "manual" ? SIGLAS : SIGLAS.filter((s) => cells[s]);

  const onCheck = (sigla, checked) => {
    setSelectedSet((prev) => {
      const next = new Set(prev);
      if (checked) next.add(sigla);
      else next.delete(sigla);
      return next;
    });
  };

  // Advance focus to the next sigla in canonical order.
  const focusNextSigla = (currentSigla) => {
    const idx = SIGLAS.indexOf(currentSigla);
    const next = SIGLAS[idx + 1];
    if (next) useSessionStore.setState({ focusSigla: next });
  };

  return (
    <div>
      <header className="flex items-center gap-4 mb-6">
        <button
          onClick={onBack}
          className="inline-flex items-center gap-1 text-sm text-po-text-muted hover:text-po-text"
        >
          <ArrowLeft size={16} strokeWidth={1.75} />
          Volver
        </button>
        <h2 className="text-xl font-semibold">{hospital}</h2>
        <span className="text-sm text-po-text-muted">
          Total: <span className="tabular-nums">{total.toLocaleString()}</span>{" "}
          {hospitalMode === "manual" ? "documentos ingresados" : "documentos detectados"}
        </span>
        <div className="ml-auto">
          <ScanControls hospital={hospital} selectedSiglas={[...selectedSet]} />
        </div>
      </header>

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)] gap-6">
        <section>
          <h3 className="text-xs font-medium uppercase tracking-wider text-po-text-muted mb-3">Categorías</h3>
          {hospitalMode !== "manual" && (
            <CategoryBulkActions
              hospital={hospital}
              cells={cells}
              selectedSiglas={[...selectedSet]}
              onMarkedReady={() => setSelectedSet(new Set())}
            />
          )}
          <CategoryGroup
            cells={ordered.map((s) => ({ sigla: s, ...cells[s] }))}
            hospital={hospital}
            selected={selected}
            onSelect={setSelected}
            checkedSet={selectedSet}
            onCheck={onCheck}
            mode={hospitalMode}
            focusSigla={focusSigla}
            onCommitNext={focusNextSigla}
          />
        </section>

        <section>
          <h3 className="text-xs font-medium uppercase tracking-wider text-po-text-muted mb-3">Detalle</h3>
          <DetailPanel hospital={hospital} sigla={selected} cell={selected ? cells[selected] : null} />
        </section>

        <section>
          <h3 className="text-xs font-medium uppercase tracking-wider text-po-text-muted mb-3">Archivos</h3>
          <FileList hospital={hospital} sigla={selected} />
        </section>
      </div>
    </div>
  );
}
