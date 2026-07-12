import { useEffect, useState } from "react";
import { Calendar, RefreshCw, FileSpreadsheet, FolderSync } from "lucide-react";
import { toast } from "sonner";
import { useSessionStore } from "../store/session";
import HospitalCard from "../components/HospitalCard";
import SparkGrid from "../components/SparkGrid";
import HistoryDrawer from "../components/HistoryDrawer";
import MonthReorgPanel from "../components/MonthReorgPanel";
import Button from "../ui/Button";
import { api } from "../lib/api";
import { computeCellCount } from "../lib/cellCount";
import { countTypeFor } from "../lib/sigla-info";
import { useHistory } from "../lib/useHistoryStore";

const HOSPITALS = ["HPV", "HRB", "HLU", "HLL"];

export default function MonthOverview() {
  // PF4: one selector per field, primitives/stable actions only — never a
  // bare useSessionStore() object destructure (re-renders on ANY store change).
  const months = useSessionStore((s) => s.months);
  const session = useSessionStore((s) => s.session);
  const loading = useSessionStore((s) => s.loading);
  // A11: `loading` is shared by openMonth/runScan/generateOutput — the scan
  // button must only claim "Escaneando…" while a pase-1 scan is actually
  // running. `scanning` is runScan's own truthful flag (openMonth's
  // first-open auto-scan fire-and-forgets runScan, which lights it —
  // correctly); `loading` keeps driving the disabled state of the buttons.
  const scanning = useSessionStore((s) => s.scanning);
  const error = useSessionStore((s) => s.error);
  const loadMonths = useSessionStore((s) => s.loadMonths);
  const openMonth = useSessionStore((s) => s.openMonth);
  const selectHospital = useSessionStore((s) => s.selectHospital);
  const runScan = useSessionStore((s) => s.runScan);
  const generateOutput = useSessionStore((s) => s.generateOutput);
  const historyView = useSessionStore((s) => s.historyView);
  const setHistoryView = useSessionStore((s) => s.setHistoryView);
  const historyDrawer = useSessionStore((s) => s.historyDrawer);
  const openHistoryDrawer = useSessionStore((s) => s.openHistoryDrawer);
  const closeHistoryDrawer = useSessionStore((s) => s.closeHistoryDrawer);
  const deleteReorgOp = useSessionStore((s) => s.deleteReorgOp);
  const exportManifest = useSessionStore((s) => s.exportManifest);
  // Zustand v5 footgun: default OUTSIDE the selector (see DetailPanel's
  // identical idiom) — a fresh `?? []` INSIDE the selector mints a new array
  // every render and loops React #185.
  const reorgOps = useSessionStore((s) => s.session?.reorg_ops) ?? [];

  const sessionId = session?.session_id;
  const { data: history } = useHistory(historyView ? sessionId : null);

  // G5 — generated RESUMEN files, so the home can open the last Excel directly.
  const [outputs, setOutputs] = useState([]);
  // Task 18 — "Reorganización del mes" is now the ONE export surface.
  const [reorgPanelOpen, setReorgPanelOpen] = useState(false);
  const pendingOpsTotal = reorgOps.filter((op) => op.status === "pending").length;

  useEffect(() => {
    loadMonths();
  }, [loadMonths]);

  useEffect(() => {
    api.listOutputs().then(setOutputs).catch(() => {});
  }, []);

  // Prefer the active month's Excel; fall back to the most recent generated.
  const activeOutput = outputs.find((o) => o.session_id === sessionId) ?? outputs[0];

  const activeMonth = sessionId;
  const cells = session?.cells || {};

  const totalsByHospital = Object.fromEntries(
    HOSPITALS.map((h) => {
      const hospCells = cells[h] || {};
      const total = Object.entries(hospCells).reduce(
        (s, [sigla, cell]) => s + computeCellCount(cell, countTypeFor(sigla)),
        0,
      );
      return [h, total];
    }),
  );

  const onGenerate = async () => {
    try {
      const r = await generateOutput(sessionId);
      const warn = r.worker_warnings?.length
        ? `Conteo de trabajadores incompleto en ${r.worker_warnings.length} celda(s): ${r.worker_warnings
            .map((w) => `${w.hospital}·${w.sigla}`)
            .join(", ")}`
        : undefined;
      toast.success(`Excel guardado en ${r.output_path}`, {
        icon: <FileSpreadsheet size={16} />,
        description: warn,
      });
      api.listOutputs().then(setOutputs).catch(() => {});
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
          <section className="space-y-2">
            <div className="flex gap-3">
              <Button
                variant="primary"
                icon={RefreshCw}
                disabled={loading}
                onClick={() => runScan(sessionId)}
              >
                {scanning ? "Escaneando…" : "Escanear todos los hospitales"}
              </Button>
              <Button
                icon={FileSpreadsheet}
                disabled={loading}
                onClick={onGenerate}
              >
                Generar Excel del mes
              </Button>
              <Button
                icon={FolderSync}
                disabled={loading}
                onClick={() => setReorgPanelOpen(true)}
              >
                Reorganización{pendingOpsTotal > 0 ? ` (${pendingOpsTotal})` : ""}
              </Button>
            </div>
            {activeOutput && (
              <a
                href={api.outputUrl(activeOutput.session_id)}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 text-xs text-po-text-muted hover:text-po-accent transition"
              >
                <FileSpreadsheet size={13} strokeWidth={1.75} />
                Último Excel: RESUMEN_{activeOutput.session_id}.xlsx
                <span className="text-po-text-subtle">
                  · {new Date(activeOutput.mtime_iso).toLocaleString()}
                </span>
              </a>
            )}
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
              <SparkGrid
                history={history}
                onCellClick={openHistoryDrawer}
                activeCell={historyDrawer}
              />
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

      <HistoryDrawer
        open={!!historyDrawer}
        hospital={historyDrawer?.hospital ?? null}
        sigla={historyDrawer?.sigla ?? null}
        series={
          historyDrawer
            ? history?.[`${historyDrawer.hospital}|${historyDrawer.sigla}`]
            : undefined
        }
        onClose={closeHistoryDrawer}
      />

      <MonthReorgPanel
        open={reorgPanelOpen}
        ops={reorgOps}
        onClose={() => setReorgPanelOpen(false)}
        onDelete={(opId) => deleteReorgOp(sessionId, opId)}
        onExport={() => exportManifest(sessionId)}
      />

      {error && <p className="text-po-error">{error}</p>}
    </div>
  );
}
