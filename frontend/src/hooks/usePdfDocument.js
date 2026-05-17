import { useEffect, useState } from "react";

import { pdfjsLib } from "../lib/pdf";

/**
 * Carga un PDF con pdf.js.
 * @param {string|null} url - URL del PDF, o null/"" para no cargar nada.
 * @returns {{doc: object|null, numPages: number, error: Error|null, loading: boolean}}
 */
export function usePdfDocument(url) {
  const [doc, setDoc] = useState(null);
  const [numPages, setNumPages] = useState(0);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!url) return undefined;
    let cancelled = false;
    setDoc(null);
    setError(null);
    setNumPages(0);

    const task = pdfjsLib.getDocument(url);
    task.promise.then(
      (pdf) => {
        if (cancelled) {
          pdf.destroy();
          return;
        }
        setDoc(pdf);
        setNumPages(pdf.numPages);
      },
      (err) => {
        if (!cancelled) setError(err);
      },
    );

    return () => {
      cancelled = true;
      task.destroy();
    };
  }, [url]);

  return { doc, numPages, error, loading: Boolean(url) && !doc && !error };
}
