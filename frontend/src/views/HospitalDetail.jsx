import { useState } from "react";
import { useSessionStore } from "../store/session";
import CategoryRow from "../components/CategoryRow";

const SIGLAS = [
  "reunion", "irl", "odi", "charla", "chintegral", "dif_pts", "art",
  "insgral", "bodega", "maquinaria", "ext", "senal", "exc",
  "altura", "caliente", "herramientas_elec", "andamios", "chps",
];

export default function HospitalDetail({ hospital, onBack }) {
  const { session } = useSessionStore();
  const [selected, setSelected] = useState(null);

  const cells = session?.cells?.[hospital] || {};
  const total = Object.values(cells).reduce(
    (s, c) => s + (c.user_override ?? c.count ?? 0), 0,
  );

  const selectedCell = selected ? cells[selected] : null;

  return (
    <div>
      <header className="flex items-center gap-4 mb-6">
        <button onClick={onBack} className="text-sm text-slate-400 hover:text-slate-200">
          ← Volver
        </button>
        <h2 className="text-xl font-semibold">{hospital}</h2>
        <span className="text-sm text-slate-400">Total: {total}</span>
      </header>

      <div className="grid grid-cols-2 gap-6">
        <section>
          <h3 className="text-sm uppercase text-slate-400 mb-2">Categorías</h3>
          <div className="space-y-0.5">
            {SIGLAS.map((s) => (
              <CategoryRow
                key={s}
                sigla={s}
                cell={cells[s]}
                selected={selected === s}
                onClick={() => setSelected(s)}
              />
            ))}
          </div>
        </section>

        <section>
          <h3 className="text-sm uppercase text-slate-400 mb-2">Detalle</h3>
          {!selectedCell && <p className="text-slate-500">Selecciona una categoría</p>}
          {selectedCell && (
            <div className="space-y-2 text-sm">
              <p><span className="text-slate-400">Sigla:</span> {selected}</p>
              <p><span className="text-slate-400">Count:</span> {selectedCell.count}</p>
              <p><span className="text-slate-400">Method:</span> {selectedCell.method}</p>
              <p><span className="text-slate-400">Confidence:</span> {selectedCell.confidence}</p>
              {selectedCell.flags?.length > 0 && (
                <p><span className="text-slate-400">Flags:</span> {selectedCell.flags.join(", ")}</p>
              )}
              {selectedCell.breakdown && (
                <div>
                  <p className="text-slate-400 mt-3">Subcarpetas:</p>
                  <ul className="ml-3 mt-1">
                    {Object.entries(selectedCell.breakdown).map(([k, v]) => (
                      <li key={k} className="font-mono text-xs">
                        · {k}: {v}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
