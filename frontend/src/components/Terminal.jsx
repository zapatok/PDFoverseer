import { SPINNER } from '../lib/constants';

export const Terminal = ({ 
  showTerminal, 
  setShowTerminal, 
  aiLogMode, 
  setAiLogMode, 
  logs, 
  aiLogs, 
  scanLine, 
  spinFrame, 
  logsEndRef 
}) => {
  const handleCopyLogs = () => {
    const filtered = aiLogMode ? aiLogs : logs;
    const text = filtered.map(l => l.msg).join('\n');
    navigator.clipboard.writeText(text);
  };

  const handleExportLogs = () => {
    const filtered = aiLogMode ? aiLogs : logs;
    const text = filtered.map(l => l.msg).join('\n');
    const blob = new Blob([text], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `logs_${new Date().getTime()}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (!showTerminal) {
    return (
      <div className="absolute bottom-4 right-4 z-30">
        <button 
          onClick={() => setShowTerminal(true)}
          className="bg-black/90 backdrop-blur-xl border border-white/5 text-gray-400 hover:text-white font-mono uppercase text-[10px] tracking-widest font-bold px-4 py-2 flex items-center shadow-lg transition-all rounded"
          title="Mostrar Terminal"
        >
          TERMINAL
          <svg className="w-4 h-4 ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" /></svg>
        </button>
      </div>
    );
  }

  return (
    <div className="h-56 bg-black/80 backdrop-blur-xl border-t border-white/10 overflow-y-auto font-mono text-xs flex flex-col shadow-inner relative custom-scroll">
      <div className="sticky top-0 w-full bg-black/90 border-b border-white/5 px-4 py-2 flex justify-between items-center z-20 shadow-sm relative">
        <span className="text-gray-500 uppercase font-bold tracking-widest text-[10px]">Terminal de Procesos</span>
        
        <div className="flex items-center space-x-3 h-full">
          <button onClick={() => setAiLogMode(v => !v)} className={`border-none outline-none focus:outline-none font-bold text-[10px] tracking-wider px-2 py-0.5 rounded transition-all ${aiLogMode ? 'bg-purple-600 text-white' : 'bg-transparent text-purple-400 hover:text-purple-300'}`} title="Modo AI Log (compacto para Claude)">
            AI
          </button>
          <div className="w-px h-4 bg-white/10"></div>
          <button onClick={handleCopyLogs} className="bg-transparent border-none outline-none focus:outline-none text-gray-600 hover:text-gray-300 transition-colors" title={aiLogMode ? "Copiar AI Logs" : "Copiar Logs"}>
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
          </button>
          <button onClick={handleExportLogs} className="bg-transparent border-none outline-none focus:outline-none text-gray-600 hover:text-gray-300 transition-colors" title="Exportar a TXT">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>
          </button>
          <div className="w-px h-4 bg-white/10"></div>
          <button onClick={() => setShowTerminal(false)} className="bg-transparent border-none outline-none focus:outline-none text-gray-600 hover:text-gray-300 transition-colors" title="Ocultar Terminal">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
          </button>
        </div>
      </div>
      <div className="p-4 space-y-1">
        {(aiLogMode ? aiLogs : logs).map((log, i) => (
          <div key={i} className={`whitespace-pre-wrap px-1 ${i % 2 === 1 && log.level === 'info' ? 'bg-white/[0.03]' : ''} ${log.level === 'ai_inf' ? 'text-violet-300 bg-violet-900/15 px-2 py-0.5 rounded' : log.level === 'ai' ? 'text-purple-400 font-bold bg-purple-900/20 px-2 py-0.5 rounded' : log.level === 'warn' ? 'text-warning' : log.level === 'error' ? 'text-error font-bold' : log.level === 'ok' || log.level === 'success' ? 'text-success' : log.level === 'file_hdr' ? 'text-accent font-bold mt-4 text-sm bg-accent/10 px-2 py-1 inline-block rounded' : log.level === 'section' ? 'text-gray-400 mt-2 italic' : 'text-gray-400'}`}>
            {log.msg}
          </div>
        ))}
        {scanLine && (
          <div className={`whitespace-pre-wrap px-1 font-bold ${scanLine.level === 'page_warn' ? 'text-yellow-500/70' : 'text-gray-500'}`}>
            <span className="text-cyan-500 mr-2">{SPINNER[spinFrame]}</span>{scanLine.msg}
          </div>
        )}
        <div ref={logsEndRef} />
      </div>
    </div>
  );
};
