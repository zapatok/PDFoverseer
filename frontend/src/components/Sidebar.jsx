export const Sidebar = ({ 
  pdfs, 
  fileProg, 
  metrics, 
  status, 
  selectedPdfFilter, 
  selectedPdfPath, 
  setSelectedPdfFilter, 
  setSelectedPdfPath, 
  handleRemovePdf, 
  handleOpenAnyPdf 
}) => {
  return (
    <div className="w-80 bg-surface/40 backdrop-blur-lg border-r border-white/5 flex flex-col shadow-2xl shrink-0">
      <div className="px-5 py-4 font-bold text-gray-300 uppercase tracking-widest text-xs border-b border-white/5 bg-black/20 flex items-center justify-between">
        <span>PDFs Cargados ({pdfs.length})</span>
        {selectedPdfFilter && (
          <button
            onClick={handleRemovePdf}
            className="bg-transparent border-none p-1.5 rounded-md cursor-pointer flex items-center justify-center outline-none text-error hover:text-red-400 hover:bg-error/10 transition-colors"
            title="Remover PDF seleccionado"
          >
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M5 11h14v2H5z" /></svg>
          </button>
        )}
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {pdfs.map((p, i) => {
          let pct = 0;
          if (status === 'running' && p.name === fileProg.filename && fileProg.total > 0) {
            pct = (fileProg.done / fileProg.total) * 100;
          } else if (p.status === 'done') {
            pct = 100;
          }

          let confColor = 'transparent';
          if (metrics.confidences && metrics.confidences[p.path] !== undefined) {
            const conf = metrics.confidences[p.path];
            if (conf > 0.95) confColor = '#a6e3a1'; // Green fluor
            else if (conf >= 0.90) confColor = '#fab387'; // Orange
            else confColor = '#f38ba8'; // Red
          }

          return (
            <div key={i} title={p.path}
              onClick={() => { const sel = selectedPdfPath === p.path; setSelectedPdfPath(sel ? '' : p.path); setSelectedPdfFilter(sel ? '' : p.name); }}
              onDoubleClick={() => handleOpenAnyPdf(p.path)}
              className={`group px-3 py-2 rounded-md text-sm cursor-pointer transition-all border flex items-center justify-between relative overflow-hidden
              ${selectedPdfFilter === p.name ? 'border-accent shadow-[0_0_10px_rgba(137,180,250,0.5)]' : 'border-transparent hover:bg-white/5'}
              ${status === 'running' && p.name === fileProg.filename && selectedPdfFilter !== p.name ? 'text-accent font-medium' : ''}
              ${p.status === 'done' && selectedPdfFilter !== p.name ? 'text-gray-300' : ''}
              ${p.status === 'error' && selectedPdfFilter !== p.name ? 'text-error line-through' : ''}
              ${p.status === 'skipped' && selectedPdfFilter !== p.name ? 'text-warning italic' : ''}
              ${p.status === 'pending' && (!status || status === 'idle') && selectedPdfFilter !== p.name ? 'text-gray-500' : ''}
            `}
              style={{
                background: pct > 0 ? `linear-gradient(to right, rgba(166,227,161,0.15) ${pct}%, transparent ${pct}%)` : (selectedPdfFilter === p.name ? 'rgba(137,180,250,0.2)' : 'transparent')
              }}>
              <div className="truncate z-10 flex-1">{p.name}</div>

              <div className="flex items-center space-x-2 z-10">
                {/* Confidence Column */}
                {p.status === 'skipped' ? (
                  <span className="text-[10px] font-mono text-blue-400 italic">Skipped</span>
                ) : p.status === 'error' ? (
                  <span className="text-[10px] font-mono text-red-500 font-bold">Aborted</span>
                ) : (
                  confColor !== 'transparent' && (
                    <div className="flex items-center ml-2">
                      <span className="text-[10px] font-mono mr-1.5" style={{ color: confColor }}>
                        {Math.round(metrics.confidences[p.path] * 100)}%
                      </span>
                      <div className="w-1.5 h-4 rounded-full" style={{ backgroundColor: confColor, boxShadow: `0 0 5px ${confColor}` }} title={`Confianza: ${Math.round(metrics.confidences[p.path] * 100)}%`}></div>
                    </div>
                  )
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  );
};
