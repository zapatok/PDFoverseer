import { useEffect } from "react";
import { X, ChevronLeft, ChevronRight } from "lucide-react";
import { usePdfDocument } from "../hooks/usePdfDocument";
import { focusIsInInput } from "../lib/keyboard-focus";
import { PdfPage } from "./PdfPage";
import * as RadixDialog from "@radix-ui/react-dialog";

/**
 * PdfCoverViewer — visor de solo lectura para una página concreta de un PDF.
 *
 * Usado en la sección "Casi-matches" del DetailPanel para mostrar la portada
 * candidata a un nuevo flavor sin necesidad de abrir el visor completo de
 * conteo de trabajadores.
 *
 * Props:
 *   open          — boolean, controla la visibilidad del diálogo.
 *   onClose       — función llamada al cerrar.
 *   url           — URL del PDF (api.cellPdfUrl(...)).
 *   pageNumber    — número de página a mostrar (1-based).
 *   title         — texto del encabezado del diálogo.
 *   rotation      — grados extra sobre el /Rotate propio (§4), 0 por defecto.
 *   onPrev        — opcional, navega al casi-match anterior (null = sin nav).
 *   onNext        — opcional, navega al casi-match siguiente (null = sin nav).
 *   positionLabel — opcional, texto "N de M" junto a los botones de nav.
 */
export default function PdfCoverViewer({
  open,
  onClose,
  url,
  pageNumber,
  title,
  rotation = 0,
  onPrev = null,
  onNext = null,
  positionLabel = null,
}) {
  const { doc, error, loading } = usePdfDocument(open ? url : null);

  // ←/→ step through casi-matches while the viewer is open. Respects the
  // shared focus guard (spec §3 idiom) so it stays inert with focus in an
  // input; disabled entirely when no nav props are given (single-page usage).
  useEffect(() => {
    if (!open || (!onPrev && !onNext)) return undefined;
    const onKey = (e) => {
      if (focusIsInInput()) return;
      if (e.key === "ArrowLeft" && onPrev) { e.preventDefault(); onPrev(); }
      else if (e.key === "ArrowRight" && onNext) { e.preventDefault(); onNext(); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onPrev, onNext]);

  return (
    <RadixDialog.Root open={open} onOpenChange={(v) => !v && onClose()}>
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="fixed inset-0 z-50 bg-black/70" />
        <RadixDialog.Content
          className="fixed inset-4 z-[51] bg-po-bg border border-po-border rounded-xl shadow-2xl flex flex-col focus-visible:outline-none"
          aria-describedby={undefined}
        >
          <RadixDialog.Title asChild>
            <header className="px-5 py-3 border-b border-po-border flex items-center gap-3">
              <span className="flex-1 min-w-0 text-sm font-medium text-po-text truncate">{title}</span>
              {positionLabel && (
                <span className="shrink-0 text-xs tabular-nums text-po-text-muted">{positionLabel}</span>
              )}
              {(onPrev || onNext) && (
                <span className="flex shrink-0 items-center gap-1">
                  <button type="button" disabled={!onPrev} onClick={onPrev ?? undefined} aria-label="Casi-match anterior" className="rounded p-1 text-po-text-muted hover:text-po-text disabled:opacity-40">
                    <ChevronLeft size={16} strokeWidth={1.75} />
                  </button>
                  <button type="button" disabled={!onNext} onClick={onNext ?? undefined} aria-label="Casi-match siguiente" className="rounded p-1 text-po-text-muted hover:text-po-text disabled:opacity-40">
                    <ChevronRight size={16} strokeWidth={1.75} />
                  </button>
                </span>
              )}
              <RadixDialog.Close
                className="text-po-text-muted hover:text-po-text shrink-0"
                aria-label="Cerrar visor"
              >
                <X size={18} strokeWidth={1.75} />
              </RadixDialog.Close>
            </header>
          </RadixDialog.Title>
          <div className="flex-1 min-h-0 overflow-auto flex items-start justify-center p-4">
            {loading && (
              <p className="text-sm text-po-text-muted mt-8">Cargando PDF…</p>
            )}
            {error && (
              <p className="text-sm text-po-error mt-8">
                No se pudo cargar el PDF: {String(error)}
              </p>
            )}
            {doc && (
              <PdfPage doc={doc} pageNumber={pageNumber} scale={1.5} rotation={rotation} />
            )}
          </div>
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  );
}
