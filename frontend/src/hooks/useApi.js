import { useEffect } from 'react';
import { API_BASE } from '../lib/constants';

export const useApi = (setters, states, refs) => {
  const {
    setPdfs,
    setIssues,
    setMetrics,
    setGlobalProg,
    setStatus,
    setFileProg,
    setLogs,
    setAiLogs,
    setScanLine,
    setConfirmModal,
    setHistorySessions,
    setShowHistory,
    setSelectedPdfFilter,
    setSelectedPdfPath,
    setSelectedIssue,
    setCorrectCurr,
    setCorrectTot
  } = setters;

  const {
    selectedPdfFilter,
    selectedPdfPath,
    selectedIssue,
    fileProg,
    issues,
    metrics,
    correctCurr,
    correctTot,
    filteredIssuesList
  } = states;

  const { preCascadeRef } = refs;

  // Global Error Handler for API
  const handleApiErr = (e, context) => {
    console.error(`API Error [${context}]:`, e);
    setConfirmModal({
      isOpen: true,
      title: 'Error de Conexión',
      message: `No se pudo completar la operación (${context}). El servidor backend podría estar inactivo.`,
      isAlert: true,
      onConfirm: null
    });
  };

  // Recover state F5
  useEffect(() => {
    fetch(`${API_BASE}/state`)
      .then(res => res.json())
      .then(data => {
        if (data.running || (data.pdf_list && data.pdf_list.length > 0)) {
          setPdfs(data.pdf_list);
          setIssues(data.issues || []);
          setMetrics(data.metrics || { docs: 0, complete: 0, incomplete: 0, inferred: 0 });
          setGlobalProg(data.globalProg || { done: 0, total: 0, elapsed: 0, eta: 0, paused: false });
          if (data.running) setStatus('running');
        }
      })
      .catch((e) => console.warn('Could not recover state (normal during cold boot).', e));
  }, []);

  const handleAddFolder = async () => {
    try {
      const res = await fetch(`${API_BASE}/add_folder`);
      const data = await res.json();
      if (data.success && data.pdfs) {
        setPdfs(data.pdfs);
        setStatus('idle');
      }
    } catch (e) { handleApiErr(e, 'Añadir Carpeta'); }
  };

  const handleAddFiles = async () => {
    try {
      const res = await fetch(`${API_BASE}/add_files`);
      const data = await res.json();
      if (data.success && data.pdfs) {
        setPdfs(data.pdfs);
        setStatus('idle');
      }
    } catch (e) { handleApiErr(e, 'Añadir Archivos'); }
  };

  const handleRemovePdf = () => {
    if (!selectedPdfPath) return;
    setConfirmModal({
      isOpen: true,
      title: 'Remover PDF',
      message: `¿Seguro que deseas remover "${selectedPdfFilter}" de la lista?`,
      isAlert: false,
      onConfirm: async () => {
        try {
          const res = await fetch(`${API_BASE}/remove_pdf?pdf_path=${encodeURIComponent(selectedPdfPath)}`, { method: 'POST' });
          const data = await res.json();
          if (data.success) {
            setPdfs(data.pdfs);
            if (selectedPdfFilter === fileProg.filename) setFileProg({ done: 0, total: 0, filename: '' });
            setSelectedPdfFilter('');
            setSelectedPdfPath('');
          }
        } catch (e) { handleApiErr(e, 'Remover PDF'); }
      }
    });
  };

  const handleNewSession = () => {
    setConfirmModal({
      isOpen: true,
      title: 'Nueva Sesión',
      message: '¿Seguro que deseas iniciar una nueva sesión? Se borrará el progreso actual no guardado.',
      isAlert: false,
      onConfirm: async () => {
        try {
          await fetch(`${API_BASE}/reset`, { method: 'POST' });
          setPdfs([]);
          setIssues([]);
          setLogs([]);
          setAiLogs([]);
          setScanLine(null);
          setMetrics({ docs: 0, complete: 0, incomplete: 0, inferred: 0 });
          setGlobalProg({ done: 0, total: 0, elapsed: 0, eta: 0, paused: false });
          setFileProg({ done: 0, total: 0, filename: '' });
          setStatus('idle');
          setSelectedPdfFilter('');
          setSelectedPdfPath('');
          setSelectedIssue(null);
        } catch (e) { handleApiErr(e, 'Nueva Sesión'); }
      }
    });
  };

  const handleSaveSession = async () => {
    try {
      const res = await fetch(`${API_BASE}/save_session`, { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        setConfirmModal({
          isOpen: true,
          title: 'Sesión Guardada',
          message: 'Sesión guardada en el historial permanentemente.',
          isAlert: true,
          onConfirm: null
        });
      }
    } catch (e) { handleApiErr(e, 'Guardar Sesión'); }
  };

  const handleViewHistory = async () => {
    try {
      const res = await fetch(`${API_BASE}/sessions`);
      const data = await res.json();
      setHistorySessions(data.sessions || []);
      setShowHistory(true);
    } catch (e) { handleApiErr(e, 'Ver Historial'); }
  };

  const handleDeleteSession = (timestamp) => {
    setConfirmModal({
      isOpen: true,
      title: 'Eliminar Sesión',
      message: '¿Seguro que deseas eliminar el registro de esta sesión del historial permanentemente?',
      isAlert: false,
      onConfirm: async () => {
        try {
          const res = await fetch(`${API_BASE}/delete_session`, {
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
        } catch (e) { handleApiErr(e, 'Eliminar Sesión'); }
      }
    });
  };

  const handleOpenNativePdf = async () => {
    if (!selectedIssue) return;
    try {
      await fetch(`${API_BASE}/open_pdf?pdf_path=${encodeURIComponent(selectedIssue.pdf_path)}&page=${selectedIssue.page}`);
    } catch (e) { handleApiErr(e, 'Abrir visor nativo'); }
  };

  const handleOpenAnyPdf = async (path) => {
    try {
      await fetch(`${API_BASE}/open_pdf?pdf_path=${encodeURIComponent(path)}&page=1`);
    } catch (e) { handleApiErr(e, 'Abrir visor de archivo'); }
  };

  const handleStart = async (startIndex = 0) => {
    setLogs([]);
    setAiLogs([]);
    setScanLine(null);
    setStatus('running');
    setGlobalProg(prev => ({ ...prev, paused: false }));
    setFileProg({ done: 0, total: 0, filename: '' });
    try {
      await fetch(`${API_BASE}/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ start_index: startIndex })
      });
    } catch (e) { handleApiErr(e, 'Iniciar Lote'); }
  };

  const handlePause = async () => {
    setGlobalProg(prev => ({ ...prev, paused: true }));
    try {
      await fetch(`${API_BASE}/pause`, { method: 'POST' });
    } catch (e) { handleApiErr(e, 'Pausar'); }
  };

  const handleResume = async () => {
    setGlobalProg(prev => ({ ...prev, paused: false }));
    try {
      await fetch(`${API_BASE}/resume`, { method: 'POST' });
    } catch (e) { handleApiErr(e, 'Reanudar'); }
  };

  const handleStop = async () => {
    setStatus('idle');
    try {
      await fetch(`${API_BASE}/stop`, { method: 'POST' });
    } catch (e) { handleApiErr(e, 'Detener'); }
  };

  const handleSkip = async () => {
    try {
      await fetch(`${API_BASE}/skip`, { method: 'POST' });
    } catch (e) { handleApiErr(e, 'Saltar'); }
  };

  const _getNextIssue = (direction) => {
    if (!selectedIssue || filteredIssuesList.length === 0) return null;
    const currentIndex = filteredIssuesList.findIndex(i => i.id === selectedIssue.id);
    let nextIndex = currentIndex + direction;

    if (nextIndex >= filteredIssuesList.length) nextIndex = 0;
    if (nextIndex < 0) nextIndex = filteredIssuesList.length - 1;
    if (filteredIssuesList.length === 1 || nextIndex === currentIndex) return null;

    return filteredIssuesList[nextIndex];
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
        setConfirmModal({
          isOpen: true,
          title: 'Extracción Fallida',
          message: "No se pudo extraer el valor inferido 'X/Y' automáticamente. Escribe los números.",
          isAlert: true,
          onConfirm: null
        });
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
      preCascadeRef.current = {
        docs: metrics?.docs || 0,
        issueCount: issues.filter(i => i.pdf_path === selectedIssue.pdf_path).length,
      };
      await fetch(`${API_BASE}/correct`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pdf_path: selectedIssue.pdf_path,
          page: selectedIssue.page,
          correct_curr: curr,
          correct_tot: tot
        })
      });
      setIssues(prev => prev.filter(i => i.id !== currentId));

      setSelectedIssue(nextIssue);
      setCorrectCurr('');
      setCorrectTot('');
    } catch (e) { handleApiErr(e, 'Validar Corrección'); }
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
      await fetch(`${API_BASE}/exclude`, {
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
    } catch (e) { handleApiErr(e, 'Excluir'); }
  };

  const navigateIssue = (direction) => {
    if (!selectedIssue || filteredIssuesList.length === 0) return;
    const currentIndex = filteredIssuesList.findIndex(i => i.id === selectedIssue.id);
    let nextIndex = currentIndex + direction;
    if (nextIndex < 0) nextIndex = filteredIssuesList.length - 1;
    if (nextIndex >= filteredIssuesList.length) nextIndex = 0;
    setSelectedIssue(filteredIssuesList[nextIndex]);
    setCorrectCurr('');
    setCorrectTot('');
  };

  return {
    handleAddFolder,
    handleAddFiles,
    handleRemovePdf,
    handleNewSession,
    handleSaveSession,
    handleViewHistory,
    handleDeleteSession,
    handleOpenNativePdf,
    handleOpenAnyPdf,
    handleStart,
    handlePause,
    handleResume,
    handleStop,
    handleSkip,
    handleCorrect,
    handleExclude,
    navigateIssue,
  };
};
