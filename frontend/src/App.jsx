import { useEffect, useRef } from 'react';
import { useWebSocket } from './hooks/useWebSocket';
import { useApi } from './hooks/useApi';
import { useStore } from './store/useStore';
import { HeaderBar } from './components/HeaderBar';
import { Sidebar } from './components/Sidebar';
import { ProgressBar } from './components/ProgressBar';
import { IssueInbox } from './components/IssueInbox';
import { Terminal } from './components/Terminal';
import { CorrectionPanel } from './components/CorrectionPanel';
import { HistoryModal } from './components/HistoryModal';
import { ConfirmModal } from './components/ConfirmModal';

function App() {
  const preCascadeRef = useRef(null);

  // Initialize hooks containing WebSocket connection and API handlers
  useWebSocket(preCascadeRef);
  const api = useApi({ preCascadeRef });

  const setSpinFrame = useStore(s => s.setSpinFrame);
  const metrics = useStore(s => s.metrics);

  useEffect(() => {
    const handleKeyDown = (e) => {
      // Direct state polling via Zustand prevents this hook from re-registering
      if (!useStore.getState().selectedIssue) return;
      if (document.activeElement.tagName === 'INPUT') return;
      if (e.key === 'ArrowRight') api.navigateIssue(1);
      else if (e.key === 'ArrowLeft') api.navigateIssue(-1);
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  useEffect(() => {
    const id = setInterval(() => setSpinFrame(f => (f + 1) % 4), 80);
    return () => clearInterval(id);
  }, [setSpinFrame]);

  return (
    <div className="h-screen w-screen bg-base text-gray-200 flex flex-col font-sans overflow-hidden relative">
      <div className="absolute inset-0 opacity-20 pointer-events-none" style={{ background: 'radial-gradient(circle at 15% 50%, rgba(137, 180, 250, 0.4), transparent 30%), radial-gradient(circle at 85% 30%, rgba(243, 139, 168, 0.3), transparent 30%)' }}></div>

      <HeaderBar api={api} />

      {/* Metrics Summary Bar */}
      <div className="h-10 bg-panel/60 backdrop-blur-md px-6 flex items-center shadow-lg space-x-8 text-sm border-b border-white/5 z-10 relative">
        <div className="font-bold text-white tracking-wide">RESUMEN GLOBAL:</div>
        <div className="flex items-center"><span className="w-2.5 h-2.5 rounded-full bg-accent mr-2 shadow-[0_0_10px_rgba(137,180,250,0.8)]"></span>Documentos: <span className="ml-1 font-mono font-bold">{metrics.docs || 0}</span></div>
        <div className="flex items-center"><span className="w-2.5 h-2.5 rounded-full bg-success mr-2 shadow-[0_0_10px_rgba(166,227,161,0.8)]"></span>Completos: <span className="ml-1 font-mono font-bold">{metrics.complete || 0}</span></div>
        <div className="flex items-center"><span className="w-2.5 h-2.5 rounded-full bg-error mr-2 shadow-[0_0_10px_rgba(243,139,168,0.8)]"></span>Incompletos: <span className="ml-1 font-mono font-bold">{metrics.incomplete || 0}</span></div>
        <div className="flex items-center"><span className="w-2.5 h-2.5 rounded-full bg-warning mr-2 shadow-[0_0_10px_rgba(250,179,135,0.8)]"></span>Pág. Inferidas: <span className="ml-1 font-mono font-bold">{metrics.inferred || 0}</span></div>
      </div>

      <div className="flex-1 flex flex-row overflow-hidden z-10">
        <Sidebar api={api} />

        <div className="flex-1 flex flex-col min-w-0">
          <ProgressBar />

          <div className="flex-1 flex flex-row overflow-hidden relative">
            <div className="flex-1 flex flex-col bg-transparent overflow-hidden relative min-w-0">
              <IssueInbox />
              <Terminal />
            </div>

            <CorrectionPanel api={api} />
          </div>
        </div>
      </div>

      <HistoryModal api={api} />
      <ConfirmModal />
    </div>
  );
}

export default App;
