import { useEffect } from 'react';
import { API_BASE } from '../lib/constants';
import { useStore } from '../store/useStore';

export const useApi = (refs) => {
  const { preCascadeRef } = refs;

  const authFetch = async (url, options = {}) => {
    const sid = useStore.getState().sessionId;
    const headers = { ...options.headers, 'x-session-id': sid };
    return fetch(url, { ...options, headers });
  };

  const handleApiErr = (e, context) => {
    console.error(`API Error [${context}]:`, e);
    const msg = e.message || 'Error desconocido';
    useStore.getState().setConfirmModal({
      isOpen: true,
      title: 'Error de Conexión',
      message: `No se pudo completar la operación (${context}). Motivo: ${msg}. El servidor backend podría estar inactivo o haber fallado.`,
      isAlert: true,
      onConfirm: null
    });
  };

  useEffect(() => {
    authFetch(`${API_BASE}/state`)
      .then(res => res.json())
      .then(data => {
        const store = useStore.getState();
        if (data.running || (data.pdf_list && data.pdf_list.length > 0)) {
          store.setPdfs(data.pdf_list);
          store.setIssues(data.issues || []);
          store.setMetrics(data.metrics || { docs: 0, complete: 0, incomplete: 0, inferred: 0 });
          store.setGlobalProg(data.globalProg || { done: 0, total: 0, elapsed: 0, eta: 0, paused: false });
          if (data.running) store.setStatus('running');
        }
      })
      .catch((e) => console.warn('Could not recover state (normal during cold boot).', e));
  }, []);

  const handleAddFolder = async () => {
    try {
      const res = await authFetch(`${API_BASE}/add_folder`);
      const data = await res.json();
      if (data.success && data.pdfs) {
        useStore.getState().setPdfs(data.pdfs);
        useStore.getState().setStatus('idle');
      }
    } catch (e) { handleApiErr(e, 'Añadir Carpeta'); }
  };

  const handleAddFiles = async () => {
    try {
      const res = await authFetch(`${API_BASE}/add_files`);
      const data = await res.json();
      if (data.success && data.pdfs) {
        useStore.getState().setPdfs(data.pdfs);
        useStore.getState().setStatus('idle');
      }
    } catch (e) { handleApiErr(e, 'Añadir Archivos'); }
  };

  const handleRemovePdf = () => {
    const store = useStore.getState();
    const { selectedPdfPath, selectedPdfFilter, fileProg } = store;
    if (!selectedPdfPath) return;
    store.setConfirmModal({
      isOpen: true,
      title: 'Remover PDF',
      message: `¿Seguro que deseas remover "${selectedPdfFilter}" de la lista?`,
      isAlert: false,
      onConfirm: async () => {
        try {
          const res = await authFetch(`${API_BASE}/remove_pdf?pdf_path=${encodeURIComponent(selectedPdfPath)}`, { method: 'POST' });
          const data = await res.json();
          if (data.success) {
            const currentStore = useStore.getState();
            currentStore.setPdfs(data.pdfs);
            if (selectedPdfFilter === fileProg.filename) currentStore.setFileProg({ done: 0, total: 0, filename: '' });
            currentStore.setSelectedPdfFilter('');
            currentStore.setSelectedPdfPath('');
          }
        } catch (e) { handleApiErr(e, 'Remover PDF'); }
      }
    });
  };

  const handleNewSession = () => {
    useStore.getState().setConfirmModal({
      isOpen: true,
      title: 'Nueva Sesión',
      message: '¿Seguro que deseas iniciar una nueva sesión? Se borrará el progreso actual no guardado.',
      isAlert: false,
      onConfirm: async () => {
        try {
          await authFetch(`${API_BASE}/reset`, { method: 'POST' });
          const store = useStore.getState();
          // Reset the session ID to tear down backend dependencies
          store.setSessionId(crypto.randomUUID());
          store.setPdfs([]);
          store.setIssues([]);
          store.setLogs([]);
          store.setAiLogs([]);
          store.setScanLine(null);
          store.setMetrics({ docs: 0, complete: 0, incomplete: 0, inferred: 0 });
          store.setGlobalProg({ done: 0, total: 0, elapsed: 0, eta: 0, paused: false });
          store.setFileProg({ done: 0, total: 0, filename: '' });
          store.setStatus('idle');
          store.setSelectedPdfFilter('');
          store.setSelectedPdfPath('');
          store.setSelectedIssue(null);
        } catch (e) { handleApiErr(e, 'Nueva Sesión'); }
      }
    });
  };

  const handleSaveSession = async () => {
    try {
      const res = await authFetch(`${API_BASE}/save_session`, { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        useStore.getState().setConfirmModal({
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
      const res = await authFetch(`${API_BASE}/sessions`);
      const data = await res.json();
      const store = useStore.getState();
      store.setHistorySessions(data.sessions || []);
      store.setShowHistory(true);
    } catch (e) { handleApiErr(e, 'Ver Historial'); }
  };

  const handleDeleteSession = (timestamp) => {
    useStore.getState().setConfirmModal({
      isOpen: true,
      title: 'Eliminar Sesión',
      message: '¿Seguro que deseas eliminar el registro de esta sesión del historial permanentemente?',
      isAlert: false,
      onConfirm: async () => {
        try {
          const res = await authFetch(`${API_BASE}/delete_session`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ timestamp })
          });
          const data = await res.json();
          if (data.success) {
            useStore.getState().setHistorySessions(prev => prev.filter(s => s.timestamp !== timestamp));
          } else {
            console.error('Error al eliminar: ' + (data.error || 'Desconocido'));
          }
        } catch (e) { handleApiErr(e, 'Eliminar Sesión'); }
      }
    });
  };

  const handleOpenNativePdf = async () => {
    const { selectedIssue } = useStore.getState();
    if (!selectedIssue) return;
    try {
      await authFetch(`${API_BASE}/open_pdf?pdf_path=${encodeURIComponent(selectedIssue.pdf_path)}&page=${selectedIssue.page}`);
    } catch (e) { handleApiErr(e, 'Abrir visor nativo'); }
  };

  const handleOpenAnyPdf = async (path) => {
    try {
      await authFetch(`${API_BASE}/open_pdf?pdf_path=${encodeURIComponent(path)}&page=1`);
    } catch (e) { handleApiErr(e, 'Abrir visor de archivo'); }
  };

  const handleStart = async (startIndex = 0) => {
    const store = useStore.getState();
    store.setLogs([]);
    store.setAiLogs([]);
    store.setScanLine(null);
    store.setStatus('running');
    store.setGlobalProg(prev => ({ ...prev, paused: false }));
    store.setFileProg({ done: 0, total: 0, filename: '' });
    try {
      await authFetch(`${API_BASE}/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ start_index: startIndex })
      });
    } catch (e) { handleApiErr(e, 'Iniciar Lote'); }
  };

  const handlePause = async () => {
    const store = useStore.getState();
    store.setGlobalProg(prev => ({ ...prev, paused: true }));
    try {
      await authFetch(`${API_BASE}/pause`, { method: 'POST' });
    } catch (e) { handleApiErr(e, 'Pausar'); }
  };

  const handleResume = async () => {
    const store = useStore.getState();
    store.setGlobalProg(prev => ({ ...prev, paused: false }));
    try {
      await authFetch(`${API_BASE}/resume`, { method: 'POST' });
    } catch (e) { handleApiErr(e, 'Reanudar'); }
  };

  const handleStop = async () => {
    useStore.getState().setStatus('idle');
    try {
      await authFetch(`${API_BASE}/stop`, { method: 'POST' });
    } catch (e) { handleApiErr(e, 'Detener'); }
  };

  const handleSkip = async () => {
    try {
      await authFetch(`${API_BASE}/skip`, { method: 'POST' });
    } catch (e) { handleApiErr(e, 'Saltar'); }
  };

  const _getFilteredIssues = (store) => {
    return (store.selectedPdfPath ? store.issues.filter(i => i.pdf_path === store.selectedPdfPath) : store.issues)
      .filter(i => store.showAllIssues || (i.impact || 'internal') !== 'internal')
      .sort((a, b) => {
        const p1 = a.impact === 'ph5b' ? 1 : a.impact === 'ph5-merge' ? 2 : a.impact === 'boundary' ? 3 : a.impact === 'sequence' ? 4 : a.impact === 'orphan' ? 5 : 6;
        const p2 = b.impact === 'ph5b' ? 1 : b.impact === 'ph5-merge' ? 2 : b.impact === 'boundary' ? 3 : b.impact === 'sequence' ? 4 : b.impact === 'orphan' ? 5 : 6;
        return p1 - p2;
      });
  };

  const _getNextIssue = (direction, store) => {
    const filteredIssuesList = _getFilteredIssues(store);
    if (!store.selectedIssue || filteredIssuesList.length === 0) return null;
    const currentIndex = filteredIssuesList.findIndex(i => i.id === store.selectedIssue.id);
    let nextIndex = currentIndex + direction;

    if (nextIndex >= filteredIssuesList.length) nextIndex = 0;
    if (nextIndex < 0) nextIndex = filteredIssuesList.length - 1;
    if (filteredIssuesList.length === 1 || nextIndex === currentIndex) return null;

    return filteredIssuesList[nextIndex];
  };

  const handleCorrect = async () => {
    const store = useStore.getState();
    const { selectedIssue, correctCurr, correctTot } = store;
    if (!selectedIssue) return;
    
    const currentId = selectedIssue.id;
    const nextIssue = _getNextIssue(1, store);

    let finalCurr = correctCurr;
    let finalTot = correctTot;

    if (!finalCurr || !finalTot) {
      const match = selectedIssue.detail.match(/(\d+)\s*[/de]+\s*(\d+)/i);
      if (match) {
        if (!finalCurr) finalCurr = match[1];
        if (!finalTot) finalTot = match[2];
      } else {
        store.setConfirmModal({
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
      store.setConfirmModal({
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
        docs: store.metrics?.docs || 0,
        issueCount: store.issues.filter(i => i.pdf_path === selectedIssue.pdf_path).length,
      };
      await authFetch(`${API_BASE}/correct`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pdf_path: selectedIssue.pdf_path,
          page: selectedIssue.page,
          correct_curr: curr,
          correct_tot: tot
        })
      });
      const updatedStore = useStore.getState();
      updatedStore.setIssues(prev => prev.filter(i => i.id !== currentId));
      updatedStore.setSelectedIssue(nextIssue);
      updatedStore.setCorrectCurr('');
      updatedStore.setCorrectTot('');
    } catch (e) { handleApiErr(e, 'Validar Corrección'); }
  };

  const handleExclude = async () => {
    const store = useStore.getState();
    const { selectedIssue, issues } = store;
    if (!selectedIssue) return;
    
    const currentId = selectedIssue.id;
    const currentIndex = issues.findIndex(i => i.id === currentId);
    let nextIssue = null;
    if (issues.length > 1) {
      nextIssue = issues[currentIndex + 1] || issues[currentIndex - 1];
    }

    try {
      await authFetch(`${API_BASE}/exclude`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pdf_path: selectedIssue.pdf_path,
          page: selectedIssue.page,
        })
      });
      const updatedStore = useStore.getState();
      updatedStore.setIssues(prev => prev.filter(i => i.id !== currentId));
      updatedStore.setSelectedIssue(nextIssue);
      updatedStore.setCorrectCurr('');
      updatedStore.setCorrectTot('');
    } catch (e) { handleApiErr(e, 'Excluir'); }
  };

  const navigateIssue = (direction) => {
    const store = useStore.getState();
    const filteredIssuesList = _getFilteredIssues(store);
    if (!store.selectedIssue || filteredIssuesList.length === 0) return;
    const currentIndex = filteredIssuesList.findIndex(i => i.id === store.selectedIssue.id);
    let nextIndex = currentIndex + direction;
    if (nextIndex < 0) nextIndex = filteredIssuesList.length - 1;
    if (nextIndex >= filteredIssuesList.length) nextIndex = 0;
    store.setSelectedIssue(filteredIssuesList[nextIndex]);
    store.setCorrectCurr('');
    store.setCorrectTot('');
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
