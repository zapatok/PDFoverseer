import { useEffect, useRef, useState } from "react";

import { computeFitScale } from "../lib/fit-scale";

const PANEL_PADDING = 32; // p-4 (16px) por lado, para no recortar la página

/**
 * Escala de ajuste-a-ventana (contain) para la página actual.
 * Mide el panel con ResizeObserver y el tamaño natural de la página con pdf.js.
 *
 * @param {object|null} doc - PDFDocumentProxy actual.
 * @param {number} pageNumber - página 1-indexada.
 * @returns {{ panelRef: object, fitScale: number }}
 */
export function useFitScale(doc, pageNumber) {
  const panelRef = useRef(null);
  const [panel, setPanel] = useState({ width: 0, height: 0 });
  const [pageSize, setPageSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const el = panelRef.current;
    if (!el) return undefined;
    const ro = new ResizeObserver((entries) => {
      const r = entries[0]?.contentRect;
      if (r) setPanel({ width: r.width, height: r.height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    if (!doc) return undefined;
    let cancelled = false;
    doc.getPage(pageNumber).then((p) => {
      if (cancelled) {
        p.cleanup();
        return;
      }
      const v = p.getViewport({ scale: 1 });
      setPageSize({ width: v.width, height: v.height });
      p.cleanup();
    });
    return () => {
      cancelled = true;
    };
  }, [doc, pageNumber]);

  const fitScale = computeFitScale(pageSize, {
    width: panel.width - PANEL_PADDING,
    height: panel.height - PANEL_PADDING,
  });
  return { panelRef, fitScale };
}
