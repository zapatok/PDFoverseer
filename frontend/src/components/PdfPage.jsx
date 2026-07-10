import { useEffect, useRef } from "react";

/**
 * Renderiza una página de un PDF a un canvas.
 *
 * @param {object} props
 * @param {object} props.doc - PDFDocumentProxy de usePdfDocument.
 * @param {number} props.pageNumber - número de página, 1-indexado.
 * @param {number} [props.scale] - escala de render (1.5 por defecto).
 * @param {number} [props.rotation] - grados extra sobre el /Rotate propio (§4).
 */
export function PdfPage({ doc, pageNumber, scale = 1.5, rotation = 0 }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    if (!doc) return undefined;
    let cancelled = false;
    let renderTask = null;
    let loadedPage = null;

    doc.getPage(pageNumber).then((page) => {
      if (cancelled) {
        // Desmontado antes de renderizar — libera la página igual.
        page.cleanup();
        return;
      }
      loadedPage = page;
      const canvas = canvasRef.current;
      if (!canvas) return;
      const viewport = page.getViewport({
        scale,
        rotation: ((page.rotate ?? 0) + rotation) % 360,
      });
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      renderTask = page.render({
        canvasContext: canvas.getContext("2d"),
        viewport,
      });
      // Cancelar un render rechaza su promesa con RenderingCancelledException.
      renderTask.promise.catch(() => {});
    });

    return () => {
      cancelled = true;
      if (renderTask) renderTask.cancel();
      // Libera fuentes y bitmaps de la página; pdf.js los retiene hasta
      // doc.destroy() si no se llama cleanup() explícito.
      if (loadedPage) loadedPage.cleanup();
    };
  }, [doc, pageNumber, scale, rotation]);

  return (
    <canvas
      ref={canvasRef}
      className="block max-w-full shadow-sm ring-1 ring-po-border"
    />
  );
}
