import { formatTime } from '../lib/constants';

export const ProgressBar = ({ status, globalProg, fileProg }) => {
  return (
    <div className="w-full bg-surface/80 backdrop-blur-md border-b border-white/5 shadow-md flex flex-col shrink-0 z-20">
      <div className="flex justify-between items-center text-xs px-8 py-2.5 text-gray-300 font-medium h-[42px]">
        
        <div className="flex items-center space-x-6 w-1/2">
          <div className="flex items-center space-x-2">
            <span className="uppercase text-[10px] tracking-widest text-gray-500">Progreso Actual</span>
            {status === 'running' || fileProg.total > 0 ? (
              <span className="font-mono bg-black/40 px-2 py-0.5 rounded text-accent flex-shrink-0">{fileProg.done} / {fileProg.total}</span>
            ) : (
              <span className="text-gray-500 italic px-2">En espera...</span>
            )}
          </div>
          
          <div className="flex items-center space-x-2">
            <span className="uppercase text-[10px] tracking-widest text-gray-500">Lote Global</span>
            <span className="font-mono bg-black/40 px-2 py-0.5 rounded text-accent flex-shrink-0">{globalProg.done} / {globalProg.total}</span>
          </div>
        </div>

        <div className="flex items-center justify-end w-1/2">
          <div className="flex items-center space-x-3 text-[11px] font-mono bg-black/30 border border-white/5 px-3 py-1 rounded shadow-inner">
            <span className={status === 'running' && !globalProg.paused ? "text-gray-100" : "text-gray-500"}>⏱ {formatTime(globalProg.elapsed || 0)}</span>
            <span className="text-gray-600">|</span>
            <span className={status === 'running' && !globalProg.paused ? "text-accent" : "text-gray-500"}>ETA {formatTime(globalProg.eta || 0)}</span>
          </div>
        </div>

      </div>
      <div className="h-2 w-full bg-black/40 overflow-hidden">
        <div className={`h-2 bg-accent rounded-r-full shadow-[0_0_12px_rgba(137,180,250,1)] transition-all duration-500 ease-out ${status === 'running' && !globalProg.paused ? 'animate-pulse' : ''}`}
          style={{ width: `${globalProg.total > 0 ? (globalProg.done / globalProg.total) * 100 : 0}%` }}></div>
      </div>
    </div>
  );
};
