import { Loader2 } from "lucide-react";

// Per-page progress bar for a single-file OCR scan (rev-2 #1). When the page
// total is unknown (pagination siglas have no per-page hook) the bar is
// indeterminate.
export default function FileViewerProgress({ page, pagesTotal }) {
  const known = pagesTotal > 0;
  const pct = known ? Math.min(100, Math.round((page / pagesTotal) * 100)) : 0;
  return (
    <div className="mt-4 rounded-lg border border-po-border bg-po-panel px-3 py-2">
      <div className="flex items-center justify-between mb-1.5">
        <span className="inline-flex items-center gap-1.5 text-xs text-po-scanning">
          <Loader2 size={13} strokeWidth={1.75} className="animate-spin" />
          Escaneando…
        </span>
        {known && (
          <span className="text-xs tabular-nums text-po-text-muted">
            página {page} de {pagesTotal}
          </span>
        )}
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
