import { useSessionStore } from "../store/session";

export default function CategoryRow({
  sigla,
  cell,
  selected,
  onClick,
  hospital,
  checked,
  onCheckChange,
}) {
  const { scanningCells } = useSessionStore();
  const isScanning = scanningCells.has(`${hospital}|${sigla}`);
  const count =
    cell?.user_override ?? cell?.ocr_count ?? cell?.filename_count ?? cell?.count ?? 0;
  const conf = cell?.confidence || "—";
  const hasErrors = (cell?.errors || []).length > 0;
  const isSuspect = (cell?.flags || []).includes("compilation_suspect");

  return (
    <div
      onClick={onClick}
      className={`flex items-center gap-2 px-2 py-1 rounded cursor-pointer text-sm ${selected ? "bg-slate-800" : "hover:bg-slate-800/50"}`}
    >
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => {
          e.stopPropagation();
          onCheckChange(e.target.checked);
        }}
        onClick={(e) => e.stopPropagation()}
      />
      <span className="flex-1 font-mono">{sigla}</span>
      <span className="text-xs text-slate-400 uppercase">{conf}</span>
      <span className="font-mono w-12 text-right">{count}</span>
      {isScanning && <span className="text-blue-400 animate-pulse">⟳</span>}
      {hasErrors && <span className="text-red-400">✕</span>}
      {isSuspect && !isScanning && <span className="text-amber-400">⚠</span>}
    </div>
  );
}
