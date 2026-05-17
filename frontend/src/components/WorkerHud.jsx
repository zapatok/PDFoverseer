import Badge from "../ui/Badge";
import Button from "../ui/Button";
import SaveIndicator from "../ui/SaveIndicator";

function Metric({ label, value }) {
  return (
    <div className="rounded-lg bg-po-bg p-2 text-center">
      <p className="text-xs text-po-text-muted">{label}</p>
      <p className="text-lg font-semibold tabular-nums text-po-text">{value}</p>
    </div>
  );
}

/**
 * @param {object} props - ver el visor (Task 16) para el origen de cada prop.
 */
export function WorkerHud({
  files, fileIndex, pageInFile, pageCount,
  subtotal, total, marks, currentFilename,
  status, saveStatus, onFinish,
}) {
  const pageMarks = [...(marks[currentFilename] || [])].sort((a, b) => a.page - b.page);

  return (
    <aside className="flex w-72 flex-col gap-4 border-l border-po-border bg-po-panel p-4">
      <div className="grid grid-cols-3 gap-2">
        <Metric label="Archivo" value={`${fileIndex + 1}/${files.length}`} />
        <Metric label="Página" value={`${pageInFile}/${pageCount || "—"}`} />
        <Metric label="Subtotal" value={subtotal} />
      </div>

      <div>
        <p className="text-xs uppercase tracking-wider text-po-text-muted">Total de trabajadores</p>
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
            {pageMarks.map((m) => (
              <li key={m.page} className="flex justify-between py-0.5">
                <span className="text-po-text-muted">Página {m.page}</span>
                <span className="font-mono tabular-nums text-po-text">{m.count}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="flex items-center justify-between gap-2">
        <SaveIndicator status={saveStatus} />
        {status === "terminado" && <Badge variant="jade">Terminado</Badge>}
      </div>
      <Button
        variant={status === "terminado" ? "ghost" : "primary"}
        onClick={onFinish}
      >
        {status === "terminado" ? "Marcar en progreso" : "Terminé esta categoría"}
      </Button>
    </aside>
  );
}
