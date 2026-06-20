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
import { participantsInCell } from "../lib/presence";
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
  const session = useSessionStore((s) => s.session);
  const saveOverride = useSessionStore((s) => s.saveOverride);
  const presence = useSessionStore((s) => s.presence);
  const here = participantsInCell(presence, hospital, sigla, getParticipantId());

  const cellKey = `${hospital}|${sigla}`;
  const isScanning = scanningCells.has(cellKey);
  const isPendingSave = pendingSaves[cellKey] === "saving";
  const placeholder = mode === "manual" ? "—" : null;

  const onCommitCount = (v) => {
    saveOverride(session.session_id, hospital, sigla, v, { manual: mode === "manual" });
    if (mode === "manual") onCommitNext?.();
  };

  return (
    <div
      onClick={onSelect}
      className={[
        "flex items-center gap-3 px-3 h-8 cursor-pointer transition",
        "hover:bg-po-panel-hover",
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
          <div className="flex items-center -space-x-1.5">
            {here.map((p) => (
              <PresenceBadge key={p.participant_id} participant={p} size="sm" />
            ))}
          </div>
        )}
        {isScanning ? (
          <Badge variant="state-scanning" icon={Loader2}>Escaneando…</Badge>
        ) : (
          <InlineEditCount
            value={computeCellCount(cell, countTypeFor(sigla))}
            onCommit={onCommitCount}
            placeholder={placeholder}
            autoFocus={autoFocus}
          />
        )}
      </div>
    </div>
  );
}
