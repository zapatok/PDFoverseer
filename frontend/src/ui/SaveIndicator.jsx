import { useEffect, useState } from "react";
import { Loader2, CheckCircle2, AlertCircle } from "lucide-react";

/**
 * status: 'idle' | 'saving' | 'saved' | 'error'
 *
 * idle: nothing rendered
 * saving: spinner + "Guardando…" in muted text
 * saved: check + "Guardado" in success color — auto-fades after 2s back to idle (the parent should set status back to 'idle' too, but the visual fades regardless)
 * error: alert + "No se pudo guardar" — sticky (no auto-fade)
 */
export default function SaveIndicator({ status = "idle" }) {
  const [visible, setVisible] = useState(status !== "idle");

  useEffect(() => {
    if (status === "saved") {
      setVisible(true);
      const t = setTimeout(() => setVisible(false), 2000);
      return () => clearTimeout(t);
    }
    setVisible(status !== "idle");
  }, [status]);

  if (!visible) return null;

  if (status === "saving") {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-po-text-muted">
        <Loader2 size={12} strokeWidth={2} className="animate-spin" />
        Guardando…
      </span>
    );
  }
  if (status === "saved") {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-po-success">
        <CheckCircle2 size={12} strokeWidth={2} />
        Guardado
      </span>
    );
  }
  if (status === "error") {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-po-error">
        <AlertCircle size={12} strokeWidth={2} />
        No se pudo guardar
      </span>
    );
  }
  return null;
}
