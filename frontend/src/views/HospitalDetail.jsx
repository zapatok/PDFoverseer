import { useState } from "react";
import { ArrowLeft } from "lucide-react";
import { useSessionStore } from "../store/session";
import CategoryGroup from "../components/CategoryGroup";
import FileList from "../components/FileList";
import DetailPanel from "../components/DetailPanel";
import ScanControls from "../components/ScanControls";

const SIGLAS = [
  "reunion", "irl", "odi", "charla", "chintegral", "dif_pts",
  "art", "insgral", "bodega", "maquinaria", "ext", "senal",
  "exc", "altura", "caliente", "herramientas_elec", "andamios", "chps",
];

export default function HospitalDetail({ hospital, onBack }) {
  const { session } = useSessionStore();
  const hospitalMode = useSessionStore((s) => s.hospitalMode);
  const focusSigla = useSessionStore((s) => s.focusSigla);
  const [selected, setSelected] = useState(null);
  const [selectedSet, setSelectedSet] = useState(new Set());

  const cells = session?.cells?.[hospital] || {};
  const total = Object.values(cells).reduce(
    (s, c) => s + (c.user_override ?? c.ocr_count ?? c.filename_count ?? c.count ?? 0),
    0,
  );

  const normalized =
    hospitalMode === "manual"
      ? SIGLAS
      : SIGLAS.filter((s) => cells[s] && !cells[s].flags?.includes("compilation_suspect"));
  const compilations =
    hospitalMode === "manual"
      ? []
      : SIGLAS.filter((s) => cells[s] && cells[s].flags?.includes("compilation_suspect"));

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

  const headerCountLabel = hospitalMode === "manual" ? "ingresadas" : "detectados";

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
          {headerCountLabel}
        </span>
        <div className="ml-auto">
          <ScanControls hospital={hospital} selectedSiglas={[...selectedSet]} />
        </div>
      </header>

      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)] gap-6">
        <section>
          <h3 className="text-xs font-medium uppercase tracking-wider text-po-text-muted mb-3">Categorías</h3>
          <CategoryGroup
            title="Normalizadas"
            cells={normalized.map((s) => ({ sigla: s, ...cells[s] }))}
            hospital={hospital}
            selected={selected}
            onSelect={setSelected}
            checkedSet={selectedSet}
            onCheck={onCheck}
            defaultOpen
            mode={hospitalMode}
            focusSigla={focusSigla}
            onCommitNext={focusNextSigla}
          />
          {compilations.length > 0 && (
            <CategoryGroup
              title="Compilaciones"
              cells={compilations.map((s) => ({ sigla: s, ...cells[s] }))}
              hospital={hospital}
              selected={selected}
              onSelect={setSelected}
              checkedSet={selectedSet}
              onCheck={onCheck}
              defaultOpen
              showScanAll
              mode={hospitalMode}
              focusSigla={focusSigla}
              onCommitNext={focusNextSigla}
            />
          )}
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
