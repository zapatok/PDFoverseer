import { IMPACT_LABELS } from '../lib/constants';

export const IssueInbox = ({ 
  filteredIssuesList, 
  selectedIssue, 
  setSelectedIssue, 
  showAllIssues, 
  setShowAllIssues,
  cascadeToast,
  metrics,
  pdfs,
  selectedPdfFilter,
  selectedPdfPath,
  fileProg,
  issues
}) => {
  return (
    <div className="flex-1 overflow-y-auto px-12 py-8 custom-scroll">
      <div className="flex items-center justify-between mb-5 border-b border-white/10 pb-5">
        <h1 className="text-4xl font-extrabold text-white tracking-tight drop-shadow-md">Bandeja de Problemas</h1>

        {/* Individual File Metrics Dashboard */}
        <div className="flex space-x-4 bg-black/40 px-4 py-2 text-xs rounded-xl border border-white/5 shadow-inner">
          {(() => {
            const targetName = selectedPdfFilter || fileProg.filename;
            const targetPathForStats = selectedPdfPath || (targetName && pdfs.find(p => p.name === targetName)?.path);
            let ind = { docs: 0, complete: 0, incomplete: 0, inferred: 0 };
            if (targetPathForStats && pdfs.length > 0 && metrics.individual) {
              const targetPdf = pdfs.find(p => p.path === targetPathForStats);
              if (targetPdf && metrics.individual[targetPdf.path]) {
                ind = metrics.individual[targetPdf.path];
              }
            }
            const targetPdfForConf = targetPathForStats && pdfs.length > 0
              ? pdfs.find(p => p.path === targetPathForStats)
              : null;
            return (
              <>
                <div className="flex flex-col items-center justify-center min-w-[30px]">
                  <span className="text-gray-500 font-bold mb-1 tracking-widest text-[9px]">DOC</span>
                  <span className={`${ind.docs > 0 ? 'text-accent' : 'text-gray-600'} font-mono font-bold`}>{ind.docs}</span>
                </div>
                <div className="w-px h-6 bg-white/5 self-center"></div>
                <div className="flex flex-col items-center justify-center min-w-[30px]" title="Documentos con todas las páginas leídas por OCR">
                  <span className="text-gray-500 font-bold mb-1 tracking-widest text-[9px]">DIR</span>
                  <span className={`${(ind.direct || 0) > 0 ? 'text-success' : 'text-gray-600'} font-mono font-bold`}>{ind.direct || 0}</span>
                </div>
                <div className="w-px h-6 bg-white/5 self-center"></div>
                <div className="flex flex-col items-center justify-center min-w-[30px]" title="Cantidad de páginas inferidas en este documento">
                  <span className="text-gray-500 font-bold mb-1 tracking-widest text-[9px]">INF</span>
                  <span className={`${(ind.inferred || 0) > 0 ? 'text-warning' : 'text-gray-600'} font-mono font-bold`}>{ind.inferred || 0}</span>
                </div>
                <div className="w-px h-6 bg-white/5 self-center"></div>
                <div className="flex flex-col items-center justify-center min-w-[30px]" title="Documentos incompletos">
                  <span className="text-gray-500 font-bold mb-1 tracking-widest text-[9px]">INC</span>
                  <span className={`${(ind.incomplete || 0) > 0 ? 'text-error' : 'text-gray-600'} font-mono font-bold`}>{ind.incomplete || 0}</span>
                </div>
                {(() => {
                  const conf = metrics?.confidences && targetPdfForConf
                    ? metrics.confidences[targetPdfForConf.path]
                    : (ind.docs > 0 ? ((ind.direct || 0) / ind.docs) : null);
                  if (conf === null || conf === undefined) return null;
                  const pct = Math.round(conf * 100);
                  const color = pct >= 90 ? 'text-success' : pct >= 70 ? 'text-warning' : 'text-error';
                  return (
                    <>
                      <div className="w-px h-6 bg-white/5 self-center"></div>
                      <div className="flex flex-col items-center justify-center min-w-[40px]" title="Porcentaje de documentos con todas las páginas verificadas por OCR">
                        <span className="text-gray-500 font-bold mb-1 tracking-widest text-[9px]">VER</span>
                        <span className={`${color} font-mono font-bold`}>{pct}%</span>
                      </div>
                    </>
                  );
                })()}
              </>
            );
          })()}
        </div>
      </div>

      {cascadeToast && (
        <div className="bg-accent/10 border border-accent/30 text-accent text-sm px-4 py-2 rounded-lg mb-3 animate-pulse">
          {cascadeToast}
        </div>
      )}

      {(() => {
        const filteredIssues = filteredIssuesList;
        const totalCount = (selectedPdfPath
          ? issues.filter(i => i.pdf_path === selectedPdfPath)
          : issues).length;

        return (
          <>
            {totalCount > 0 && (
              <div className="flex items-center justify-between mb-3">
                <span className="text-gray-500 text-xs">
                  {filteredIssues.length} de {totalCount} issues
                </span>
                <button
                  onClick={() => setShowAllIssues(v => !v)}
                  className={`text-[10px] font-bold tracking-wider px-2 py-0.5 rounded transition-all cursor-pointer ${
                    showAllIssues ? 'bg-gray-600 text-white' : 'bg-transparent text-gray-500 hover:text-gray-300'
                  }`}
                >
                  {showAllIssues ? 'TODOS' : 'CRÍTICOS'}
                </button>
              </div>
            )}

            {filteredIssues.length === 0 && (
              <div className="flex items-center justify-center h-48 border-2 border-dashed border-[#313244] rounded-2xl text-gray-500">
                {totalCount === 0 ? 'Aún no hay problemas por revisar' : 'No hay issues críticos — pulsa TODOS para ver internos'}
              </div>
            )}

            <div className="grid gap-3">
              {filteredIssues.map(iss => {
                const imp = IMPACT_LABELS[iss.impact] || IMPACT_LABELS.internal;
                return (
                  <div key={iss.id}
                    onClick={() => setSelectedIssue(iss)}
                    className={`bg-surface rounded-xl p-4 border flex items-center shadow-sm transition-all cursor-pointer group
                    ${selectedIssue?.id === iss.id ? 'border-accent ring-1 ring-accent scale-[1.01]' : 'border-[#313244] hover:border-warning/50'}`}>
                    <div className="bg-warning/10 text-warning px-3 py-1.5 rounded-lg font-mono text-xl w-16 text-center shadow-inner">
                      {iss.page}
                    </div>
                    <div className="ml-4 flex-1">
                      <div className="flex items-center">
                        <h3 className="font-semibold text-gray-100 truncate">{iss.filename}</h3>
                        <span className={`${imp.color} px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ml-2`}>
                          {imp.label}
                        </span>
                      </div>
                      <p className="text-gray-400 text-sm mt-0.5">{iss.type} — {iss.detail}</p>
                    </div>
                    <div className={`transition-opacity ${selectedIssue?.id === iss.id ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}`}>
                      <button className="bg-accent/20 text-accent hover:bg-accent hover:text-base px-4 py-2 rounded-lg font-medium transition-colors cursor-pointer text-sm">
                        Revisar ➔
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        );
      })()}
    </div>
  );
};
