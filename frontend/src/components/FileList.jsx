import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useSessionStore } from "../store/session";

export default function FileList({ hospital, sigla }) {
  const { session, openLightbox } = useSessionStore();
  const [files, setFiles] = useState(null);
  const [error, setError] = useState(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    if (!session || !hospital || !sigla) {
      setFiles(null);
      return;
    }
    setError(null);
    let cancelled = false; // ignore stale responses when the user
    // rapidly clicks between cells
    api
      .getCellFiles(session.session_id, hospital, sigla)
      .then((data) => {
        if (!cancelled) setFiles(data);
      })
      .catch((e) => {
        if (!cancelled) setError(String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [session?.session_id, hospital, sigla]);

  if (!hospital || !sigla)
    return <p className="text-slate-500 text-sm">Selecciona una categoría</p>;
  if (error) return <p className="text-red-400 text-sm">{error}</p>;
  if (!files) return <p className="text-slate-500 text-sm">Cargando…</p>;
  if (files.length === 0) return <p className="text-slate-500 text-sm">Sin PDFs</p>;

  const filtered = query
    ? files.filter((f) => f.name.toLowerCase().includes(query.toLowerCase()))
    : files;

  return (
    <div className="space-y-2">
      <input
        type="search"
        placeholder="buscar…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1 text-sm"
      />
      <ul className="space-y-0.5 max-h-[60vh] overflow-y-auto">
        {filtered.map((f) => {
          const actualIndex = files.indexOf(f);
          return (
            <li key={f.name}>
              <button
                onClick={() => openLightbox(hospital, sigla, actualIndex)}
                className="w-full text-left text-xs px-2 py-1 rounded hover:bg-slate-800 font-mono"
              >
                {f.subfolder && <span className="text-slate-500">{f.subfolder}/</span>}
                {f.name}
                <span className="ml-2 text-slate-500">· {f.page_count}pp</span>
                {f.suspect && <span className="ml-1 text-amber-400">⚠</span>}
              </button>
            </li>
          );
        })}
      </ul>
      <p className="text-xs text-slate-500">
        {filtered.length} de {files.length}
      </p>
    </div>
  );
}
