import { Building2, FolderX, PenLine } from "lucide-react";
import Dot from "../ui/Dot";
import Button from "../ui/Button";
import EmptyState from "../ui/EmptyState";
import Tooltip from "../ui/Tooltip";

const SIGLAS = [
  "reunion", "irl", "odi", "charla", "chintegral", "dif_pts",
  "art", "insgral", "bodega", "maquinaria", "ext", "senal",
  "exc", "altura", "caliente", "herramientas_elec", "andamios", "chps",
];

function dotVariantFor(cell) {
  if (!cell) return "neutral";
  if (cell.errors?.length > 0) return "state-error";
  if (cell.user_override !== null && cell.user_override !== undefined) return "state-override";
  if (cell.flags?.includes("compilation_suspect")) return "state-suspect";
  if (cell.confidence === "high") return "confidence-high";
  if (cell.confidence === "low") return "confidence-low";
  return "neutral";
}

export default function HospitalCard({ hospital, total, cells, status, onClick }) {
  if (status === "missing") {
    return (
      <div className="rounded-xl bg-po-panel border border-po-border p-5">
        <div className="flex items-center gap-2 mb-3">
          <Building2 size={14} strokeWidth={1.75} className="text-po-text-muted" />
          <span className="text-sm font-medium text-po-text">{hospital}</span>
        </div>
        <EmptyState
          icon={FolderX}
          title="Sin carpeta normalizada"
          description={`${hospital} no entrega PDFs por carpeta este mes. El flujo de ingreso manual estará disponible en una versión próxima.`}
          action={
            <Tooltip content="Disponible en FASE 4">
              <span>
                <Button disabled icon={PenLine}>Ingresar conteos</Button>
              </span>
            </Tooltip>
          }
        />
      </div>
    );
  }

  return (
    <button
      onClick={onClick}
      className="text-left rounded-xl bg-po-panel border border-po-border p-5 hover:border-po-border-strong transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-po-accent"
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Building2 size={14} strokeWidth={1.75} className="text-po-text-muted" />
          <span className="text-sm font-medium text-po-text">{hospital}</span>
        </div>
      </div>
      <p className="text-4xl font-semibold tabular-nums">{(total ?? 0).toLocaleString()}</p>
      <p className="text-xs text-po-text-muted mt-0.5">documentos detectados</p>
      <div className="flex gap-0.5 mt-4" aria-label={`${SIGLAS.length} categorías`}>
        {SIGLAS.map((s) => (
          <Tooltip key={s} content={`${s}: ${cells?.[s]?.user_override ?? cells?.[s]?.ocr_count ?? cells?.[s]?.filename_count ?? 0}`}>
            <span><Dot variant={dotVariantFor(cells?.[s])} /></span>
          </Tooltip>
        ))}
      </div>
    </button>
  );
}
