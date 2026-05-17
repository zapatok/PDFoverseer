// Configuración única de pdf.js. Importar `pdfjsLib` SIEMPRE desde aquí,
// nunca desde "pdfjs-dist" directo — así el workerSrc queda garantizado.
import * as pdfjsLib from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;

export { pdfjsLib };
