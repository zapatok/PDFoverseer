import { useRef } from "react";
import Drawer from "../ui/Drawer";
import OriginChip from "./OriginChip";
import { SIGLA_LABELS } from "../lib/sigla-labels";
import { anomalyTone } from "../lib/anomaly";

// Método de historical_counts → variante de OriginChip.
function methodToOrigin(method) {
  if (method === "manual") return "manual";
  if (method === "filename_glob") return "R1";
  return "OCR"; // header_detect / corner_count / page_count_pure
}

const MES = (p) => `${String(p.month).padStart(2, "0")}/${p.year}`;

// Gráfico de línea inline — 12 puntos, último resaltado.
function SeriesChart({ counts, tone }) {
  const W = 380;
  const H = 110;
  const PAD = 12;
  if (counts.length === 0) return null;
  const max = Math.max(...counts, 1);
  const min = Math.min(...counts);
  const range = Math.max(max - min, 1);
  const xFor = (i) =>
    PAD + (i / Math.max(counts.length - 1, 1)) * (W - 2 * PAD);
  const yFor = (c) => PAD + (1 - (c - min) / range) * (H - 2 * PAD);
  const points = counts.map((c, i) => `${xFor(i).toFixed(1)},${yFor(c).toFixed(1)}`).join(" ");
  const stroke = tone === "warn" ? "stroke-po-suspect" : "stroke-po-accent";
  const fill = tone === "warn" ? "fill-po-suspect" : "fill-po-accent";
  const lastIdx = counts.length - 1;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} className="block">
      <polyline fill="none" strokeWidth={2} className={stroke} points={points} />
      <circle cx={xFor(lastIdx)} cy={yFor(counts[lastIdx])} r={3.5} className={fill} />
    </svg>
  );
}

/**
 * Drill-in read-only de una serie histórica (hospital x sigla).
 *
 * Props:
 *   open      — bool
 *   hospital  — string | null
 *   sigla     — string | null
 *   series    — [{year, month, count, confidence, method}] | undefined
 *               (orden viejo → nuevo, como lo devuelve /history)
 *   onClose   — () => void
 */
export default function HistoryDrawer({ open, hospital, sigla, series, onClose }) {
  // Al cerrar, MonthOverview pasa hospital/sigla/series en null. Sin esto, el
  // panel mostraría el estado vacío durante los 200 ms de la animación de
  // salida: congelamos el último contenido real y lo seguimos mostrando
  // mientras el drawer se desliza fuera de pantalla.
  const shown = useRef({ hospital, sigla, series });
  if (hospital != null) {
    shown.current = { hospital, sigla, series };
  }
  const view = shown.current;

  const points = view.series ?? [];
  const counts = points.map((p) => p.count);
  const tone = anomalyTone(points);

  const title = (
    <div>
      <div className="text-sm font-semibold text-po-text">
        {view.hospital} · {view.sigla}
      </div>
      {view.sigla && (
        <div className="text-xs text-po-text-muted truncate">
          {SIGLA_LABELS[view.sigla] ?? view.sigla}
        </div>
      )}
    </div>
  );

  const hasData = counts.length > 0;
  const last = hasData ? counts[counts.length - 1] : 0;
  const avg = hasData ? Math.round(counts.reduce((a, b) => a + b, 0) / counts.length) : 0;
  const lo = hasData ? Math.min(...counts) : 0;
  const hi = hasData ? Math.max(...counts) : 0;
  // Fila anómala: solo si la serie entera es "warn", el último mes la marca.
  const anomalyKey = tone === "warn" && hasData ? MES(points[points.length - 1]) : null;

  return (
    <Drawer open={open} onClose={onClose} title={title}>
      {!hasData ? (
        <div className="p-6 text-sm text-po-text-muted">
          Sin datos históricos para esta serie.
        </div>
      ) : (
        <div className="p-4 space-y-4">
          {/* Stats strip */}
          <div className="flex gap-4">
            <Stat value={last} label="Último" />
            <Stat value={avg} label="Promedio 12m" />
            <Stat value={`${lo}–${hi}`} label="Rango" />
          </div>

          {/* Gráfico */}
          <div className="rounded-lg bg-po-bg border border-po-border p-2">
            <SeriesChart counts={counts} tone={tone} />
          </div>

          {/* Tabla mes-a-mes (más reciente arriba) */}
          <div className="text-sm">
            <div className="grid grid-cols-[1fr_auto_64px] gap-2 px-1 pb-1.5 text-[10px] uppercase tracking-wide text-po-text-subtle">
              <span>Mes</span>
              <span className="text-right">Conteo</span>
              <span className="text-center">Método</span>
            </div>
            {[...points].reverse().map((p) => {
              const isAnomaly = MES(p) === anomalyKey;
              return (
                <div
                  key={`${p.year}-${p.month}`}
                  className={[
                    "grid grid-cols-[1fr_auto_64px] gap-2 px-1 py-1.5 items-center border-t border-po-border",
                    isAnomaly ? "bg-po-suspect-bg rounded" : "",
                  ].join(" ")}
                >
                  <span className="text-po-text-muted tabular-nums">{MES(p)}</span>
                  <span
                    className={[
                      "text-right tabular-nums",
                      isAnomaly ? "text-po-suspect font-semibold" : "text-po-text",
                    ].join(" ")}
                  >
                    {p.count}
                  </span>
                  <div className="flex justify-center">
                    <OriginChip origin={methodToOrigin(p.method)} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </Drawer>
  );
}

function Stat({ value, label }) {
  return (
    <div className="flex-1">
      <div className="text-xl font-semibold text-po-text tabular-nums">{value}</div>
      <div className="text-[10px] uppercase tracking-wide text-po-text-subtle mt-0.5">
        {label}
      </div>
    </div>
  );
}
