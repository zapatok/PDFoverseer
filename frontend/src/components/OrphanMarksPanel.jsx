import { useState } from "react";
import { AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import Button from "../ui/Button";
import Dialog from "../ui/Dialog";
import { useSessionStore } from "../store/session";
import { fileSubtotal } from "../lib/worker-count";

/**
 * OrphanMarksPanel — reconcile worker/check marks whose PDF is no longer in the
 * cell folder (F1 / bug #2).
 *
 * A file rename or merge during a corpus reorganization orphans its marks: the
 * canonical (present-filtered) worker_count drops them, so the counted work
 * silently vanishes from the Excel. This panel makes that recoverable — migrate
 * the marks onto a present file, or discard them (with confirmation).
 *
 * Orphans are derived client-side from ``cell.worker_marks`` minus ``files``
 * (the names currently on disk, passed by DetailPanel). Renders ``null`` when
 * there are none. Respects the M3 cell lock via the ``locked`` prop.
 *
 * Props:
 *   hospital  {string}
 *   sigla     {string}
 *   cell      {object}   — the current cell (source of worker_marks)
 *   files     {string[]} — filenames present in the cell folder today
 *   sessionId {string}
 *   locked    {boolean}  — another participant holds this cell → disable actions
 */
export default function OrphanMarksPanel({
  hospital,
  sigla,
  cell,
  files = [],
  sessionId,
  locked = false,
}) {
  const reconcileWorkerMarks = useSessionStore((s) => s.reconcileWorkerMarks);
  const [dest, setDest] = useState({}); // { orphanName: destFile }
  const [confirmFile, setConfirmFile] = useState(null); // orphan pending discard

  const marks = cell?.worker_marks ?? {};
  const fileSet = new Set(files);
  const orphans = Object.keys(marks).filter((f) => !fileSet.has(f));

  if (orphans.length === 0) return null;

  const totalOrphanMarks = orphans.reduce((sum, o) => sum + fileSubtotal(marks, o), 0);
  const destFor = (orphan) => dest[orphan] ?? files[0] ?? "";
  const canMigrate = files.length > 0;

  async function handleMigrate(orphan) {
    const to = destFor(orphan);
    if (!to) return;
    try {
      // The store returns the enriched cell on success and null on a handled
      // 409 (it already toasted the lock holder) — never claim success on null.
      const result = await reconcileWorkerMarks(sessionId, hospital, sigla, {
        action: "migrate",
        from_file: orphan,
        to_file: to,
      });
      if (result) toast.success(`Marcas de ${orphan} migradas a ${to}`);
    } catch {
      toast.error("No se pudieron migrar las marcas");
    }
  }

  async function handleDiscard(orphan) {
    try {
      // Same success/409 contract as handleMigrate (null = handled lock 409).
      const result = await reconcileWorkerMarks(sessionId, hospital, sigla, {
        action: "discard",
        from_file: orphan,
      });
      if (result) toast.success(`Marcas de ${orphan} descartadas`);
    } catch {
      toast.error("No se pudieron descartar las marcas");
    } finally {
      setConfirmFile(null);
    }
  }

  return (
    <div className="mt-6">
      <div className="rounded-lg border border-po-suspect-border bg-po-suspect-bg px-3 py-2.5 text-xs text-po-suspect">
        <div className="mb-2 flex items-center gap-2">
          <AlertTriangle size={14} strokeWidth={1.75} className="shrink-0" />
          <span>
            {totalOrphanMarks} marcas pertenecen a archivos que ya no están en la carpeta.
          </span>
        </div>
        <ul className="space-y-2">
          {orphans.map((orphan) => (
            <li key={orphan} className="flex flex-wrap items-center gap-2">
              <span className="min-w-0 flex-1 truncate font-mono text-po-text">
                {orphan} — {fileSubtotal(marks, orphan)} marcas
              </span>
              <select
                aria-label={`Migrar ${orphan} a`}
                value={destFor(orphan)}
                disabled={locked || !canMigrate}
                onChange={(e) => setDest((d) => ({ ...d, [orphan]: e.target.value }))}
                className="rounded border border-po-border bg-po-bg px-2 py-1 text-xs text-po-text focus:border-po-accent focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {files.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </select>
              <Button
                size="sm"
                variant="secondary"
                disabled={locked || !canMigrate}
                onClick={() => handleMigrate(orphan)}
              >
                Migrar
              </Button>
              <Button
                size="sm"
                variant="destructive"
                disabled={locked}
                onClick={() => setConfirmFile(orphan)}
              >
                Descartar
              </Button>
            </li>
          ))}
        </ul>
      </div>

      {confirmFile && (
        <Dialog open onOpenChange={(open) => !open && setConfirmFile(null)}>
          <Dialog.Header>
            <Dialog.Title className="text-sm font-medium text-po-text">
              Descartar marcas
            </Dialog.Title>
          </Dialog.Header>
          <Dialog.Body className="flex-col gap-4 p-5">
            <Dialog.Description className="text-sm text-po-text">
              Se descartarán {fileSubtotal(marks, confirmFile)} marcas de {confirmFile}. Esta
              acción no se puede deshacer.
            </Dialog.Description>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setConfirmFile(null)}>
                Cancelar
              </Button>
              <Button variant="destructive" onClick={() => handleDiscard(confirmFile)}>
                Descartar
              </Button>
            </div>
          </Dialog.Body>
        </Dialog>
      )}
    </div>
  );
}
