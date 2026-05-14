import { MousePointer2, FileStack, PenLine } from "lucide-react";
import OverridePanel from "./OverridePanel";
import EmptyState from "../ui/EmptyState";
import Badge from "../ui/Badge";
import Tooltip from "../ui/Tooltip";
import { SIGLA_LABELS } from "../lib/sigla-labels";
import { METHOD_LABEL, CONFIDENCE_LABEL } from "../lib/method-labels";

function effectiveCount(cell) {
  return cell?.user_override ?? cell?.ocr_count ?? cell?.filename_count ?? cell?.count ?? 0;
}

function confidenceVariant(cell) {
  if (cell?.confidence === "high") return "confidence-high";
  if (cell?.confidence === "low") return "confidence-low";
  return "neutral";
}

export default function DetailPanel({ hospital, sigla, cell }) {
  if (!cell || !sigla) {
    return (
      <EmptyState
        icon={MousePointer2}
        title="Selecciona una categoría"
        description="Elige una sigla de la lista para ver el conteo, ajustar manualmente y abrir los archivos."
      />
    );
  }

  const isCompilationSuspect = cell.flags?.includes("compilation_suspect");
  const hasOverride = cell.user_override !== null && cell.user_override !== undefined;
  const total = effectiveCount(cell);
  const label = SIGLA_LABELS[sigla];
  const showLabel = label && label.toLowerCase() !== sigla.toLowerCase();

  return (
    <div className="rounded-xl bg-po-panel border border-po-border p-5">
      <div className="flex items-baseline gap-2 mb-1">
        <span className="font-mono text-sm text-po-text">{sigla}</span>
        {showLabel && (
          <>
            <span className="text-po-text-muted">·</span>
            <span className="text-sm text-po-text">{label}</span>
          </>
        )}
      </div>

      <p className="text-5xl font-semibold tabular-nums mt-4">{total.toLocaleString()}</p>
      <p className="text-xs text-po-text-muted mt-0.5">documentos</p>

      <div className="flex flex-wrap gap-2 mt-3">
        {isCompilationSuspect && (
          <Tooltip content="Probable compilación (PDF con >5× páginas esperadas)">
            <span><Badge variant="state-suspect" icon={FileStack}>Compilación</Badge></span>
          </Tooltip>
        )}
        {cell.confidence && (
          <Badge variant={confidenceVariant(cell)}>{CONFIDENCE_LABEL[cell.confidence] ?? cell.confidence}</Badge>
        )}
        {hasOverride && <Badge variant="state-override" icon={PenLine}>Manual</Badge>}
      </div>

      <h4 className="text-xs font-medium uppercase tracking-wider text-po-text-muted mt-6 mb-2">Conteo automático</h4>
      <table className="w-full text-sm">
        <tbody>
          <tr>
            <td className="text-po-text-muted py-1">Por nombre de archivo</td>
            <td className="text-right font-mono tabular-nums">{cell.filename_count ?? "—"}</td>
          </tr>
          <tr>
            <td className="text-po-text-muted py-1">Por OCR</td>
            <td className="text-right font-mono tabular-nums">{cell.ocr_count ?? "—"}</td>
          </tr>
          <tr>
            <td className="text-po-text-muted py-1">Método</td>
            <td className="text-right">
              <Tooltip content={`Token interno: ${cell.method ?? "—"}`}>
                <span>{METHOD_LABEL[cell.method] ?? cell.method ?? "—"}</span>
              </Tooltip>
            </td>
          </tr>
        </tbody>
      </table>

      <h4 className="text-xs font-medium uppercase tracking-wider text-po-text-muted mt-6 mb-2">Ajuste manual</h4>
      <OverridePanel hospital={hospital} sigla={sigla} cell={cell} />
    </div>
  );
}
