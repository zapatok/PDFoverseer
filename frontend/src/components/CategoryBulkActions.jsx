import { CheckCircle2, Scan } from "lucide-react";
import { useSessionStore } from "../store/session";
import { isCellReady } from "../lib/cell-status";
import { countTypeFor } from "../lib/sigla-info";
import Button from "../ui/Button";

// Two bulk actions above the category list (conteo-confiable Tema A):
//  - "Escanear pendientes": OCR only the amber (pendiente) cells.
//  - "Marcar seleccionadas como listas": confirm the checked cells by hand.
export default function CategoryBulkActions({ hospital, cells, selectedSiglas, onMarkedReady }) {
  const session = useSessionStore((s) => s.session);
  const scanPending = useSessionStore((s) => s.scanPending);
  const confirmCell = useSessionStore((s) => s.confirmCell);

  const pendingCount = Object.entries(cells).filter(([sigla, c]) => !isCellReady(c, countTypeFor(sigla))).length;
  const selectedCount = selectedSiglas.length;

  const onScanPending = () => {
    if (pendingCount === 0) return;
    scanPending(session.session_id, hospital);
  };

  const onMarkReady = () => {
    if (selectedCount === 0) return;
    for (const sigla of selectedSiglas) {
      confirmCell(session.session_id, hospital, sigla, true);
    }
    onMarkedReady?.();
  };

  return (
    <div className="flex items-center gap-2 mb-3">
      <Button
        size="sm"
        variant={pendingCount > 0 ? "primary" : "secondary"}
        icon={Scan}
        disabled={pendingCount === 0}
        onClick={onScanPending}
      >
        {pendingCount > 0 ? `Escanear pendientes (${pendingCount})` : "Sin pendientes"}
      </Button>
      <Button
        size="sm"
        variant="secondary"
        icon={CheckCircle2}
        disabled={selectedCount === 0}
        onClick={onMarkReady}
      >
        {selectedCount > 0 ? `Marcar ${selectedCount} como listas` : "Marcar seleccionadas"}
      </Button>
    </div>
  );
}
