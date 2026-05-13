import { useSessionStore } from "../store/session";

export default function ScanProgress() {
  const { session, scanProgress, cancelScan } = useSessionStore();
  if (!scanProgress) return null;
  const { done, total, terminal } = scanProgress;
  const pct = total > 0 ? Math.round((done / total) * 100) : 0;

  let label = `Escaneando · ${done}/${total}`;
  let color = "bg-blue-600";
  if (terminal === "complete") {
    label = `Completado · ${done}/${total}`;
    color = "bg-emerald-600";
  }
  if (terminal === "cancelled") {
    label = `Cancelado · ${done}/${total}`;
    color = "bg-amber-600";
  }

  return (
    <div className="fixed bottom-0 left-0 right-0 bg-slate-900 border-t border-slate-700 px-4 py-2 flex items-center gap-4 text-sm z-40">
      <span className="font-medium">{label}</span>
      <div className="flex-1 h-2 bg-slate-800 rounded overflow-hidden">
        <div className={`h-full transition-all ${color}`} style={{ width: `${pct}%` }} />
      </div>
      {!terminal && session && (
        <button
          onClick={() => cancelScan(session.session_id)}
          className="px-3 py-1 rounded bg-slate-700 hover:bg-slate-600 text-xs"
        >
          Cancel
        </button>
      )}
    </div>
  );
}
