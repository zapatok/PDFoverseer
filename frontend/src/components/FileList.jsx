import { useEffect, useState } from "react";
import { FileText, FileStack, FileX, MousePointer2 } from "lucide-react";
import { useSessionStore } from "../store/session";
import { api } from "../lib/api";
import EmptyState from "../ui/EmptyState";
import Skeleton from "../ui/Skeleton";
import Tooltip from "../ui/Tooltip";
import InlineEditCount from "./InlineEditCount";
import OriginChip from "./OriginChip";

export default function FileList({ hospital, sigla }) {
  const session = useSessionStore((s) => s.session);
  const openLightbox = useSessionStore((s) => s.openLightbox);
  const savePerFileOverride = useSessionStore((s) => s.savePerFileOverride);
  const [files, setFiles] = useState(null);
  const [search, setSearch] = useState("");

  useEffect(() => {
    if (!session?.session_id || !hospital || !sigla) {
      setFiles(null);
      return;
    }
    setFiles(null);
    api.getCellFiles(session.session_id, hospital, sigla)
      .then(setFiles)
      .catch((err) => setFiles({ error: String(err) }));
  }, [session?.session_id, hospital, sigla]);

  if (!sigla) {
    return (
      <EmptyState
        icon={MousePointer2}
        title="Selecciona una categoría"
        description="Elige una sigla para ver los archivos PDF asociados."
      />
    );
  }

  if (files === null) {
    return (
      <div className="space-y-2">
        {[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-10" />)}
      </div>
    );
  }

  if (files?.error) {
    return (
      <EmptyState
        icon={FileX}
        title="No se pudieron cargar los archivos"
        description={files.error}
      />
    );
  }

  if (files.length === 0) {
    return (
      <EmptyState
        icon={FileX}
        title="Sin archivos"
        description="Esta categoría no tiene archivos PDF en este mes."
      />
    );
  }

  const filtered = files.filter((f) =>
    f.name.toLowerCase().includes(search.toLowerCase()),
  );

  return (
    <div className="rounded-xl bg-po-panel border border-po-border overflow-hidden">
      <div className="p-2 border-b border-po-border">
        <input
          placeholder="Buscar archivo…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full bg-transparent text-sm text-po-text placeholder-po-text-subtle focus:outline-none px-2 py-1"
        />
      </div>
      <ul className="max-h-[60vh] overflow-y-auto">
        {filtered.map((f, i) => (
          <li key={`${f.name}-${i}`} className="px-3 py-2 hover:bg-po-panel-hover transition">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => openLightbox(hospital, sigla, files.indexOf(f))}
                className="flex items-center gap-2 flex-1 text-left"
              >
                <FileText size={14} strokeWidth={1.75} className="text-po-text-muted shrink-0" />
                <span className="font-mono text-xs text-po-text truncate flex-1">{f.name}</span>
                <span className="text-xs tabular-nums text-po-text-muted shrink-0">{f.page_count}pp</span>
                {f.suspect && (
                  <Tooltip content="Probable compilación">
                    <span><FileStack size={14} strokeWidth={1.75} className="text-po-suspect shrink-0" /></span>
                  </Tooltip>
                )}
              </button>
              <div className="flex items-center gap-1.5 shrink-0" onClick={(e) => e.stopPropagation()}>
                <InlineEditCount
                  value={f.effective_count ?? 1}
                  onCommit={(newCount) => {
                    setFiles((prev) =>
                      prev.map((row) =>
                        row.name === f.name
                          ? { ...row, effective_count: newCount, override_count: newCount, origin: "manual" }
                          : row,
                      ),
                    );
                    savePerFileOverride(session.session_id, hospital, sigla, f.name, newCount);
                  }}
                />
                <OriginChip origin={f.origin ?? "R1"} />
              </div>
            </div>
          </li>
        ))}
      </ul>
      <div className="px-3 py-2 text-xs text-po-text-muted border-t border-po-border">
        {filtered.length} de {files.length}
      </div>
    </div>
  );
}
