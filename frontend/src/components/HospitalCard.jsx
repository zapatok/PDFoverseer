import { Building2, FolderX } from "lucide-react";
import Dot from "../ui/Dot";
import EmptyState from "../ui/EmptyState";
import Tooltip from "../ui/Tooltip";
import { CTA_LLENAR_MANUAL } from "../lib/constants";
import { SIGLAS } from "../lib/sigla-labels";
import { dotVariantFor } from "../lib/cell-status";
import { useSessionStore } from "../store/session";
import { countTypeFor } from "../lib/sigla-info";

export default function HospitalCard({ hospital, total, cells, status, onClick }) {
  const selectHospital = useSessionStore((s) => s.selectHospital);

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
          description={`${hospital} no entrega PDFs por carpeta este mes. Ingresa los conteos manualmente.`}
          action={
            <button
              type="button"
              onClick={() => selectHospital(hospital, { mode: "manual", focus: "reunion" })}
              className="inline-flex items-center gap-1 text-xs text-po-accent hover:text-po-accent-hover px-2 py-1 rounded hover:bg-po-panel-hover transition"
            >
              {CTA_LLENAR_MANUAL}
            </button>
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
            <span><Dot variant={dotVariantFor(cells?.[s], { countType: countTypeFor(s) })} /></span>
          </Tooltip>
        ))}
      </div>
    </button>
  );
}
