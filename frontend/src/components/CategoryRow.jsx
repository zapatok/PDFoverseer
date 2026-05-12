import ScanIndicator from "./ScanIndicator";
import ConfidenceBadge from "./ConfidenceBadge";

function deriveStatus(cell) {
  if (!cell) return "pending";
  if (cell.user_override != null) return "manual";
  if (cell.errors?.length) return "error";
  if (cell.flags?.includes("compilation_suspect")) return "done_review";
  if (cell.confidence === "high") return "done_high";
  return "done_review";
}

export default function CategoryRow({ sigla, cell, selected, onClick }) {
  const count = cell?.user_override ?? cell?.count ?? 0;
  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center justify-between gap-3 px-3 py-2 rounded transition
        ${selected ? "bg-slate-800" : "hover:bg-slate-900"}`}
    >
      <ScanIndicator status={deriveStatus(cell)} />
      <span className="flex-1 text-left font-mono text-sm">{sigla}</span>
      <ConfidenceBadge confidence={cell?.confidence} />
      <span className="text-right tabular-nums font-semibold w-16">{count}</span>
    </button>
  );
}
