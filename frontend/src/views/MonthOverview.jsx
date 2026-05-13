import { useEffect } from "react";
import { useSessionStore } from "../store/session";
import HospitalCard from "../components/HospitalCard";

const HOSPITALS = ["HPV", "HRB", "HLU", "HLL"];

export default function MonthOverview() {
  const {
    months, session, loading, error,
    loadMonths, openMonth, selectHospital, runScan, generateOutput,
  } = useSessionStore();

  useEffect(() => {
    loadMonths();
  }, [loadMonths]);

  const activeMonth = session?.session_id;
  const cells = session?.cells || {};

  const totalsByHospital = Object.fromEntries(
    HOSPITALS.map((h) => {
      const hospCells = cells[h] || {};
      const total = Object.values(hospCells).reduce(
        (s, cell) => s + (cell.user_override ?? cell.ocr_count ?? cell.filename_count ?? cell.count ?? 0),
        0,
      );
      return [h, total];
    }),
  );

  return (
    <div className="space-y-6">
      <section>
        <h2 className="text-sm uppercase text-slate-400 mb-2">Mes</h2>
        <div className="flex gap-2 flex-wrap">
          {months.map((m) => (
            <button
              key={m.session_id}
              onClick={() => openMonth(m.session_id, m.year, m.month)}
              className={`px-3 py-1.5 rounded text-sm border transition
                ${activeMonth === m.session_id
                  ? "bg-indigo-600 border-indigo-500"
                  : "bg-slate-900 border-slate-700 hover:bg-slate-800"
                }`}
            >
              {m.name} {m.year}
            </button>
          ))}
        </div>
      </section>

      {session && (
        <>
          <section className="flex gap-3">
            <button
              onClick={() => runScan(session.session_id)}
              disabled={loading}
              className="px-4 py-2 rounded bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50"
            >
              {loading ? "Escaneando…" : "Escanear todo"}
            </button>
            <button
              onClick={async () => {
                const r = await generateOutput(session.session_id);
                alert(`Generado: ${r.output_path}`);
              }}
              disabled={loading}
              className="px-4 py-2 rounded bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50"
            >
              Generar Resumen
            </button>
          </section>

          <section>
            <h2 className="text-sm uppercase text-slate-400 mb-2">Hospitales</h2>
            <div className="grid grid-cols-4 gap-4">
              {HOSPITALS.map((h) => (
                <HospitalCard
                  key={h}
                  hospital={h}
                  total={totalsByHospital[h]}
                  status={cells[h] ? "present" : "missing"}
                  onClick={() => selectHospital(h)}
                />
              ))}
            </div>
          </section>
        </>
      )}

      {error && <p className="text-red-400">{error}</p>}
    </div>
  );
}
