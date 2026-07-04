import { AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import Badge from "../ui/Badge";
import Button from "../ui/Button";
import { useSessionStore } from "../store/session";
import { SIGLA_LABELS } from "../lib/sigla-labels";

/**
 * PosiblesColadosPanel — misfiled-document ("colado") suspects for a cell
 * (anti-colados V1). Two kinds:
 *   - "filename": a whole file whose NAME suggests another sigla → move_file.
 *   - "code":     a page-run inside a compilation carrying another sigla's form
 *                 code → extract_pages (V2; the panel renders it identically).
 *
 * Detection never changes a count; this panel is the surface. Each row offers
 * "Crear op de reorg" (prefills the existing Incr-J op — its delta corrects the
 * count and the manifest tells paso-1 to move the file physically) and
 * "Descartar" (the operator judged it legitimate; lasts until the next scan).
 *
 * ``cell.colado_suspects`` arrives ALREADY open-filtered by the backend (§5
 * dedupe), so a suspect covered by a pending op is not shown here. Renders
 * ``null`` when there are none. Respects the M3 cell lock via ``locked``.
 *
 * Props:
 *   hospital  {string}
 *   sigla     {string}
 *   cell      {object}
 *   sessionId {string}
 *   locked    {boolean}
 */
export default function PosiblesColadosPanel({ hospital, sigla, cell, sessionId, locked = false }) {
  const addReorgOp = useSessionStore((s) => s.addReorgOp);
  const dismissColadoSuspect = useSessionStore((s) => s.dismissColadoSuspect);

  const suspects = cell?.colado_suspects ?? [];
  if (suspects.length === 0) return null;

  async function handleCreate(s) {
    // Prefill the existing Incr-J op. doc_count: omit when counted (backend
    // resolve_op_defaults = the file's real contribution for move_file, 1 for
    // extract_pages); explicit 0 when NOT counted — an intentional divergence
    // from the default (the file added nothing to the host, so nothing moves).
    const draft = {
      op_type: s.page_range ? "extract_pages" : "move_file",
      source: { file: s.file, page_range: s.page_range ?? null },
      dest: { hospital, sigla: s.suggested_sigla },
    };
    if (!s.counted) draft.doc_count = 0;
    try {
      await addReorgOp(sessionId, hospital, sigla, draft);
      toast.success("Operación de reorganización creada");
    } catch {
      /* addReorgOp already toasted the failure */
    }
  }

  return (
    <div className="mt-6">
      <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-po-text-muted">
        Posibles colados
      </div>
      <div className="rounded-lg border border-po-suspect-border bg-po-suspect-bg px-3 py-2.5 text-xs text-po-suspect">
        <div className="mb-2 flex items-center gap-2">
          <AlertTriangle size={14} strokeWidth={1.75} className="shrink-0" />
          <span>
            {suspects.length} archivo(s) podrían estar mal clasificados en esta categoría.
          </span>
        </div>
        <ul className="space-y-2">
          {suspects.map((s) => {
            const ranged = Boolean(s.page_range);
            const destLabel = s.suggested_sigla
              ? SIGLA_LABELS[s.suggested_sigla] ?? s.suggested_sigla
              : null;
            return (
              <li key={s.id} className="flex flex-wrap items-center gap-2">
                <Badge variant="amber">
                  {ranged ? `Páginas ${s.page_range[0]}–${s.page_range[1]}` : "Archivo"}
                </Badge>
                <span className="min-w-0 flex-1 truncate font-mono text-po-text" title={s.file}>
                  {s.file}
                </span>
                <span className="text-po-text-muted">
                  {s.kind === "code" ? "código" : "token"}: {s.evidence}
                </span>
                <span className="text-po-text">
                  {destLabel ? `→ ${destLabel}` : "→ elige el destino"}
                </span>
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={locked || !s.suggested_sigla}
                  title={!s.suggested_sigla ? "Varios destinos posibles — créala manualmente" : undefined}
                  onClick={() => handleCreate(s)}
                >
                  Crear op de reorg
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  disabled={locked}
                  onClick={() => dismissColadoSuspect(sessionId, hospital, sigla, s.id)}
                >
                  Descartar
                </Button>
              </li>
            );
          })}
        </ul>
        <p className="mt-2 text-[11px] text-po-text-muted">
          Se recalculan en cada escaneo; descartar dura hasta el próximo escaneo de la celda.
        </p>
      </div>
    </div>
  );
}
