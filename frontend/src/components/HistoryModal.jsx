import { formatTime } from '../lib/constants';
import { useStore } from '../store/useStore';

export const HistoryModal = ({ api }) => {
  const show = useStore(s => s.showHistory);
  const sessions = useStore(s => s.historySessions);
  const setShowHistory = useStore(s => s.setShowHistory);
  
  const { handleDeleteSession } = api;

  if (!show) return null;
  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-md z-50 flex items-center justify-center">
      <div className="bg-surface border border-white/10 rounded-2xl shadow-2xl w-[800px] h-[600px] flex flex-col">
        <div className="p-6 border-b border-white/10 flex justify-between items-center">
          <h2 className="text-2xl font-bold text-gray-100">Historial de Sesiones Guardadas</h2>
          <button 
            onClick={() => setShowHistory(false)} 
            className="bg-transparent border-none outline-none text-gray-500 hover:text-error transition-colors flex items-center justify-center p-2 rounded-lg"
            title="Cerrar Historial"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {sessions.length === 0 ? (
            <div className="text-gray-500 text-center mt-20">No hay sesiones guardadas aún.</div>
          ) : (
            sessions.map((s, idx) => (
              <div key={idx} className="bg-white/5 border border-white/5 rounded-xl p-5 flex justify-between items-center hover:bg-black/60 transition-colors relative group">
                <button
                  onClick={() => handleDeleteSession(s.timestamp)}
                  className="absolute top-3 right-3 text-[#dc3545] opacity-50 hover:opacity-100 hover:text-red-400 p-1 rounded flex items-center justify-center transition-all bg-transparent border-none outline-none"
                  title="Eliminar sesión"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" /></svg>
                </button>
                <div>
                  <div className="text-gray-200 font-bold text-lg mb-1 pr-6">
                    Sesión: {s.timestamp.substring(0, 4)}-{s.timestamp.substring(4, 6)}-{s.timestamp.substring(6, 8)} {s.timestamp.substring(9, 11)}:{s.timestamp.substring(11, 13)}
                  </div>
                  <div className="text-gray-400 text-sm">Archivos Procesados: <span className="text-white">{s.files_processed}</span></div>
                  <div className="text-gray-400 text-sm">Problemas Totales: <span className="text-warning font-bold">{s.issues_count}</span></div>
                  {s.metrics.total_time !== undefined && (
                    <div className="text-gray-400 text-sm mt-1">Tiempo de proceso: <span className="text-accent font-mono">{formatTime(s.metrics.total_time)}</span></div>
                  )}
                </div>
                <div className="flex space-x-6 text-sm bg-panel/30 group-hover:bg-panel/80 p-3 rounded-lg border border-white/5">
                  <div className="flex flex-col items-center"><span className="text-gray-400">Documentos</span><span className="font-bold text-white text-lg">{s.metrics.docs}</span></div>
                  <div className="flex flex-col items-center"><span className="text-gray-400">Directo</span><span className="font-bold text-success text-lg">{s.metrics.direct || s.metrics.complete}</span></div>
                  <div className="flex flex-col items-center"><span className="text-gray-400">Inferido</span><span className="font-bold text-warning text-lg">{(s.metrics.inferred_hi || 0) + (s.metrics.inferred_lo || 0)}</span></div>
                  <div className="flex flex-col items-center"><span className="text-gray-400">Incompleto</span><span className="font-bold text-error text-lg">{s.metrics.incomplete}</span></div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};
