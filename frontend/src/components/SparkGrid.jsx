import Sparkline from "./Sparkline";
import Tooltip from "../ui/Tooltip";
import { SIGLAS } from "../lib/sigla-labels";
import { anomalyTone } from "../lib/anomaly";

const HOSPITALS = ["HPV", "HRB", "HLU", "HLL"];

function TooltipRows({ series }) {
  if (!series || series.length === 0) return <span>Sin datos</span>;
  return (
    <span className="font-mono">
      {series.map((p, i) => (
        <span key={i} className="block">
          {String(p.month).padStart(2, "0")}/{p.year}: {p.count}
        </span>
      ))}
    </span>
  );
}

export default function SparkGrid({ history }) {
  return (
    <div className="rounded-xl bg-po-panel border border-po-border overflow-hidden">
      {/* Header row */}
      <div className="grid grid-cols-[200px_repeat(4,1fr)] bg-po-panel-hover text-xs font-mono text-po-text-subtle uppercase tracking-wide">
        <div className="px-3 py-2">Sigla</div>
        {HOSPITALS.map((h) => (
          <div key={h} className="px-3 py-2 text-center">
            {h}
          </div>
        ))}
      </div>

      {/* Data rows */}
      {SIGLAS.map((code) => (
        <div
          key={code}
          className="grid grid-cols-[200px_repeat(4,1fr)] border-t border-po-border"
        >
          <div className="px-3 py-2 text-sm text-po-text font-mono">{code}</div>
          {HOSPITALS.map((h) => {
            const series = history?.[`${h}|${code}`] ?? [];
            const tone = anomalyTone(series);
            const last = series.length > 0 ? series[series.length - 1].count : "—";
            return (
              <Tooltip key={h} content={<TooltipRows series={series} />}>
                <div className="px-3 py-2 flex items-center justify-between gap-2 cursor-default hover:bg-po-panel-hover">
                  <Sparkline data={series.map((p) => p.count)} tone={tone} />
                  <span
                    className={`text-sm tabular-nums ${
                      tone === "warn"
                        ? "text-po-suspect font-semibold"
                        : "text-po-text"
                    }`}
                  >
                    {last}
                    {tone === "warn" && " ↓"}
                  </span>
                </div>
              </Tooltip>
            );
          })}
        </div>
      ))}
    </div>
  );
}
