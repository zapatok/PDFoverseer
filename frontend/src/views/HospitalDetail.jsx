import { useState } from "react";
import { useSessionStore } from "../store/session";
import CategoryRow from "../components/CategoryRow";
import FileList from "../components/FileList";
import OverridePanel from "../components/OverridePanel";
import ScanControls from "../components/ScanControls";

const SIGLAS = [
  "reunion",
  "irl",
  "odi",
  "charla",
  "chintegral",
  "dif_pts",
  "art",
  "insgral",
  "bodega",
  "maquinaria",
  "ext",
  "senal",
  "exc",
  "altura",
  "caliente",
  "herramientas_elec",
  "andamios",
  "chps",
];

export default function HospitalDetail({ hospital, onBack }) {
  const { session } = useSessionStore();
  const [selected, setSelected] = useState(null);
  const [selectedSet, setSelectedSet] = useState(new Set());

  const cells = session?.cells?.[hospital] || {};
  const total = Object.values(cells).reduce(
    (s, c) => s + (c.user_override ?? c.ocr_count ?? c.filename_count ?? c.count ?? 0),
    0,
  );
  const selectedCell = selected ? cells[selected] : null;

  const onCheck = (sigla, checked) => {
    setSelectedSet((prev) => {
      const next = new Set(prev);
      if (checked) next.add(sigla);
      else next.delete(sigla);
      return next;
    });
  };

  return (
    <div>
      <header className="flex items-center gap-4 mb-6">
        <button onClick={onBack} className="text-sm text-slate-400 hover:text-slate-200">
          ← Volver
        </button>
        <h2 className="text-xl font-semibold">{hospital}</h2>
        <span className="text-sm text-slate-400">Total: {total}</span>
        <div className="ml-auto">
          <ScanControls hospital={hospital} selectedSiglas={[...selectedSet]} />
        </div>
      </header>

      <div className="grid gap-6 grid-cols-1 xl:grid-cols-[1fr_1fr_1fr]">
        <section>
          <h3 className="text-sm uppercase text-slate-400 mb-2">Categorías</h3>
          <div className="space-y-0.5">
            {SIGLAS.map((s) => (
              <CategoryRow
                key={s}
                sigla={s}
                cell={cells[s]}
                hospital={hospital}
                selected={selected === s}
                onClick={() => setSelected(s)}
                checked={selectedSet.has(s)}
                onCheckChange={(c) => onCheck(s, c)}
              />
            ))}
          </div>
        </section>

        <section>
          <h3 className="text-sm uppercase text-slate-400 mb-2">Detalle</h3>
          {!selectedCell && <p className="text-slate-500">Selecciona una categoría</p>}
          {selectedCell && (
            <div className="space-y-3 text-sm">
              <p>
                <span className="text-slate-400">Sigla:</span> {selected}
              </p>
              <p>
                <span className="text-slate-400">Filename:</span>{" "}
                {selectedCell.filename_count ?? selectedCell.count ?? "—"}
              </p>
              <p>
                <span className="text-slate-400">OCR:</span> {selectedCell.ocr_count ?? "—"}{" "}
                {selectedCell.method && (
                  <span className="text-xs text-slate-500">via {selectedCell.method}</span>
                )}
              </p>
              <p>
                <span className="text-slate-400">Confidence:</span> {selectedCell.confidence}
              </p>
              {(selectedCell.flags || []).length > 0 && (
                <p>
                  <span className="text-slate-400">Flags:</span> {selectedCell.flags.join(", ")}
                </p>
              )}
              <OverridePanel hospital={hospital} sigla={selected} cell={selectedCell} />
            </div>
          )}
        </section>

        <section>
          <h3 className="text-sm uppercase text-slate-400 mb-2">Archivos</h3>
          <FileList hospital={hospital} sigla={selected} />
        </section>
      </div>
    </div>
  );
}
