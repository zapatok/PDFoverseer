export const HeaderBar = ({ onAddFolder, onAddFiles, onNewSession, onSave, onHistory, controls }) => {
  const { status, globalProg, pdfs, handleStart, handlePause, handleResume, handleStop, handleSkip, setConfirmModal } = controls;
  return (
    <div className="h-16 bg-surface/80 backdrop-blur-xl border-b border-white/5 px-6 flex items-center justify-between shadow-lg z-20">
      <div className="flex items-center space-x-3">
        <button onClick={onAddFolder} className="bg-panel hover:bg-surface text-gray-300 font-medium py-1.5 px-4 rounded transition-colors text-sm shadow flex items-center border border-[#313244]">
          Abrir Carpeta
        </button>
        <button onClick={onAddFiles} className="bg-panel hover:bg-surface text-gray-300 font-medium py-1.5 px-4 rounded transition-colors text-sm shadow flex items-center border border-[#313244]">
          Abrir Archivos
        </button>
        <div className="w-px h-6 bg-gray-700 mx-1"></div>
        <button onClick={onNewSession} className="bg-panel hover:bg-surface text-gray-300 font-medium py-1.5 px-4 rounded transition-colors text-sm shadow flex items-center border border-[#313244]">
          Nueva Sesión
        </button>
        <button onClick={onSave} className="bg-panel hover:bg-surface text-gray-300 font-medium py-1.5 px-4 rounded transition-colors text-sm shadow flex items-center border border-[#313244]">
          Guardar
        </button>
        <button onClick={onHistory} className="bg-panel/40 border-accent/30 hover:bg-accent/20 hover:border-accent text-accent font-medium py-1.5 px-4 rounded transition-colors text-sm shadow flex items-center border">
          Historial
        </button>
      </div>

      <div className="flex items-center px-4 py-2">
        <div className="flex items-center justify-center space-x-2 bg-black/50 backdrop-blur-xl rounded-full border border-white/10 px-2 py-1 shadow-inner">
          {(!status || status === 'idle' || globalProg.paused) ? (
            <button
              onClick={() => {
                if (globalProg.paused) {
                  handleResume();
                } else {
                  const hasProgress = pdfs.some(p => p.status === 'done' || p.status === 'error' || p.status === 'skipped');
                  if (hasProgress && status !== 'running') {
                    setConfirmModal({
                      isOpen: true,
                      title: 'Opciones de Inicio',
                      message: 'Existen documentos consolidados en la lista. ¿Deseas reanudar desde el primer documento pendiente o reiniciar el recorrido desde cero?',
                      isAlert: false,
                      buttons: [
                        { label: 'Reiniciar', onClick: () => handleStart(0), className: 'px-4 py-2 rounded-lg bg-surface hover:bg-white/5 text-gray-300 transition-colors text-sm font-medium border border-white/5' },
                        { label: 'Reanudar', onClick: () => { const firstPending = pdfs.findIndex(p => p.status === 'pending' || p.status === 'error'); handleStart(Math.max(0, firstPending)); }, className: 'px-4 py-2 rounded-lg bg-green-500/20 hover:bg-green-500/30 text-green-400 font-bold transition-all text-sm border border-green-500/30' }
                      ]
                    });
                  } else {
                    handleStart(0);
                  }
                }
              }}
              disabled={(status === 'running' && !globalProg.paused) || pdfs.every(p => p.status === 'done')}
              className="group flex-none flex items-center justify-center px-3 bg-transparent text-gray-500 hover:text-green-400 transition-colors disabled:opacity-50 disabled:pointer-events-none"
              title={globalProg.paused ? "Reanudar" : "Iniciar Lote"}
            >
              <svg className="w-6 h-6 ml-1" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>
            </button>
          ) : (
            <button onClick={handlePause} disabled={status !== 'running'} className="group flex-none flex items-center justify-center px-3 bg-transparent text-gray-500 hover:text-orange-400 transition-colors disabled:opacity-50 disabled:pointer-events-none" title="Pausar">
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z" /></svg>
            </button>
          )}

          <div className="w-[1px] h-5 bg-white/20 mx-1"></div>

          <button onClick={handleStop} disabled={status !== 'running' && !globalProg.paused} className="group flex-none flex items-center justify-center px-3 bg-transparent text-gray-500 hover:text-red-400 transition-colors disabled:opacity-50 disabled:pointer-events-none" title="Detener">
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M6 6h12v12H6z" /></svg>
          </button>

          <div className="w-[1px] h-5 bg-white/20 mx-1"></div>

          <button onClick={handleSkip} disabled={status !== 'running' && !globalProg.paused} className="group flex-none flex items-center justify-center px-3 bg-transparent text-gray-500 hover:text-blue-400 transition-colors disabled:opacity-50 disabled:pointer-events-none" title="Saltar Actual">
            <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M4 18l8.5-6L4 6v12zm9-12v12l8.5-6L13 6z" /></svg>
          </button>
        </div>
      </div>
    </div>
  );
};
