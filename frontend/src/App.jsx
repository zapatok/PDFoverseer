import { useState, useRef, useEffect } from 'react';
import { useWebSocket } from './hooks/useWebSocket';
import { useApi } from './hooks/useApi';
import { HeaderBar } from './components/HeaderBar';
import { Sidebar } from './components/Sidebar';
import { ProgressBar } from './components/ProgressBar';
import { IssueInbox } from './components/IssueInbox';
import { Terminal } from './components/Terminal';
import { CorrectionPanel } from './components/CorrectionPanel';
import { HistoryModal } from './components/HistoryModal';
import { ConfirmModal } from './components/ConfirmModal';

function App() {
  const [pdfs, setPdfs] = useState([]);
  const [issues, setIssues] = useState([]);
  const [metrics, setMetrics] = useState({ docs: 0, complete: 0, incomplete: 0, inferred: 0 });
  const [globalProg, setGlobalProg] = useState({ done: 0, total: 0, elapsed: 0, eta: 0, paused: false });
  const [fileProg, setFileProg] = useState({ done: 0, total: 0, filename: '' });
  const [logs, setLogs] = useState([]);
  const [aiLogs, setAiLogs] = useState([]);
  const [scanLine, setScanLine] = useState(null);
  const [spinFrame, setSpinFrame] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setSpinFrame(f => (f + 1) % 4), 80);
    return () => clearInterval(id);
  }, []);

  const [status, setStatus] = useState('idle');
  const [selectedIssue, setSelectedIssue] = useState(null);
  const [correctCurr, setCorrectCurr] = useState('');
  const [correctTot, setCorrectTot] = useState('');
  const [selectedPdfFilter, setSelectedPdfFilter] = useState('');
  const [selectedPdfPath, setSelectedPdfPath] = useState('');
  const [showHistory, setShowHistory] = useState(false);
  const [historySessions, setHistorySessions] = useState([]);
  const [confirmModal, setConfirmModal] = useState({ isOpen: false, title: '', message: '', onConfirm: null, isAlert: false });
  const [showTerminal, setShowTerminal] = useState(true);
  const [aiLogMode, setAiLogMode] = useState(false);
  const [showAllIssues, setShowAllIssues] = useState(false);
  const [cascadeToast, setCascadeToast] = useState(null);
  
  const preCascadeRef = useRef(null);
  const logsEndRef = useRef(null);

  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs, aiLogs, aiLogMode]);

  const setters = {
    setPdfs, setIssues, setMetrics, setGlobalProg, setStatus, setFileProg, 
    setLogs, setAiLogs, setScanLine, setCascadeToast, setConfirmModal, 
    setHistorySessions, setShowHistory, setSelectedPdfFilter, setSelectedPdfPath,
    setSelectedIssue, setCorrectCurr, setCorrectTot
  };

  const states = {
    selectedPdfFilter, selectedPdfPath, selectedIssue, fileProg, issues,
    metrics, correctCurr, correctTot, 
    filteredIssuesList: (selectedPdfPath ? issues.filter(i => i.pdf_path === selectedPdfPath) : issues)
      .filter(i => showAllIssues || (i.impact || 'internal') !== 'internal')
      .sort((a, b) => {
        // Basic priority sorting matching what was in monolithic App
        const p1 = a.impact === 'ph5b' ? 1 : a.impact === 'ph5-merge' ? 2 : a.impact === 'boundary' ? 3 : a.impact === 'sequence' ? 4 : a.impact === 'orphan' ? 5 : 6;
        const p2 = b.impact === 'ph5b' ? 1 : b.impact === 'ph5-merge' ? 2 : b.impact === 'boundary' ? 3 : b.impact === 'sequence' ? 4 : b.impact === 'orphan' ? 5 : 6;
        return p1 - p2;
      })
  };

  const refs = { preCascadeRef };

  // Initialize hooks
  useWebSocket(setters, preCascadeRef);
  
  const api = useApi(setters, states, refs);

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (!selectedIssue) return;
      if (document.activeElement.tagName === 'INPUT') return;
      if (e.key === 'ArrowRight') api.navigateIssue(1);
      else if (e.key === 'ArrowLeft') api.navigateIssue(-1);
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedIssue, issues, showAllIssues, selectedPdfPath]);

  return (
    <div className="h-screen w-screen bg-base text-gray-200 flex flex-col font-sans overflow-hidden relative">
      <div className="absolute inset-0 opacity-20 pointer-events-none" style={{ background: 'radial-gradient(circle at 15% 50%, rgba(137, 180, 250, 0.4), transparent 30%), radial-gradient(circle at 85% 30%, rgba(243, 139, 168, 0.3), transparent 30%)' }}></div>

      <HeaderBar 
        onAddFolder={api.handleAddFolder}
        onAddFiles={api.handleAddFiles}
        onNewSession={api.handleNewSession}
        onSave={api.handleSaveSession}
        onHistory={api.handleViewHistory}
        controls={{ status, globalProg, pdfs, handleStart: api.handleStart, handlePause: api.handlePause, handleResume: api.handleResume, handleStop: api.handleStop, handleSkip: api.handleSkip, setConfirmModal }}
      />

      {/* Metrics Summary Bar */}
      <div className="h-10 bg-panel/60 backdrop-blur-md px-6 flex items-center shadow-lg space-x-8 text-sm border-b border-white/5 z-10 relative">
        <div className="font-bold text-white tracking-wide">RESUMEN GLOBAL:</div>
        <div className="flex items-center"><span className="w-2.5 h-2.5 rounded-full bg-accent mr-2 shadow-[0_0_10px_rgba(137,180,250,0.8)]"></span>Documentos: <span className="ml-1 font-mono font-bold">{metrics.docs || 0}</span></div>
        <div className="flex items-center"><span className="w-2.5 h-2.5 rounded-full bg-success mr-2 shadow-[0_0_10px_rgba(166,227,161,0.8)]"></span>Completos: <span className="ml-1 font-mono font-bold">{metrics.complete || 0}</span></div>
        <div className="flex items-center"><span className="w-2.5 h-2.5 rounded-full bg-error mr-2 shadow-[0_0_10px_rgba(243,139,168,0.8)]"></span>Incompletos: <span className="ml-1 font-mono font-bold">{metrics.incomplete || 0}</span></div>
        <div className="flex items-center"><span className="w-2.5 h-2.5 rounded-full bg-warning mr-2 shadow-[0_0_10px_rgba(250,179,135,0.8)]"></span>Pág. Inferidas: <span className="ml-1 font-mono font-bold">{metrics.inferred || 0}</span></div>
      </div>

      <div className="flex-1 flex flex-row overflow-hidden z-10">
        <Sidebar 
          pdfs={pdfs}
          fileProg={fileProg}
          metrics={metrics}
          status={status}
          selectedPdfFilter={selectedPdfFilter}
          selectedPdfPath={selectedPdfPath}
          setSelectedPdfFilter={setSelectedPdfFilter}
          setSelectedPdfPath={setSelectedPdfPath}
          handleRemovePdf={api.handleRemovePdf}
          handleOpenAnyPdf={api.handleOpenAnyPdf}
        />

        <div className="flex-1 flex flex-col min-w-0">
          <ProgressBar status={status} globalProg={globalProg} fileProg={fileProg} />

          <div className="flex-1 flex flex-row overflow-hidden relative">
            <div className="flex-1 flex flex-col bg-transparent overflow-hidden relative min-w-0">
              
              <IssueInbox 
                filteredIssuesList={states.filteredIssuesList}
                selectedIssue={selectedIssue}
                setSelectedIssue={setSelectedIssue}
                showAllIssues={showAllIssues}
                setShowAllIssues={setShowAllIssues}
                cascadeToast={cascadeToast}
                metrics={metrics}
                pdfs={pdfs}
                selectedPdfFilter={selectedPdfFilter}
                selectedPdfPath={selectedPdfPath}
                fileProg={fileProg}
                issues={issues}
              />

              <Terminal 
                showTerminal={showTerminal}
                setShowTerminal={setShowTerminal}
                aiLogMode={aiLogMode}
                setAiLogMode={setAiLogMode}
                logs={logs}
                aiLogs={aiLogs}
                scanLine={scanLine}
                spinFrame={spinFrame}
                logsEndRef={logsEndRef}
              />
            </div>

            <CorrectionPanel 
              selectedIssue={selectedIssue}
              setSelectedIssue={setSelectedIssue}
              correctCurr={correctCurr}
              setCorrectCurr={setCorrectCurr}
              correctTot={correctTot}
              setCorrectTot={setCorrectTot}
              handleExclude={api.handleExclude}
              handleCorrect={api.handleCorrect}
              handleOpenNativePdf={api.handleOpenNativePdf}
              navigateIssue={api.navigateIssue}
            />
          </div>
        </div>
      </div>

      <HistoryModal 
        show={showHistory}
        sessions={historySessions}
        onClose={() => setShowHistory(false)}
        onDelete={api.handleDeleteSession}
      />

      <ConfirmModal config={confirmModal} onClose={() => setConfirmModal({ ...confirmModal, isOpen: false })} />
    </div>
  );
}

export default App;
