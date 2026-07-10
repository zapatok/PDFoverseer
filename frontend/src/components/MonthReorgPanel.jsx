import { X, Download } from "lucide-react";
import * as RadixDialog from "@radix-ui/react-dialog";
import Button from "../ui/Button";
import { OpRow } from "./ReorganizacionPanel";
import { useSessionStore } from "../store/session";
import { cellLockHolder } from "../lib/presence";
import { getParticipantId } from "../lib/identity";

/**
 * MonthReorgPanel — "Reorganización del mes": the ONE session-wide export
 * surface (Task 18). Opened from the MonthOverview header. Lists every
 * PENDING reorg op across all hospitals/siglas, delete per-op, and hosts the
 * single Exportar manifiesto button (the backend export already writes ALL
 * pending ops, so a per-cell export button — removed from ReorganizacionPanel
 * in this same change — was misleading: "quiero que exista en un solo lugar
 * donde exporte todos los cambios", Daniel 2026-07-08).
 *
 * Grouping decision (documented, not accidental): ops are grouped by their
 * SOURCE cell only — the op is executed FROM the source file, so that's the
 * cell the operator was looking at when they created it. A cross-cell op
 * (e.g. extract_pages from HRB|altura to HRB|insgral) lists under its source
 * group ("HRB · altura"); the destination still renders inline per row via
 * the reused OpRow (isOutgoing=true: file → dest). The per-cell
 * ReorganizacionPanel is unaffected — it keeps showing incoming ops for the
 * destination cell too, from that cell's point of view.
 *
 * Applied ops are hidden entirely: they're already reflected in the counts,
 * nothing left to review, delete, or export for them.
 *
 * Props:
 *   open      {boolean}    — dialog visibility
 *   ops       {object[]}   — full session.reorg_ops (all hospitals)
 *   onClose   {fn()}
 *   onDelete  {fn(opId)}
 *   onExport  {fn()}
 */
export default function MonthReorgPanel({ open, ops = [], onClose, onDelete, onExport }) {
  // M3 lock visibility (per-cell F3 precedent, mirrored from DetailPanel):
  // this panel spans cells, so each row derives its own `locked` from the
  // op's SOURCE cell — a delete against a cell held by another participant
  // would just 409, so it must not look clickable. Raw selector, no `?? []`
  // inside (Zustand v5 footgun); presence is always initialized in the store,
  // and cellLockHolder tolerates undefined anyway.
  const presence = useSessionStore((s) => s.presence);
  const selfId = getParticipantId();

  const pending = ops.filter((op) => op.status === "pending");
  const hasPending = pending.length > 0;

  // Group by SOURCE cell key — Map preserves insertion order so groups
  // appear in the order their first pending op appears in `ops`.
  const groups = new Map();
  for (const op of pending) {
    const key = `${op.source?.hospital ?? "?"} · ${op.source?.sigla ?? "?"}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(op);
  }

  return (
    <RadixDialog.Root open={open} onOpenChange={(v) => !v && onClose()}>
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="fixed inset-0 z-50 bg-black/70" />
        <RadixDialog.Content
          className="fixed left-1/2 top-1/2 z-[51] flex max-h-[80vh] w-full max-w-lg -translate-x-1/2 -translate-y-1/2 flex-col rounded-xl border border-po-border bg-po-bg shadow-2xl focus-visible:outline-none"
          aria-describedby={undefined}
        >
          <RadixDialog.Title asChild>
            <header className="flex items-center gap-3 border-b border-po-border px-5 py-3">
              <span className="flex-1 min-w-0 text-sm font-medium text-po-text">
                Reorganización del mes
              </span>
              <RadixDialog.Close
                className="shrink-0 text-po-text-muted hover:text-po-text"
                aria-label="Cerrar"
              >
                <X size={18} strokeWidth={1.75} />
              </RadixDialog.Close>
            </header>
          </RadixDialog.Title>

          <div className="flex-1 overflow-y-auto px-5 py-3">
            {!hasPending ? (
              <p className="text-sm text-po-text-muted">Sin operaciones pendientes</p>
            ) : (
              [...groups.entries()].map(([key, groupOps]) => (
                <div key={key} className="mb-4 last:mb-0">
                  <h4 className="mb-1 text-xs font-medium uppercase tracking-wider text-po-text-muted">
                    {key}
                  </h4>
                  <ul className="divide-y divide-po-border">
                    {groupOps.map((op) => (
                      <OpRow
                        key={op.id}
                        op={op}
                        isOutgoing
                        onDelete={onDelete}
                        locked={
                          !!cellLockHolder(
                            presence,
                            op.source?.hospital,
                            op.source?.sigla,
                            selfId,
                          )
                        }
                      />
                    ))}
                  </ul>
                </div>
              ))
            )}
          </div>

          <footer className="border-t border-po-border px-5 py-3 flex justify-end">
            <Button
              variant="secondary"
              icon={Download}
              size="sm"
              disabled={!hasPending}
              onClick={onExport}
              data-testid="export-btn"
            >
              Exportar manifiesto
            </Button>
          </footer>
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}
