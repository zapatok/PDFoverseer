// Maps backend ScanResult.method tokens → human Spanish labels for UI.
// Token comes verbatim from core.scanners.*; never invent new tokens here.
export const METHOD_LABEL = {
  filename_glob:       "Nombre",
  header_detect:       "Encabezados OCR",
  header_band_anchors: "OCR encabezados",
  corner_count:        "Recuadro de página",
  v4:                  "Paginación OCR",
  page_count_pure:     "Conteo de páginas",
  manual:              "Manual",
};

// ScanResult.confidence → human label.
export const CONFIDENCE_LABEL = {
  high:   "Alta",
  medium: "Media",
  low:    "Baja",
  manual: "Manual",
};
