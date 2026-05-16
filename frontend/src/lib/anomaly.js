// Detector de caída. Devuelve "warn" cuando el último mes cae bajo 0.7x el
// promedio de los 6 meses previos, con baseline efectivo >= 6 puntos. NO marca
// picos hacia arriba — es un detector de caída, no de anomalía genérica.
// Compartido por SparkGrid (tono de celda) y HistoryDrawer (línea + fila).
export function anomalyTone(series) {
  if (!series || series.length < 7) return "neutral";
  const last = series[series.length - 1].count;
  const baseline = series.slice(-7, -1);
  const valid = baseline.filter((p) => p && p.count > 0);
  if (valid.length < 6) return "neutral";
  const mean = valid.reduce((a, b) => a + b.count, 0) / valid.length;
  if (mean === 0) return "neutral";
  return last / mean < 0.7 ? "warn" : "neutral";
}
