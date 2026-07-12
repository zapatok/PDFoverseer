import { Loader2 } from "lucide-react";
import { useSessionStore } from "../store/session";
import Badge from "../ui/Badge";
import Dot from "../ui/Dot";
import Tooltip from "../ui/Tooltip";
import { SIGLA_LABELS, siglaDisplay } from "../lib/sigla-labels";
import { dotVariantFor } from "../lib/cell-status";
import { computeCellCount } from "../lib/cellCount";
import { countTypeFor } from "../lib/sigla-info";
import InlineEditCount from "./InlineEditCount";
import { participantsInCell, cellLockHolder } from "../lib/presence";
import { getParticipantId } from "../lib/identity";
import PresenceBadge from "./PresenceBadge";


export default function CategoryRow({
  sigla,
  cell,
  hospital,
  selected,
  onSelect,
  checked,
  onCheckChange,
  mode = "scanned",
  autoFocus = false,
  onCommitNext,
}) {
  const scanningCells = useSessionStore((s) => s.scanningCells);
  const pendingSaves = useSessionStore((s) => s.pendingSaves);
  // A6: per-field selector — this component only ever reads session_id, so a
  // whole-session subscription re-rendered every row on any cell_updated.
  const sessionId = useSessionStore((s) => s.session?.session_id);
  const saveOverride = useSessionStore((s) => s.saveOverride);
  const presence = useSessionStore((s) => s.presence);
  const here = participantsInCell(presence, hospital, sigla, getParticipantId());
  // M3a: non-null when another participant is editing this cell.
  const lockHolder = cellLockHolder(presence, hospital, sigla, getParticipantId());

  const cellKey = `${hospital}|${sigla}`;
  const isScanning = scanningCells.has(cellKey);
  const isPendingSave = pendingSaves[cellKey] === "saving";
  const placeholder = mode === "manual" ? "—" : null;

  const onCommitCount = (v, opts) => {
    saveOverride(sessionId, hospital, sigla, v, {
      manual: mode === "manual",
      allowOverPages: opts?.allowOverPages,
    });
    if (mode === "manual") onCommitNext?.();
  };

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(e) => {
        // §A7: only the row itself responds to Enter/Space — a nested control
        // (checkbox, the count editor's button) already has its own native
        // keyboard behavior, and this event still bubbles up to us; without
        // this guard, Space-toggling the checkbox would ALSO select the row.
        // No roving ↑/↓ between rows (YAGNI — Tab already reaches every row).
        if (e.target !== e.currentTarget) return;
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect();
        }
      }}
      className={[
        "flex items-center gap-3 px-3 h-8 cursor-pointer transition outline-none",
        "hover:bg-po-panel-hover",
        "focus-visible:ring-1 focus-visible:ring-po-accent focus-visible:ring-inset",
        selected && "bg-po-panel-hover border-l-2 border-po-accent",
      ].filter(Boolean).join(" ")}
    >
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onCheckChange(e.target.checked)}
        onClick={(e) => e.stopPropagation()}
        className="accent-po-accent"
      />
      <Tooltip content={SIGLA_LABELS[sigla] ?? null}>
        <span className="font-mono text-xs text-po-text">{siglaDisplay(sigla)}</span>
      </Tooltip>
      <Dot variant={dotVariantFor(cell, { isScanning, countType: countTypeFor(sigla) })} className={isPendingSave ? "animate-pulse" : ""} />

      {/* Trailing slot: presence badges (others focused here) + count/scan state.
          Status (error/manual/compilación) lives in the Detalle column.
          "Escaneando…" stays — it is transient live feedback, not a status. */}
      <div className="ml-auto flex items-center gap-2">
        {here.length > 0 && (
          // When lockHolder is set, wrap with a tooltip so the operator can see
          // "Editando" affordance without adding a separate lock icon.
          <Tooltip content={lockHolder ? `${lockHolder.name} está editando` : undefined}>
            <div className={["flex items-center -space-x-1.5", lockHolder ? "ring-1 ring-po-suspect-border rounded-full" : ""].filter(Boolean).join(" ")}>
              {here.map((p) => (
                <PresenceBadge key={p.participant_id} participant={p} size="sm" />
              ))}
            </div>
          </Tooltip>
        )}
        {isScanning ? (
          <Badge variant="state-scanning" icon={Loader2}>Escaneando…</Badge>
        ) : (
          <InlineEditCount
            value={computeCellCount(cell, countTypeFor(sigla))}
            onCommit={onCommitCount}
            placeholder={placeholder}
            autoFocus={autoFocus}
            disabled={!!lockHolder}
          />
        )}
      </div>
    </div>
  );
}
