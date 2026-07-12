import Button from "../ui/Button";
import Dialog from "../ui/Dialog";
import { useSessionStore } from "../store/session";

/**
 * §A5 — the OCR cost guard's in-app confirm dialog, replacing window.confirm
 * (which blocked the thread and couldn't show a breakdown). Renders only
 * when the store has staged a pendingScanConfirm (scanOcr, over the PDF
 * threshold). Confirmar launches the staged scan; Cancelar discards it.
 */
export default function ScanConfirmDialog() {
  const pending = useSessionStore((s) => s.pendingScanConfirm);
  const confirmScanOcr = useSessionStore((s) => s.confirmScanOcr);
  const cancelScanOcr = useSessionStore((s) => s.cancelScanOcr);

  if (!pending) return null;

  const cellCount = pending.cellPairs?.length ?? 0;

  return (
    <Dialog open onOpenChange={(open) => !open && cancelScanOcr()}>
      <Dialog.Header>
        <Dialog.Title className="text-sm font-medium text-po-text">
          Confirmar escaneo OCR
        </Dialog.Title>
      </Dialog.Header>
      <Dialog.Body className="flex-col gap-4 p-5">
        <Dialog.Description className="text-sm text-po-text">
          Vas a escanear con OCR {pending.totalPdfs} PDF{pending.totalPdfs === 1 ? "" : "s"} en{" "}
          {cellCount} celda{cellCount === 1 ? "" : "s"} (~{pending.mins} min). En categorías de
          régimen 1 el conteo por nombre de archivo ya suele ser correcto. ¿Continuar?
        </Dialog.Description>
        <ul className="text-xs text-po-text-muted space-y-0.5">
          <li>
            {cellCount} celda{cellCount === 1 ? "" : "s"}
          </li>
          <li>
            {pending.totalPdfs} PDF{pending.totalPdfs === 1 ? "" : "s"}
          </li>
          <li>ETA: ~{pending.mins} min</li>
        </ul>
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={cancelScanOcr}>
            Cancelar
          </Button>
          <Button variant="primary" onClick={confirmScanOcr}>
            Confirmar
          </Button>
        </div>
      </Dialog.Body>
    </Dialog>
  );
}
