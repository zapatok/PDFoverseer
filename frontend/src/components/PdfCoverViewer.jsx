import { X } from "lucide-react";
import { usePdfDocument } from "../hooks/usePdfDocument";
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
 *   open       — boolean, controla la visibilidad del diálogo.
 *   onClose    — función llamada al cerrar.
 *   url        — URL del PDF (api.cellPdfUrl(...)).
 *   pageNumber — número de página a mostrar (1-based).
 *   title      — texto del encabezado del diálogo.
 *   rotation   — grados extra sobre el /Rotate propio (§4), 0 por defecto.
 */
export default function PdfCoverViewer({ open, onClose, url, pageNumber, title, rotation = 0 }) {
  const { doc, error, loading } = usePdfDocument(open ? url : null);

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
