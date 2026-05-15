import { useEffect } from "react";
import { Calendar, RefreshCw, FileSpreadsheet } from "lucide-react";
import { toast } from "sonner";
import { useSessionStore } from "../store/session";
import HospitalCard from "../components/HospitalCard";
import SparkGrid from "../components/SparkGrid";
import Button from "../ui/Button";
import { useHistory } from "../lib/useHistoryStore";

const HOSPITALS = ["HPV", "HRB", "HLU", "HLL"];

export default function MonthOverview() {
  const {
    months, session, loading, error,
    loadMonths, openMonth, selectHospital, runScan, generateOutput,
    historyView, setHistoryView,
  } = useSessionStore();

  const sessionId = session?.session_id;
  const { data: history } = useHistory(historyView ? sessionId : null);

  useEffect(() => {
    loadMonths();
  }, [loadMonths]);

  const activeMonth = sessionId;
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

  const onGenerate = async () => {
    try {
      const r = await generateOutput(sessionId);
      toast.success(`Excel guardado en ${r.output_path}`, { icon: <FileSpreadsheet size={16} /> });
    } catch (err) {
      toast.error(`No se pudo generar el Excel: ${String(err)}`);
    }
  };

  return (
    <div className="space-y-8">
      <section>
        <h2 className="text-xs font-medium uppercase tracking-wider text-po-text-muted mb-3">Mes</h2>
        <div className="flex gap-2 flex-wrap">
          {months.map((m) => (
            <button
              key={m.session_id}
              onClick={() => openMonth(m.session_id, m.year, m.month)}
              className={[
                "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm border transition",
                activeMonth === m.session_id
                  ? "bg-po-accent text-white border-po-accent"
                  : "bg-po-panel border-po-border hover:border-po-border-strong text-po-text",
              ].join(" ")}
            >
              <Calendar size={14} strokeWidth={1.75} />
              {m.name} {m.year}
            </button>
          ))}
        </div>
      </section>

      {session && (
        <>
          <section className="flex gap-3">
            <Button
              variant="primary"
              icon={RefreshCw}
              disabled={loading}
              onClick={() => runScan(sessionId)}
            >
              {loading ? "Escaneando…" : "Escanear todos los hospitales"}
            </Button>
            <Button
              icon={FileSpreadsheet}
              disabled={loading}
              onClick={onGenerate}
            >
              Generar Excel del mes
            </Button>
          </section>

          <section>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-xs font-medium uppercase tracking-wider text-po-text-muted">Hospitales</h2>
              <div className="flex bg-po-panel border border-po-border rounded-md p-0.5 text-xs">
                <button
                  type="button"
                  onClick={() => setHistoryView(false)}
                  className={`px-3 py-1 rounded transition ${
                    !historyView
                      ? "bg-po-panel-hover text-po-text font-semibold"
                      : "text-po-text-muted"
                  }`}
                >
                  Mes actual
                </button>
                <button
                  type="button"
                  onClick={() => setHistoryView(true)}
                  className={`px-3 py-1 rounded transition ${
                    historyView
                      ? "bg-po-panel-hover text-po-text font-semibold"
                      : "text-po-text-muted"
                  }`}
                >
                  Histórico
                </button>
              </div>
            </div>
            {historyView ? (
              <SparkGrid history={history} />
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
                {HOSPITALS.map((h) => (
                  <HospitalCard
                    key={h}
                    hospital={h}
                    total={totalsByHospital[h]}
                    cells={cells[h]}
                    status={cells[h] ? "present" : "missing"}
                    onClick={() => selectHospital(h)}
                  />
                ))}
              </div>
            )}
          </section>
        </>
      )}

      {error && <p className="text-po-error">{error}</p>}
    </div>
  );
}
