import { useState, useEffect, useRef } from 'react'
import { TransformWrapper, TransformComponent } from 'react-zoom-pan-pinch'

function App() {
  const [pdfs, setPdfs] = useState([])
  const [issues, setIssues] = useState([])
  const [metrics, setMetrics] = useState({ docs: 0, complete: 0, incomplete: 0, inferred: 0 })
  const [globalProg, setGlobalProg] = useState({ done: 0, total: 0, elapsed: 0, eta: 0, paused: false })
  const [fileProg, setFileProg] = useState({ done: 0, total: 0, filename: '' })
  const [logs, setLogs] = useState([])
  const [aiLogs, setAiLogs] = useState([])
  const [scanLine, setScanLine] = useState(null) // spinning page indicator
  const [spinFrame, setSpinFrame] = useState(0)
  const SPINNER = ['/', '-', '\\', '|']

  useEffect(() => {
    const id = setInterval(() => setSpinFrame(f => (f + 1) % 4), 80)
    return () => clearInterval(id)
  }, [])

  const [status, setStatus] = useState('idle') // idle, running, stopped
  const [selectedIssue, setSelectedIssue] = useState(null)

  // Correction State
  const [correctCurr, setCorrectCurr] = useState('')
  const [correctTot, setCorrectTot] = useState('')

  const [selectedPdfFilter, setSelectedPdfFilter] = useState('')
  const [selectedPdfPath, setSelectedPdfPath] = useState('')
  const [showHistory, setShowHistory] = useState(false)
  const [historySessions, setHistorySessions] = useState([])
  const [confirmModal, setConfirmModal] = useState({ isOpen: false, title: '', message: '', onConfirm: null, isAlert: false });
  const [showTerminal, setShowTerminal] = useState(true)
  const [terminalMenuOpen, setTerminalMenuOpen] = useState(false)
  const [aiLogMode, setAiLogMode] = useState(false)
  const [showAllIssues, setShowAllIssues] = useState(false)
  const [cascadeToast, setCascadeToast] = useState(null)
  const preCascadeRef = useRef(null)

  const IMPACT_PRIORITY = {
    'ph5b': 1,
    'ph5-merge': 2,
    'boundary': 3,
    'sequence': 4,
    'orphan': 5,
    'internal': 6,
  };

  const IMPACT_LABELS = {
    'ph5b': { label: 'Ph5b', color: 'text-red-400 bg-red-400/10' },
    'ph5-merge': { label: 'Fusión', color: 'text-orange-400 bg-orange-400/10' },
    'boundary': { label: 'Frontera', color: 'text-yellow-400 bg-yellow-400/10' },
    'sequence': { label: 'Secuencia', color: 'text-red-400 bg-red-400/10' },
    'orphan': { label: 'Huérfana', color: 'text-red-400 bg-red-400/10' },
    'internal': { label: 'Interna', color: 'text-gray-500 bg-gray-500/10' },
  };

  const handleCopyLogs = () => {
    const filtered = aiLogMode ? aiLogs : logs;
    const text = filtered.map(l => l.msg).join('\n');
    navigator.clipboard.writeText(text);
    setTerminalMenuOpen(false);
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
    setTerminalMenuOpen(false);
  };

  // F5 Survival: Reload state from backend on mount
  useEffect(() => {
    fetch('http://localhost:8000/api/state')
      .then(res => res.json())
      .then(data => {
        if (data.running || (data.pdf_list && data.pdf_list.length > 0)) {
          setPdfs(data.pdf_list)
          setIssues(data.issues || [])
          setMetrics(data.metrics || { docs: 0, complete: 0, incomplete: 0, inferred: 0 })
          setGlobalProg(data.globalProg || { done: 0, total: 0, elapsed: 0, eta: 0 })
          if (data.running) setStatus('running')
        }
      })
      .catch(e => console.error("Could not recover state", e))
  }, [])

  // Connection Ref
  const ws = useRef(null)

  useEffect(() => {
    // Setup WebSocket
    ws.current = new WebSocket('ws://localhost:8000/ws')

    ws.current.onmessage = (event) => {
      let data
      try {
        data = JSON.parse(event.data)
      } catch (e) {
        console.error('WebSocket: invalid JSON received', e)
        return
      }
      const { type, payload } = data

      if (type === 'log') {
        if (payload.level === 'ai' || payload.level === 'ai_inf') {
          setAiLogs(prev => [...prev, payload])
        } else if (payload.level === 'page_ok' || payload.level === 'page_warn') {
          setScanLine({ msg: payload.msg, level: payload.level })
        } else {
          if (payload.level === 'file_hdr') setScanLine(null)
          setLogs(prev => [...prev.slice(-199), payload])
        }
      } else if (type === 'status_update') {
        setPdfs(prev => {
          const arr = [...prev]
          if (arr[payload.idx]) arr[payload.idx].status = payload.status
          return arr
        })
      } else if (type === 'global_progress') {
        setGlobalProg(prev => ({ ...prev, ...payload }))
      } else if (type === 'file_progress') {
        setFileProg(payload)
      } else if (type === 'new_issue') {
        setIssues(prev => [...prev, payload])
      } else if (type === 'issues_refresh') {
        // CASCADING RESET: El backend manda { pdf_path, issues }
        setIssues(prev => {
          if (!payload.pdf_path) return prev;
          const targetPdf = payload.pdf_path;
          const newList = [...prev.filter(i => i.pdf_path !== targetPdf), ...(payload.issues || [])];

          // Cascade impact toast
          if (preCascadeRef.current) {
            const prev_snap = preCascadeRef.current;
            const newIssueCount = (payload.issues || []).length;
            const parts = [];
            const issuesDelta = prev_snap.issueCount - newIssueCount;
            if (issuesDelta > 0) parts.push(`${issuesDelta} issues resueltos`);
            if (issuesDelta < 0) parts.push(`${Math.abs(issuesDelta)} issues nuevos`);
            if (parts.length > 0) {
              setCascadeToast(parts.join(', '));
              setTimeout(() => setCascadeToast(null), 5000);
            }
            preCascadeRef.current = null;
          }

          return newList;
        });
      } else if (type === 'metrics') {
        setMetrics(payload)
      } else if (type === 'process_finished') {
        setStatus('idle')
        setScanLine(null)
      }
    }

    return () => {
      if (ws.current) ws.current.close()
    }
  }, [])

  const logsEndRef = useRef(null)
  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [logs])

  const handleAddFolder = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/add_folder')
      const data = await res.json()
      if (data.success && data.pdfs) {
        setPdfs(data.pdfs)
        setStatus('idle')
      }
    } catch (e) {
      console.error(e)
    }
  }

  const handleAddFiles = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/add_files')
      const data = await res.json()
      if (data.success && data.pdfs) {
        setPdfs(data.pdfs)
        setStatus('idle')
      }
    } catch (e) {
      console.error(e)
    }
  }

  const handleRemovePdf = () => {
    if (!selectedPdfPath) return;
    setConfirmModal({
      isOpen: true,
      title: 'Remover PDF',
      message: `¿Seguro que deseas remover "${selectedPdfFilter}" de la lista?`,
      isAlert: false,
      onConfirm: async () => {
        try {
          const res = await fetch(`http://localhost:8000/api/remove_pdf?pdf_path=${encodeURIComponent(selectedPdfPath)}`, { method: 'POST' });
          const data = await res.json();
          if (data.success) {
            setPdfs(data.pdfs);
            if (selectedPdfFilter === fileProg.filename) setFileProg({ done: 0, total: 0, filename: '' });
            setSelectedPdfFilter('');
            setSelectedPdfPath('');
          }
        } catch (e) {
          console.error(e);
        }
      }
    });
  }

  const handleNewSession = () => {
    setConfirmModal({
      isOpen: true,
      title: 'Nueva Sesión',
      message: '¿Seguro que deseas iniciar una nueva sesión? Se borrará el progreso actual no guardado.',
      isAlert: false,
      onConfirm: async () => {
        await fetch('http://localhost:8000/api/reset', { method: 'POST' })
        setPdfs([])
        setIssues([])
        setLogs([])
        setAiLogs([])
        setScanLine(null)
        setMetrics({ docs: 0, complete: 0, incomplete: 0, inferred: 0 })
        setGlobalProg({ done: 0, total: 0, elapsed: 0, eta: 0, paused: false })
        setFileProg({ done: 0, total: 0, filename: '' })
        setStatus('idle')
        setSelectedPdfFilter('')
        setSelectedPdfPath('')
        setSelectedIssue(null)
      }
    });
  }

  const handleSaveSession = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/save_session', { method: 'POST' })
      const data = await res.json()
      if (data.success) {
        setConfirmModal({
          isOpen: true,
          title: 'Sesión Guardada',
          message: 'Sesión guardada en el historial permanentemente.',
          isAlert: true,
          onConfirm: null
        });
      }
    } catch (e) {
      console.error(e)
    }
  }

  const handleViewHistory = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/sessions')
      const data = await res.json()
      setHistorySessions(data.sessions || [])
      setShowHistory(true)
    } catch (e) {
      console.error(e)
    }
  }

  const handleDeleteSession = (timestamp) => {
    setConfirmModal({
      isOpen: true,
      title: 'Eliminar Sesión',
      message: '¿Seguro que deseas eliminar el registro de esta sesión del historial permanentemente?',
      isAlert: false,
      onConfirm: async () => {
        try {
          const res = await fetch('http://localhost:8000/api/delete_session', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ timestamp })
          });
          const data = await res.json();
          if (data.success) {
            setHistorySessions(prev => prev.filter(s => s.timestamp !== timestamp));
          } else {
            console.error('Error al eliminar: ' + (data.error || 'Desconocido'));
          }
        } catch (e) {
          console.error('Error de conexión al eliminar.', e);
        }
      }
    });
  }

  const handleOpenNativePdf = async () => {
    if (!selectedIssue) return;
    try {
      await fetch(`http://localhost:8000/api/open_pdf?pdf_path=${encodeURIComponent(selectedIssue.pdf_path)}&page=${selectedIssue.page}`);
    } catch (e) {
      console.error("No se pudo abrir el PDF nativo", e);
    }
  }

  const handleOpenAnyPdf = async (path) => {
    try {
      await fetch(`http://localhost:8000/api/open_pdf?pdf_path=${encodeURIComponent(path)}&page=1`);
    } catch (e) {
      console.error("No se pudo abrir el PDF nativo", e);
    }
  }

  const handleStart = async (startIndex = 0) => {
    setLogs([])
    setAiLogs([])
    setScanLine(null)
    setStatus('running')
    setGlobalProg(prev => ({ ...prev, paused: false }))
    await fetch('http://localhost:8000/api/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ start_index: startIndex })
    })
  }

  const handlePause = async () => {
    setGlobalProg(prev => ({ ...prev, paused: true }))
    await fetch('http://localhost:8000/api/pause', { method: 'POST' })
  }

  const handleResume = async () => {
    setGlobalProg(prev => ({ ...prev, paused: false }))
    await fetch('http://localhost:8000/api/resume', { method: 'POST' })
  }

  const handleStop = async () => {
    await fetch('http://localhost:8000/api/stop', { method: 'POST' })
    setStatus('idle')
  }

  const handleSkip = async () => {
    await fetch('http://localhost:8000/api/skip', { method: 'POST' })
  }

  const formatTime = (seconds) => {
    if (!seconds || isNaN(seconds)) return "00:00";
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  const _getNextIssue = (direction) => {
    if (!selectedIssue || issues.length === 0) return null;
    const currentIndex = issues.findIndex(i => i.id === selectedIssue.id);
    let nextIndex = currentIndex + direction;

    if (nextIndex >= issues.length) nextIndex = 0;
    if (nextIndex < 0) nextIndex = issues.length - 1;
    if (issues.length === 1 || nextIndex === currentIndex) return null;

    return issues[nextIndex];
  };

  const handleCorrect = async () => {
    if (!selectedIssue) return;
    const currentId = selectedIssue.id;
    const nextIssue = _getNextIssue(1);

    let finalCurr = correctCurr;
    let finalTot = correctTot;

    if (!finalCurr || !finalTot) {
      const match = selectedIssue.detail.match(/(\d+)\s*[/de]+\s*(\d+)/i);
      if (match) {
        if (!finalCurr) finalCurr = match[1];
        if (!finalTot) finalTot = match[2];
      } else {
        alert("No se pudo extraer el valor inferido 'X/Y' automáticamente. Escribe los números.");
        return;
      }
    }

    const curr = parseInt(finalCurr);
    const tot = parseInt(finalTot);
    if (isNaN(curr) || isNaN(tot) || curr < 1 || curr > 50 || tot < 1 || tot > 50 || curr > tot) {
      setConfirmModal({
        isOpen: true,
        title: 'Valor Inválido',
        message: 'Ingresa números entre 1 y 50, y la página actual debe ser menor o igual al total.',
        isAlert: true,
        onConfirm: null
      });
      return;
    }

    try {
      // Snapshot for cascade impact toast
      preCascadeRef.current = {
        issueCount: issues.filter(i => i.pdf_path === selectedIssue.pdf_path).length,
      };
      await fetch('http://localhost:8000/api/correct', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pdf_path: selectedIssue.pdf_path,
          page: selectedIssue.page,
          correct_curr: curr,
          correct_tot: tot
        })
      });
      // Removemos optimismamente para UI rapida
      setIssues(prev => prev.filter(i => i.id !== currentId));

      setSelectedIssue(nextIssue);
      setCorrectCurr('');
      setCorrectTot('');
    } catch (e) {
      console.error(e);
    }
  }

  const navigateIssue = (direction) => {
    if (!selectedIssue || issues.length === 0) return;
    const currentIndex = issues.findIndex(i => i.id === selectedIssue.id);
    let nextIndex = currentIndex + direction;
    if (nextIndex < 0) nextIndex = issues.length - 1;
    if (nextIndex >= issues.length) nextIndex = 0;
    setSelectedIssue(issues[nextIndex]);
    setCorrectCurr('');
    setCorrectTot('');
  };

  const handleExclude = async () => {
    if (!selectedIssue) return;
    const currentId = selectedIssue.id;

    const currentIndex = issues.findIndex(i => i.id === currentId);
    let nextIssue = null;
    if (issues.length > 1) {
      nextIssue = issues[currentIndex + 1] || issues[currentIndex - 1];
    }

    try {
      await fetch('http://localhost:8000/api/exclude', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pdf_path: selectedIssue.pdf_path,
          page: selectedIssue.page,
        })
      });
      setIssues(prev => prev.filter(i => i.id !== currentId));
      setSelectedIssue(nextIssue);
      setCorrectCurr('');
      setCorrectTot('');
    } catch (e) {
      console.error(e);
    }
  }

  // Keyboard Navigation
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (!selectedIssue) return;
      if (document.activeElement.tagName === 'INPUT') return; // Don't trigger if typing

      if (e.key === 'ArrowRight') {
        navigateIssue(1);
      } else if (e.key === 'ArrowLeft') {
        navigateIssue(-1);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [selectedIssue, issues]);

  return (
    <div className="h-screen w-screen bg-base text-gray-200 flex flex-col font-sans overflow-hidden relative">
      {/* Dynamic Vivid Background */}
      <div className="absolute inset-0 opacity-20 pointer-events-none" style={{
        background: 'radial-gradient(circle at 15% 50%, rgba(137, 180, 250, 0.4), transparent 30%), radial-gradient(circle at 85% 30%, rgba(243, 139, 168, 0.3), transparent 30%)'
      }}></div>

      {/* Top Header Control Bar */}
      <div className="h-16 bg-surface/80 backdrop-blur-xl border-b border-white/5 px-6 flex items-center justify-between shadow-lg z-20">
        <div className="flex items-center space-x-3">
          <button onClick={handleAddFolder} className="bg-panel hover:bg-surface text-gray-300 font-medium py-1.5 px-4 rounded transition-colors text-sm shadow flex items-center border border-[#313244]">
            Abrir Carpeta
          </button>

          <button onClick={handleAddFiles} className="bg-panel hover:bg-surface text-gray-300 font-medium py-1.5 px-4 rounded transition-colors text-sm shadow flex items-center border border-[#313244]">
            Abrir Archivos
          </button>

          <div className="w-px h-6 bg-gray-700 mx-1"></div>

          <button onClick={handleNewSession} className="bg-panel hover:bg-surface text-gray-300 font-medium py-1.5 px-4 rounded transition-colors text-sm shadow flex items-center border border-[#313244]">
            Nueva Sesión
          </button>

          <button onClick={handleSaveSession} className="bg-panel hover:bg-surface text-gray-300 font-medium py-1.5 px-4 rounded transition-colors text-sm shadow flex items-center border border-[#313244]">
            Guardar
          </button>

          <button onClick={handleViewHistory} className="bg-panel/40 border-accent/30 hover:bg-accent/20 hover:border-accent text-accent font-medium py-1.5 px-4 rounded transition-colors text-sm shadow flex items-center border">
            Historial
          </button>
        </div>

        <div className="flex items-center px-4 py-2">
          {/* Main Controls Pill Container */}
          <div className="flex items-center justify-center space-x-2 bg-black/50 backdrop-blur-xl rounded-full border border-white/10 px-2 py-1 shadow-inner">
            
            {/* Play / Pause Toggle Button */}
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
                          {
                            label: 'Reiniciar',
                            onClick: () => handleStart(0),
                            className: 'px-4 py-2 rounded-lg bg-surface hover:bg-white/5 text-gray-300 transition-colors text-sm font-medium border border-white/5'
                          },
                          {
                            label: 'Reanudar',
                            onClick: () => {
                              const firstPending = pdfs.findIndex(p => p.status === 'pending' || p.status === 'error');
                              handleStart(Math.max(0, firstPending));
                            },
                            className: 'px-4 py-2 rounded-lg bg-green-500/20 hover:bg-green-500/30 text-green-400 font-bold transition-all text-sm border border-green-500/30'
                          }
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
              <button
                onClick={handlePause}
                disabled={status !== 'running'}
                className="group flex-none flex items-center justify-center px-3 bg-transparent text-gray-500 hover:text-orange-400 transition-colors disabled:opacity-50 disabled:pointer-events-none"
                title="Pausar"
              >
                <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z" /></svg>
              </button>
            )}

            <div className="w-[1px] h-5 bg-white/20 mx-1"></div>
            
            {/* Stop Button */}
            <button
              onClick={handleStop}
              disabled={status !== 'running' && !globalProg.paused}
              className="group flex-none flex items-center justify-center px-3 bg-transparent text-gray-500 hover:text-red-400 transition-colors disabled:opacity-50 disabled:pointer-events-none"
              title="Detener"
            >
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M6 6h12v12H6z" /></svg>
            </button>
  
            <div className="w-[1px] h-5 bg-white/20 mx-1"></div>
  
            {/* Skip Button */}
            <button
              onClick={handleSkip}
              disabled={status !== 'running' && !globalProg.paused}
              className="group flex-none flex items-center justify-center px-3 bg-transparent text-gray-500 hover:text-blue-400 transition-colors disabled:opacity-50 disabled:pointer-events-none"
              title="Saltar Actual"
            >
              <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M4 18l8.5-6L4 6v12zm9-12v12l8.5-6L13 6z" /></svg>
            </button>
            
          </div>
        </div>
      </div>

      {/* Metrics Summary Bar */}
      <div className="h-10 bg-panel/60 backdrop-blur-md px-6 flex items-center shadow-lg space-x-8 text-sm border-b border-white/5 z-10 relative">
        <div className="font-bold text-white tracking-wide">RESUMEN GLOBAL:</div>
        <div className="flex items-center"><span className="w-2.5 h-2.5 rounded-full bg-accent mr-2 shadow-[0_0_10px_rgba(137,180,250,0.8)]"></span>Documentos: <span className="ml-1 font-mono font-bold">{metrics.docs}</span></div>
        <div className="flex items-center"><span className="w-2.5 h-2.5 rounded-full bg-success mr-2 shadow-[0_0_10px_rgba(166,227,161,0.8)]"></span>Completos: <span className="ml-1 font-mono font-bold">{metrics.complete}</span></div>
        <div className="flex items-center"><span className="w-2.5 h-2.5 rounded-full bg-error mr-2 shadow-[0_0_10px_rgba(243,139,168,0.8)]"></span>Incompletos: <span className="ml-1 font-mono font-bold">{metrics.incomplete}</span></div>
        <div className="flex items-center"><span className="w-2.5 h-2.5 rounded-full bg-warning mr-2 shadow-[0_0_10px_rgba(250,179,135,0.8)]"></span>Pág. Inferidas: <span className="ml-1 font-mono font-bold">{metrics.inferred}</span></div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-row overflow-hidden z-10">

        {/* Left Sidebar - Files List */}
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
                  onClick={() => { const sel = selectedPdfFilter === p.name; setSelectedPdfFilter(sel ? '' : p.name); setSelectedPdfPath(sel ? '' : p.path); }}
                  onDoubleClick={() => handleOpenAnyPdf(p.path)}
                  className={`group px-3 py-2 rounded-md text-sm cursor-pointer transition-all border flex items-center justify-between relative overflow-hidden
                  ${selectedPdfFilter === p.name ? 'border-accent shadow-[0_0_10px_rgba(137,180,250,0.5)]' : 'border-transparent hover:bg-white/5'}
                  ${status === 'running' && p.name === fileProg.filename && selectedPdfFilter !== p.name ? 'text-accent font-medium' : ''}
                  ${p.status === 'done' && selectedPdfFilter !== p.name && selectedPdfFilter !== p.name ? 'text-gray-300' : ''}
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

        {/* Split Right Side (Progress Bar + Layout) */}
        <div className="flex-1 flex flex-col min-w-0">

          {/* Progress Bar (Always Visible, Full Width across center and right panels) */}
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
              <div className={`h-2 bg-accent rounded-r-full shadow-[0_0_12px_rgba(137,180,250,1)] transition-all duration-500 ease-out ${status === 'running' ? 'animate-pulse' : ''}`}
                style={{ width: `${globalProg.total > 0 ? (globalProg.done / globalProg.total) * 100 : 0}%` }}></div>
            </div>
          </div>

          {/* Inner Layout Container */}
          <div className="flex-1 flex flex-row overflow-hidden relative">

            {/* Center Workspace (Inbox + Terminal) */}
            <div className="flex-1 flex flex-col bg-transparent overflow-hidden relative min-w-0">

              {/* Issue Inbox */}
              <div className="flex-1 overflow-y-auto px-12 py-8 custom-scroll">
                <div className="flex items-center justify-between mb-5 border-b border-white/10 pb-5">
                  <h1 className="text-4xl font-extrabold text-white tracking-tight drop-shadow-md">Bandeja de Problemas</h1>

                  {/* Individual File Metrics Dashboard */}
                  <div className="flex space-x-4 bg-black/40 px-4 py-2 text-xs rounded-xl border border-white/5 shadow-inner">
                    {(() => {
                      const targetName = selectedPdfFilter || fileProg.filename;
                      let ind = { docs: 0, complete: 0, incomplete: 0, inferred: 0 };
                      if (targetName && pdfs.length > 0 && metrics.individual) {
                        const targetPdf = pdfs.find(p => p.name === targetName);
                        if (targetPdf && metrics.individual[targetPdf.path]) {
                          ind = metrics.individual[targetPdf.path];
                        }
                      }
                      // Find the target PDF for verified% calculation
                      const targetPdfForConf = targetName && pdfs.length > 0
                        ? pdfs.find(p => p.name === targetName)
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
                          <div className="flex flex-col items-center justify-center min-w-[30px]" title="Documentos completos con páginas inferidas">
                            <span className="text-gray-500 font-bold mb-1 tracking-widest text-[9px]">INF</span>
                            <span className={`${((ind.inferred_hi || 0) + (ind.inferred_lo || 0)) > 0 ? 'text-warning' : 'text-gray-600'} font-mono font-bold`}>{(ind.inferred_hi || 0) + (ind.inferred_lo || 0)}</span>
                          </div>
                          <div className="w-px h-6 bg-white/5 self-center"></div>
                          <div className="flex flex-col items-center justify-center min-w-[30px]" title="Documentos incompletos">
                            <span className="text-gray-500 font-bold mb-1 tracking-widest text-[9px]">INC</span>
                            <span className={`${(ind.incomplete || 0) > 0 ? 'text-error' : 'text-gray-600'} font-mono font-bold`}>{ind.incomplete || 0}</span>
                          </div>
                          {/* Verified% — fraction of docs fully verified by OCR */}
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
                                <div className="flex flex-col items-center justify-center min-w-[40px]"
                                     title="Porcentaje de documentos con todas las páginas verificadas por OCR">
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
                {/* Cascade impact toast */}
                {cascadeToast && (
                  <div className="bg-accent/10 border border-accent/30 text-accent text-sm px-4 py-2 rounded-lg mb-3 animate-pulse">
                    {cascadeToast}
                  </div>
                )}

                {/* Filter toggle + issue count */}
                {(() => {
                  const filteredIssues = (selectedPdfFilter
                    ? issues.filter(i => i.filename === selectedPdfFilter)
                    : issues
                  ).filter(i => showAllIssues || (i.impact || 'internal') !== 'internal')
                   .sort((a, b) => (IMPACT_PRIORITY[a.impact] || 6) - (IMPACT_PRIORITY[b.impact] || 6));

                  const totalCount = (selectedPdfFilter
                    ? issues.filter(i => i.filename === selectedPdfFilter)
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

              {/* Log Console Terminal (Bottom half of center workspace) */}
              {showTerminal ? (
                <div className="h-56 bg-black/80 backdrop-blur-xl border-t border-white/10 overflow-y-auto font-mono text-xs flex flex-col shadow-inner relative custom-scroll">
                  <div className="sticky top-0 w-full bg-black/90 border-b border-white/5 px-4 py-2 flex justify-between items-center z-20 shadow-sm relative">
                    <span className="text-gray-500 uppercase font-bold tracking-widest text-[10px]">Terminal de Procesos</span>
                    
                    <div className="flex items-center space-x-3 h-full">
                      <button onClick={() => setAiLogMode(v => !v)} className={`border-none outline-none focus:outline-none font-bold text-[10px] tracking-wider px-2 py-0.5 rounded transition-all ${aiLogMode ? 'bg-purple-600 text-white' : 'bg-transparent text-purple-400 hover:text-purple-300'}`} title="Modo AI Log (compacto para Claude)">
                        AI
                      </button>
                      <div className="w-px h-4 bg-white/10"></div>
                      <button onClick={handleCopyLogs} className="bg-transparent border-none outline-none focus:outline-none text-[#842029] hover:text-[#dc3545] transition-colors" title={aiLogMode ? "Copiar AI Logs" : "Copiar Logs"}>
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" /></svg>
                      </button>
                      <button onClick={handleExportLogs} className="bg-transparent border-none outline-none focus:outline-none text-[#842029] hover:text-[#dc3545] transition-colors" title="Exportar a TXT">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>
                      </button>
                      <div className="w-px h-4 bg-white/10"></div>
                      <button onClick={() => setShowTerminal(false)} className="bg-transparent border-none outline-none focus:outline-none text-[#842029] hover:text-[#dc3545] transition-colors" title="Ocultar Terminal">
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
              ) : (
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
              )}

            </div> {/* <-- Cierra Center Workspace (Progress + Inbox + Terminal) */}

            {/* Right Panel - Preview & Correction */}
            {selectedIssue && (
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
                    <button onClick={() => { const n = _getNextIssue(-1); if (n) setSelectedIssue(n); }} className="bg-transparent border-none outline-none focus:outline-none text-gray-500 hover:text-white transition-colors flex items-center justify-center p-2" title="Problema Anterior">
                      <svg className="w-5 h-5" stroke="currentColor" fill="none" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 19l-7-7 7-7" /></svg>
                    </button>
                    <button onClick={() => { const n = _getNextIssue(1); if (n) setSelectedIssue(n); }} className="bg-transparent border-none outline-none focus:outline-none text-gray-500 hover:text-white transition-colors flex items-center justify-center p-2" title="Problema Siguiente">
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
                        src={`http://localhost:8000/api/preview?pdf_path=${encodeURIComponent(selectedIssue.pdf_path)}&page=${selectedIssue.page}`}
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
            )}

          </div> {/* <-- Cierra Inner Layout Container */}
        </div> {/* <-- Cierra Split Right Side */}
      </div> {/* <-- Cierra Main Workspace flex-row */}

      {/* History Modal Overlay */}
      {showHistory && (
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
              {historySessions.length === 0 ? (
                <div className="text-gray-500 text-center mt-20">No hay sesiones guardadas aún.</div>
              ) : (
                historySessions.map((s, idx) => (
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
      )}

      {/* Confirm/Alert Modal */}
      {confirmModal.isOpen && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="bg-[#1e1e2e] border border-[#313244] rounded-2xl p-6 shadow-2xl max-w-sm w-full mx-4 relative overflow-hidden">
            <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-accent to-success"></div>
            <h3 className="text-xl font-bold text-gray-200 mb-3">{confirmModal.title}</h3>
            <p className="text-gray-400 text-sm mb-6 leading-relaxed">{confirmModal.message}</p>
            <div className="flex justify-end space-x-3">
              {confirmModal.buttons ? (
                <>
                  <button
                    onClick={() => setConfirmModal({ ...confirmModal, isOpen: false })}
                    className="px-4 py-2 rounded-lg bg-surface hover:bg-white/5 text-gray-300 transition-colors text-sm font-medium border border-white/5"
                  >
                    Cancelar
                  </button>
                  {confirmModal.buttons.map((btn, idx) => (
                    <button
                      key={idx}
                      onClick={() => {
                        if (btn.onClick) btn.onClick();
                        setConfirmModal({ ...confirmModal, isOpen: false });
                      }}
                      className={btn.className}
                    >
                      {btn.label}
                    </button>
                  ))}
                </>
              ) : (
                <>
                  {!confirmModal.isAlert && (
                    <button
                      onClick={() => setConfirmModal({ ...confirmModal, isOpen: false })}
                      className="px-4 py-2 rounded-lg bg-surface hover:bg-white/5 text-gray-300 transition-colors text-sm font-medium border border-white/5"
                    >
                      Cancelar
                    </button>
                  )}
                  <button
                    onClick={() => {
                      if (confirmModal.onConfirm) confirmModal.onConfirm();
                      setConfirmModal({ ...confirmModal, isOpen: false });
                    }}
                    className="px-4 py-2 rounded-lg bg-accent text-base hover:opacity-90 font-bold transition-shadow shadow-[0_0_15px_rgba(137,180,250,0.3)] text-sm"
                  >
                    {confirmModal.isAlert ? 'Aceptar' : 'Confirmar'}
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}

    </div>
  )
}

export default App
