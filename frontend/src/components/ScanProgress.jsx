import { CheckCircle2, X, Loader2 } from "lucide-react";
import { useSessionStore } from "../store/session";
import Badge from "../ui/Badge";
import Button from "../ui/Button";

export default function ScanProgress() {
  const scanProgress = useSessionStore((s) => s.scanProgress);
  const session = useSessionStore((s) => s.session);
  const cancelScan = useSessionStore((s) => s.cancelScan);

  if (!scanProgress) return null;

  const { done, total, etaMs, terminal } = scanProgress;
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

  return (
    <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-40 bg-po-panel border border-po-border rounded-xl shadow-2xl p-4 min-w-[400px]">
      <div className="flex items-center gap-3 mb-2">
        <span className={iconColorClass}>{icon}</span>
        <span className="text-sm font-medium text-po-text">{label}</span>
        <Badge variant="neutral" className="ml-auto">{done}/{total}</Badge>
        {etaMs && !terminal && (
          <span className="text-xs text-po-text-muted">~{Math.round(etaMs / 1000)}s</span>
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
    </div>
  );
}
