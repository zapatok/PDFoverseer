import { Loader2, X } from "lucide-react";

// Per-page progress bar for a single-file OCR scan (rev-2 #1). When the page
// total is unknown (pagination siglas have no per-page hook) the bar is
// indeterminate. U6: onCancel (optional) renders a small Cancelar button that
// stops this scan — it shares the same /cancel endpoint the batch progress
// bar uses (ScanProgress.jsx), now wired to the single-file scan too.
export default function FileViewerProgress({ page, pagesTotal, onCancel }) {
  const known = pagesTotal > 0;
  const pct = known ? Math.min(100, Math.round((page / pagesTotal) * 100)) : 0;
  return (
    <div className="mt-4 rounded-lg border border-po-border bg-po-panel px-3 py-2">
      <div className="flex items-center justify-between mb-1.5">
        <span className="inline-flex items-center gap-1.5 text-xs text-po-scanning">
          <Loader2 size={13} strokeWidth={1.75} className="animate-spin" />
          Escaneando…
        </span>
        <div className="flex items-center gap-2">
          {known && (
            <span className="text-xs tabular-nums text-po-text-muted">
              página {page} de {pagesTotal}
            </span>
          )}
          {onCancel && (
            <button
              type="button"
              onClick={onCancel}
              className="inline-flex items-center gap-1 text-xs text-po-error hover:underline"
            >
              <X size={12} strokeWidth={1.75} />
              Cancelar
            </button>
          )}
        </div>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-po-border">
        {known ? (
          <div
            className="h-full bg-po-accent transition-all duration-200"
            style={{ width: `${pct}%` }}
          />
        ) : (
          <div className="h-full w-1/3 animate-pulse bg-po-accent" />
        )}
      </div>
    </div>
  );
}
