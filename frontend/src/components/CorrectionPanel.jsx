import { TransformWrapper, TransformComponent } from 'react-zoom-pan-pinch';
import { API_BASE } from '../lib/constants';

export const CorrectionPanel = ({
  selectedIssue,
  setSelectedIssue,
  correctCurr,
  setCorrectCurr,
  correctTot,
  setCorrectTot,
  handleExclude,
  handleCorrect,
  handleOpenNativePdf,
  navigateIssue
}) => {
  if (!selectedIssue) return null;

  return (
    <div className="w-[45%] bg-panel/90 backdrop-blur-2xl border-l border-white/10 flex flex-col shadow-2xl z-40 shrink-0 transition-all duration-300">
      <div className="p-4 border-b border-[#313244] flex items-center justify-between bg-surface/50">
        <div>
          <h2 className="text-lg font-bold">Corrección Manual</h2>
          <p className="text-xs text-gray-400 truncate max-w-xs">{selectedIssue.filename} - Pág {selectedIssue.page}</p>
        </div>
        <div className="flex space-x-1 items-center">
          <button onClick={handleOpenNativePdf} className="bg-transparent border-none outline-none focus:outline-none text-gray-400 hover:text-accent disabled:opacity-30 transition-colors flex items-center justify-center p-2 mr-2" title="Abrir en Visor Nativo">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" /></svg>
          </button>
          <button onClick={() => navigateIssue(-1)} className="bg-transparent border-none outline-none focus:outline-none text-gray-500 hover:text-white transition-colors flex items-center justify-center p-2" title="Problema Anterior">
            <svg className="w-5 h-5" stroke="currentColor" fill="none" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 19l-7-7 7-7" /></svg>
          </button>
          <button onClick={() => navigateIssue(1)} className="bg-transparent border-none outline-none focus:outline-none text-gray-500 hover:text-white transition-colors flex items-center justify-center p-2" title="Problema Siguiente">
            <svg className="w-5 h-5" stroke="currentColor" fill="none" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5l7 7-7 7" /></svg>
          </button>
          <div className="w-px h-5 bg-white/10 mx-1"></div>
          <button onClick={() => setSelectedIssue(null)} className="bg-transparent border-none outline-none focus:outline-none text-gray-500 hover:text-error transition-colors flex items-center justify-center p-2" title="Cerrar">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>
      </div>

      <div className="flex-1 bg-black/60 p-4 relative overflow-hidden flex items-center justify-center">
        <TransformWrapper initialScale={1} minScale={0.5} maxScale={4} centerOnInit>
          <TransformComponent wrapperStyle={{ width: "100%", height: "100%" }} contentStyle={{ width: "100%", height: "100%", display: "flex", justifyContent: "center", alignItems: "center" }}>
            <img
              src={`${API_BASE}/preview?pdf_path=${encodeURIComponent(selectedIssue.pdf_path)}&page=${selectedIssue.page}`}
              alt="Preview"
              className="max-w-full max-h-full object-contain shadow-2xl rounded"
              draggable="false"
            />
          </TransformComponent>
        </TransformWrapper>
      </div>

      <div className="p-6 bg-surface border-t border-[#313244]">
        <p className="text-sm text-gray-300 mb-4 whitespace-pre-wrap font-mono bg-base p-3 border border-gray-700 rounded-lg">
          Error: {selectedIssue.detail}
        </p>

        <div className="flex space-x-4 mb-6">
          <div className="flex-1">
            <label className="block text-xs uppercase tracking-wider text-gray-400 mb-1">Página Actual</label>
            <input
              type="number"
              value={correctCurr}
              onChange={(e) => setCorrectCurr(e.target.value)}
              placeholder="Inferido"
              className="w-full bg-base border border-[#313244] text-white p-3 rounded-lg focus:outline-none focus:border-accent font-mono text-center text-xl placeholder:text-gray-600"
              autoFocus
            />
          </div>
          <div className="flex items-end justify-center pb-3 text-2xl text-gray-500 font-light">/</div>
          <div className="flex-1">
            <label className="block text-xs uppercase tracking-wider text-gray-400 mb-1">Total del Doc.</label>
            <input
              type="number"
              value={correctTot}
              onChange={(e) => setCorrectTot(e.target.value)}
              placeholder="Inferido"
              className="w-full bg-base border border-[#313244] text-white p-3 rounded-lg focus:outline-none focus:border-accent font-mono text-center text-xl placeholder:text-gray-600"
            />
          </div>
        </div>

        <div className="flex space-x-3">
          <button
            onClick={handleExclude}
            className="flex-none bg-surface border border-error/50 text-error hover:bg-error hover:text-[#11111b] px-4 py-3 rounded-xl font-bold text-sm transition-all focus:ring-2 focus:ring-error outline-none"
            title="Excluir página del conteo"
          >
            🗑 Excluir
          </button>
          <button
            onClick={handleCorrect}
            className="flex-1 bg-accent text-base py-3 rounded-xl font-bold text-lg hover:shadow-[0_0_15px_rgba(137,180,250,0.4)] hover:opacity-90 transition-all flex items-center justify-center focus:ring-2 focus:ring-accent outline-none"
          >
            ✓ Validar e Inferir
          </button>
        </div>
      </div>
    </div>
  );
};
