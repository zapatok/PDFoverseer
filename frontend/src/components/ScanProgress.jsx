import { CheckCircle2, X, Loader2, AlertTriangle, RotateCcw } from "lucide-react";
import { useSessionStore } from "../store/session";
import Badge from "../ui/Badge";
import Button from "../ui/Button";
import { formatEta } from "../lib/scanCost";

export default function ScanProgress() {
  const scanProgress = useSessionStore((s) => s.scanProgress);
  const session = useSessionStore((s) => s.session);
  const cancelScan = useSessionStore((s) => s.cancelScan);
  const scanOcr = useSessionStore((s) => s.scanOcr);

  if (!scanProgress) return null;

  const { done, total, etaMs, terminal, pdfName } = scanProgress;
  // Default skipped to [] OUTSIDE the selector to avoid Zustand v5 fresh-literal footgun.
  const skipped = scanProgress.skipped ?? [];
  const pct = total > 0 ? Math.min(100, (done / total) * 100) : 0;

  let icon, label, iconColorClass;
  if (terminal === "complete") {
    icon = <CheckCircle2 size={16} strokeWidth={1.75} />;
    iconColorClass = "text-po-success";
    label = "Completado";
  } else if (terminal === "cancelled") {
    icon = <X size={16} strokeWidth={1.75} />;
    iconColorClass = "text-po-error";
    label = "Cancelado";
  } else {
    icon = <Loader2 size={16} strokeWidth={1.75} className="animate-spin" />;
    iconColorClass = "text-po-scanning";
    label = "Escaneando…";
  }

  // M3b: when the scan is complete but some cells were skipped (a human was
  // editing them), show a persistent suspect-tone summary with a re-scan action.
  const hasSkipped = terminal === "complete" && skipped.length > 0;

  function handleRescan() {
    if (!session?.session_id) return;
    const pairs = skipped.map((c) => [c.hospital, c.sigla]);
    scanOcr(session.session_id, pairs);
  }

  function handleDismiss() {
    // Force-clear the scanProgress; the store would have auto-dismissed if
    // skipped were empty, but we need a manual dismiss path here.
    useSessionStore.setState({ scanProgress: null });
  }

  return (
    <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-40 bg-po-panel border border-po-border rounded-xl shadow-2xl p-4 min-w-[400px]">
      <div className="flex items-center gap-3 mb-2">
        <span className={iconColorClass}>{icon}</span>
        <span className="text-sm font-medium text-po-text">{label}</span>
        {pdfName && !terminal && (
          <span className="text-xs text-po-text-muted truncate max-w-[180px]" title={pdfName}>
            {pdfName}
          </span>
        )}
        <Badge variant="neutral" className="ml-auto">{done}/{total}</Badge>
        {etaMs && !terminal && (
          <span className="text-xs text-po-text-muted">{formatEta(etaMs)}</span>
        )}
        {!terminal && (
          <Button
            variant="destructive"
            size="sm"
            onClick={() => cancelScan(session.session_id)}
          >
            Cancelar
          </Button>
        )}
      </div>
      <div className="h-1.5 bg-po-border rounded-full overflow-hidden">
        <div
          className="h-full bg-po-accent transition-all duration-200"
          style={{ width: `${pct}%` }}
        />
      </div>

      {/* M3b — skipped-cells summary (persistent; shown only when complete + skipped > 0) */}
      {hasSkipped && (
        <div className="mt-3 rounded-lg border border-po-suspect-border bg-po-suspect-bg p-3">
          <div className="flex items-center justify-between gap-2 mb-2">
            <div className="flex items-center gap-1.5 text-xs font-medium text-po-suspect">
              <AlertTriangle size={14} strokeWidth={1.75} />
              <span>
                {skipped.length === 1
                  ? "1 celda saltada (en edición)"
                  : `${skipped.length} celdas saltadas (en edición)`}
              </span>
            </div>
            <button
              type="button"
              className="text-po-text-muted hover:text-po-text transition-colors"
              aria-label="Cerrar"
              onClick={handleDismiss}
            >
              <X size={14} strokeWidth={1.75} />
            </button>
          </div>
          <ul className="text-xs text-po-suspect space-y-0.5 mb-3">
            {skipped.map((c) => (
              <li key={`${c.hospital}|${c.sigla}`} className="font-mono">
                {c.hospital} · {c.sigla}
              </li>
            ))}
          </ul>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleRescan}
          >
            <RotateCcw size={13} strokeWidth={1.75} className="mr-1.5" />
            Re-escanear saltadas
          </Button>
        </div>
      )}
    </div>
  );
}
