import { useState } from "react";
import { ChevronDown, ChevronRight, Scan } from "lucide-react";
import CategoryRow from "./CategoryRow";
import Button from "../ui/Button";
import { useSessionStore } from "../store/session";

export default function CategoryGroup({
  title,
  cells,
  hospital,
  selected,
  onSelect,
  checkedSet,
  onCheck,
  defaultOpen = true,
  showScanAll = false,
}) {
  const [open, setOpen] = useState(defaultOpen);
  const session = useSessionStore((s) => s.session);
  const scanOcr = useSessionStore((s) => s.scanOcr);

  const scanAll = () => {
    const pairs = cells.map((c) => [hospital, c.sigla]);
    scanOcr(session.session_id, pairs);
  };

  return (
    <div className="border-b border-po-border last:border-b-0 mb-2 last:mb-0">
      <div className="flex items-center justify-between py-2 px-1">
        <button
          onClick={() => setOpen((v) => !v)}
          className="inline-flex items-center gap-2 text-sm font-medium text-po-text hover:text-po-accent"
        >
          {open ? <ChevronDown size={14} strokeWidth={1.75} /> : <ChevronRight size={14} strokeWidth={1.75} />}
          {title}
          <span className="text-po-text-muted font-normal">· {cells.length}</span>
        </button>
        {showScanAll && open && (
          <Button size="sm" icon={Scan} onClick={scanAll} disabled={cells.length === 0}>
            Escanear todas
          </Button>
        )}
      </div>
      {open && (
        <div>
          {cells.map((cell) => (
            <CategoryRow
              key={cell.sigla}
              sigla={cell.sigla}
              cell={cell}
              hospital={hospital}
              selected={selected === cell.sigla}
              onSelect={() => onSelect(cell.sigla)}
              checked={checkedSet.has(cell.sigla)}
              onCheckChange={(c) => onCheck(cell.sigla, c)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
