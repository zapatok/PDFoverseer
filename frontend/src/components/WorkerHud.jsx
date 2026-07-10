import { useEffect, useRef, useState } from "react";
import { Mic, MicOff } from "lucide-react";

import Badge from "../ui/Badge";
import Button from "../ui/Button";
import Disclosure from "../ui/Disclosure";
import SaveIndicator from "../ui/SaveIndicator";
import { WORKER_SHORTCUTS } from "../lib/worker-shortcuts";
import { evaluate } from "../lib/calc";

function Metric({ label, value }) {
  return (
    <div className="rounded-lg bg-po-bg p-2 text-center">
      <p className="text-xs text-po-text-muted">{label}</p>
      <p className="text-lg font-semibold tabular-nums text-po-text">{value}</p>
    </div>
  );
}

// El chip de micrófono reusa el primitive Badge — misma forma que el resto de
// chips, varía color y texto (feedback_chip_consistency). "Voz no disponible"
// es además el aviso permanente del spec §10 cuando el navegador no soporta el
// Web Speech API: estado visible, no bloquea el conteo por teclado.
const MIC_CHIP = {
  listening: { variant: "jade", icon: Mic, label: "Escuchando" },
  paused: { variant: "amber", icon: MicOff, label: "Voz en pausa" },
  error: { variant: "neutral", icon: MicOff, label: "Voz con error" },
  unsupported: { variant: "neutral", icon: MicOff, label: "Voz no disponible" },
};

function MicChip({ status }) {
  const c = MIC_CHIP[status] ?? MIC_CHIP.unsupported;
  return <Badge variant={c.variant} icon={c.icon}>{c.label}</Badge>;
}

// Collapsible keyboard calculator (triage I8) — a scratch pad for quick sums
// while counting (e.g. "3*24+7" workers across shifts). Focus isolation: the
// viewer's key handler already guards shortcuts with focusIsInInput() (see
// WorkerCountViewer.jsx §3), so digits typed here never leak into the
// pending-count buffer — no extra wiring needed.
function CalcBar() {
  const [expr, setExpr] = useState("");
  const result = evaluate(expr);
  return (
    <div className="space-y-1">
      <input
        value={expr}
        onChange={(e) => setExpr(e.target.value)}
        placeholder="p. ej. 3*24+7"
        aria-label="Calculadora"
        className="w-full rounded border border-po-border bg-po-panel px-2 py-1 text-xs font-mono text-po-text placeholder-po-text-subtle focus:outline-none focus:ring-1 focus:ring-po-accent"
      />
      <p className="text-right font-mono text-sm tabular-nums text-po-text">
        {result != null ? `= ${result}` : expr ? "…" : ""}
      </p>
    </div>
  );
}

/**
 * @param {object} props - ver el visor (Task 16) para el origen de cada prop.
 * @param {string} [props.unit] - "trabajadores" | "chequeos" (derivado del count_type).
 * @param {boolean} [props.showMic] - si false, oculta el chip de micrófono (checks).
 */
export function WorkerHud({
  files, fileIndex, pageInFile, pageCount,
  subtotal, total, marks, currentFilename,
  status, saveStatus, micStatus, onFinish,
  unit = "trabajadores", showMic = true,
}) {
  const pageMarks = [...(marks[currentFilename] || [])].sort((a, b) => a.page - b.page);

  const currentRowRef = useRef(null);
  useEffect(() => {
    currentRowRef.current?.scrollIntoView({ block: "nearest" });
  }, [pageInFile]);

  return (
    <aside className="flex w-72 flex-col gap-4 border-l border-po-border bg-po-panel p-4">
      <div className="grid grid-cols-3 gap-2">
        <Metric label="Archivo" value={`${fileIndex + 1}/${files.length}`} />
        <Metric label="Página" value={`${pageInFile}/${pageCount || "—"}`} />
        <Metric label="Subtotal" value={subtotal} />
      </div>

      <div>
        <p className="text-xs uppercase tracking-wider text-po-text-muted">Total de {unit}</p>
        <p className="text-4xl font-semibold tabular-nums text-po-text">{total}</p>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <p className="mb-1 text-xs uppercase tracking-wider text-po-text-muted">
          Marcas · {currentFilename}
        </p>
        {pageMarks.length === 0 ? (
          <p className="text-sm text-po-text-subtle">Sin marcas en este archivo.</p>
        ) : (
          <ul className="text-sm">
            {pageMarks.map((m) => {
              const isCurrent = m.page === pageInFile;
              return (
                <li
                  key={m.page}
                  ref={isCurrent ? currentRowRef : null}
                  className={`flex justify-between py-0.5 px-1 rounded ${
                    isCurrent ? "bg-po-panel-hover border-l-2 border-po-accent" : ""
                  }`}
                >
                  <span className={isCurrent ? "font-medium text-po-text" : "text-po-text-muted"}>
                    Página {m.page}
                  </span>
                  <span className="font-mono tabular-nums text-po-text">{m.count}</span>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {showMic && <MicChip status={micStatus} />}
        <SaveIndicator status={saveStatus} />
        {status === "terminado" && <Badge variant="jade">Terminado</Badge>}
      </div>
      <Button
        variant={status === "terminado" ? "ghost" : "primary"}
        onClick={onFinish}
      >
        {status === "terminado" ? "Marcar en progreso" : "Terminé esta categoría"}
      </Button>

      <div className="shrink-0 border-t border-po-border pt-3">
        <p className="mb-1.5 text-xs uppercase tracking-wider text-po-text-muted">Atajos</p>
        <ul className="flex flex-col gap-1">
          {WORKER_SHORTCUTS.filter((s) => showMic || s.action !== "Voz on / off").map((s) => (
            <li key={s.action} className="flex items-center justify-between gap-2 text-xs">
              <span className="flex shrink-0 gap-1">
                {s.keys.map((k) => (
                  <Badge key={k} variant="neutral" className="font-mono">{k}</Badge>
                ))}
              </span>
              <span className="text-right text-po-text-subtle">{s.action}</span>
            </li>
          ))}
        </ul>
      </div>

      <Disclosure summary="Calculadora">
        <CalcBar />
      </Disclosure>
    </aside>
  );
}
