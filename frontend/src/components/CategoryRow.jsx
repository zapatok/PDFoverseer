import {
  Loader2, AlertCircle, FileStack, PenLine,
} from "lucide-react";
import { useSessionStore } from "../store/session";
import Badge from "../ui/Badge";
import Dot from "../ui/Dot";
import Tooltip from "../ui/Tooltip";
import { SIGLA_LABELS } from "../lib/sigla-labels";
import InlineEditCount from "./InlineEditCount";

function dotVariantFor(cell, isScanning, hasOverride) {
  if (isScanning) return "state-scanning";
  if (cell?.errors?.length > 0) return "state-error";
  if (hasOverride) return "state-override";
  if (cell?.flags?.includes("compilation_suspect")) return "state-suspect";
  if (cell?.confidence === "high") return "confidence-high";
  if (cell?.confidence === "low") return "confidence-low";
  return "neutral";
}

function effectiveCount(cell) {
  return cell?.user_override ?? cell?.ocr_count ?? cell?.filename_count ?? cell?.count ?? 0;
}


export default function CategoryRow({
  sigla,
  cell,
  hospital,
  selected,
  onSelect,
  checked,
  onCheckChange,
  mode = "scanned",
  autoFocus = false,
  onCommitNext,
}) {
  const scanningCells = useSessionStore((s) => s.scanningCells);
  const pendingSaves = useSessionStore((s) => s.pendingSaves);
  const session = useSessionStore((s) => s.session);
  const saveOverride = useSessionStore((s) => s.saveOverride);

  const cellKey = `${hospital}|${sigla}`;
  const isScanning = scanningCells.has(cellKey);
  const isPendingSave = pendingSaves[cellKey] === "saving";
  const hasOverride = cell?.user_override !== null && cell?.user_override !== undefined;
  const isCompilationSuspect = cell?.flags?.includes("compilation_suspect");
  const hasError = cell?.errors?.length > 0;
  const showMethodChip = mode === "scanned" && cell?.count != null;
  const placeholder = mode === "manual" ? "—" : null;

  const onCommitCount = (v) => {
    saveOverride(session.session_id, hospital, sigla, v, cell?.override_note ?? null, { manual: mode === "manual" });
    if (mode === "manual") onCommitNext?.();
  };

  return (
    <div
      onClick={onSelect}
      className={[
        "flex items-center gap-3 px-3 h-8 cursor-pointer transition",
        "hover:bg-po-panel-hover",
        selected && "bg-po-panel-hover border-l-2 border-po-accent",
      ].filter(Boolean).join(" ")}
    >
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onCheckChange(e.target.checked)}
        onClick={(e) => e.stopPropagation()}
        className="accent-po-accent"
      />
      <Tooltip content={SIGLA_LABELS[sigla] ?? null}>
        <span className="font-mono text-xs text-po-text">{sigla}</span>
      </Tooltip>
      <Dot variant={dotVariantFor(cell, isScanning, hasOverride)} className={isPendingSave ? "animate-pulse" : ""} />

      <div className="ml-auto flex items-center gap-2">
        {isScanning ? (
          <Badge variant="state-scanning" icon={Loader2}>Escaneando…</Badge>
        ) : (
          <>
            {hasError && (
              <Tooltip content={cell.errors[0]}>
                <span><Badge variant="state-error" icon={AlertCircle}>Error</Badge></span>
              </Tooltip>
            )}
            {showMethodChip && hasOverride && <Badge variant="state-override" icon={PenLine}>Manual</Badge>}
            {showMethodChip && isCompilationSuspect && !hasOverride && (
              <Tooltip content="Probable compilación (PDF con >5× páginas esperadas)">
                <span><Badge variant="state-suspect" icon={FileStack}>Compilación</Badge></span>
              </Tooltip>
            )}
            <InlineEditCount
              value={effectiveCount(cell)}
              onCommit={onCommitCount}
              placeholder={placeholder}
              autoFocus={autoFocus}
            />
          </>
        )}
      </div>
    </div>
  );
}
