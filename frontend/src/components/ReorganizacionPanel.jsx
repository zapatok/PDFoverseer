import { ArrowRight, ArrowLeft, Trash2 } from "lucide-react";
import Badge from "../ui/Badge";

// op_type → chip variant + label (same Badge primitive, vary color/text).
// Keys are the four canonical backend op_types (api/reorg.py OP_TYPES) — never a
// UI label like "reclasificar" (that's just a move_file to another sigla).
const OP_TYPE_VARIANT = {
  move_file:      "iris",
  extract_pages:  "iris",
  split_in_place: "blue",
  rotate:         "blue",
};

const OP_TYPE_LABEL = {
  move_file:      "Mover",
  extract_pages:  "Extraer",
  split_in_place: "Dividir",
  rotate:         "Rotar",
};

/** Pure helpers — also used by ReorganizacionPanel.test.js */

/** Ops where this (hospital, sigla) is the source. */
export function outgoingOps(ops, hospital, sigla) {
  return ops.filter(
    (op) => op.source?.hospital === hospital && op.source?.sigla === sigla,
  );
}

/** Ops where this (hospital, sigla) is the destination. */
export function incomingOps(ops, hospital, sigla) {
  return ops.filter(
    (op) => op.dest?.hospital === hospital && op.dest?.sigla === sigla,
  );
}

/**
 * Net document delta for this cell from pending ops only:
 *   Σ incoming.doc_count − Σ outgoing.doc_count
 */
export function netDocDelta(ops, hospital, sigla) {
  const pending = ops.filter((op) => op.status === "pending");
  const inc = incomingOps(pending, hospital, sigla).reduce(
    (sum, op) => sum + (op.doc_count ?? 0), 0,
  );
  const out = outgoingOps(pending, hospital, sigla).reduce(
    (sum, op) => sum + (op.doc_count ?? 0), 0,
  );
  return inc - out;
}

/** True if there is at least one pending op involving this cell. */
export function hasPendingOps(ops, hospital, sigla) {
  return ops.some(
    (op) =>
      op.status === "pending" &&
      ((op.source?.hospital === hospital && op.source?.sigla === sigla) ||
        (op.dest?.hospital === hospital && op.dest?.sigla === sigla)),
  );
}

/** Count of pending ops touching a cell as source or dest (Disclosure badge). */
export function pendingOpsCountForCell(ops, hospital, sigla) {
  return (ops || []).filter(
    (op) =>
      op.status === "pending" &&
      ((op.source?.hospital === hospital && op.source?.sigla === sigla) ||
        (op.dest?.hospital === hospital && op.dest?.sigla === sigla)),
  ).length;
}

function formatDelta(n) {
  if (n > 0) return `+${n}`;
  if (n < 0) return `${n}`;
  return "±0";
}

/** Also used by MonthReorgPanel (Task 18) — one row renderer, not duplicated. */
export function OpRow({ op, isOutgoing, onDelete, locked = false }) {
  const muted = op.status === "applied";
  const otherHospital = isOutgoing ? op.dest?.hospital : op.source?.hospital;
  const otherSigla   = isOutgoing ? op.dest?.sigla    : op.source?.sigla;
  const otherLabel   = `${otherHospital ?? "?"}/${otherSigla ?? "?"}`;

  const countLabel = op.doc_count != null
    ? (isOutgoing ? `−${op.doc_count}` : `+${op.doc_count}`)
    : "";

  const variant = OP_TYPE_VARIANT[op.op_type] ?? "neutral";
  const typeLabel = OP_TYPE_LABEL[op.op_type] ?? op.op_type ?? "Op";

  return (
    <li
      className={[
        "flex items-center gap-2 py-1.5 text-xs",
        muted ? "text-po-text-muted" : "text-po-text",
      ].join(" ")}
    >
      <Badge variant={muted ? "neutral" : variant}>{typeLabel}</Badge>
      <span className="font-mono truncate flex-1 min-w-0 text-po-text-muted">
        {op.source?.file ?? "—"}
      </span>
      <span className="shrink-0 tabular-nums font-medium">
        {countLabel}
      </span>
      {isOutgoing ? (
        <ArrowRight size={12} strokeWidth={1.75} className="shrink-0 text-po-text-muted" />
      ) : (
        <ArrowLeft size={12} strokeWidth={1.75} className="shrink-0 text-po-text-muted" />
      )}
      <span className="font-mono shrink-0 text-po-text-muted">{otherLabel}</span>
      {!muted && (
        <button
          type="button"
          aria-label="Eliminar operación"
          disabled={locked}
          onClick={locked ? undefined : () => onDelete(op.id)}
          className={[
            "ml-auto shrink-0 transition",
            locked
              ? "text-po-text-muted cursor-not-allowed opacity-50"
              : "text-po-text-muted hover:text-po-error",
          ].join(" ")}
          data-testid="eliminar-btn"
        >
          <Trash2 size={13} strokeWidth={1.75} />
        </button>
      )}
    </li>
  );
}

/**
 * REORGANIZACIÓN section for the DetailPanel.
 *
 * Props:
 *   hospital  {string}   — current cell's hospital
 *   sigla     {string}   — current cell's sigla
 *   ops       {object[]} — full session reorg_ops array (all hospitals)
 *   onDelete  {fn(opId)} — called when the operator removes a pending op
 *   locked    {boolean}  — another participant holds this cell (F3): disable the
 *                          per-op delete buttons.
 *
 * Export lives ONLY in MonthReorgPanel now (Task 18) — it's session-wide (the
 * endpoint writes ALL pending ops), so a per-cell export button was
 * misleading ("quiero que exista en un solo lugar donde exporte todos los
 * cambios", Daniel 2026-07-08).
 */
export default function ReorganizacionPanel({
  hospital,
  sigla,
  ops = [],
  onDelete,
  locked = false,
}) {
  const outgoing = outgoingOps(ops, hospital, sigla);
  const incoming = incomingOps(ops, hospital, sigla);

  const all = [...outgoing, ...incoming];
  const delta = netDocDelta(ops, hospital, sigla);

  return (
    <div className="space-y-2">
      {all.length === 0 ? (
        <p className="text-xs text-po-text-muted">Sin operaciones</p>
      ) : (
        <>
          <div className="flex items-center gap-2 text-xs text-po-text-muted">
            <span>Delta neto:</span>
            <span
              className={[
                "font-semibold tabular-nums",
                delta > 0 ? "text-po-confidence-high" : delta < 0 ? "text-po-error" : "text-po-text-muted",
              ].join(" ")}
              data-testid="net-delta"
            >
              {formatDelta(delta)}
            </span>
          </div>
          <ul className="divide-y divide-po-border">
            {outgoing.map((op) => (
              <OpRow key={op.id} op={op} isOutgoing={true} onDelete={onDelete} locked={locked} />
            ))}
            {incoming.map((op) => (
              <OpRow key={op.id} op={op} isOutgoing={false} onDelete={onDelete} locked={locked} />
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
