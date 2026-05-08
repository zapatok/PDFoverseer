import { useEffect, useRef } from 'react';
import { WS_BASE } from '../lib/constants';
import { useStore } from '../store/useStore';

export const useWebSocket = (preCascadeRef) => {
  const ws = useRef(null);
  const sessionId = useStore(s => s.sessionId);

  useEffect(() => {
    if (!sessionId) return;
    ws.current = new WebSocket(`${WS_BASE}?session_id=${sessionId}`);

    ws.current.onmessage = (event) => {
      let data;
      try {
        data = JSON.parse(event.data);
      } catch (e) {
        console.error('WebSocket: invalid JSON received', e);
        return;
      }
      const { type, payload } = data;
      const store = useStore.getState();

      if (type === 'log') {
        if (payload.level === 'ai' || payload.level === 'ai_inf') {
          store.setAiLogs(prev => [...prev.slice(-199), payload]);
        } else if (payload.level === 'page_ok' || payload.level === 'page_warn') {
          store.setScanLine({ msg: payload.msg, level: payload.level });
        } else {
          if (payload.level === 'file_hdr') store.setScanLine(null);
          store.setLogs(prev => [...prev.slice(-199), payload]);
        }
      } else if (type === 'status_update') {
        store.setPdfs(prev => {
          const arr = [...prev];
          if (arr[payload.idx]) arr[payload.idx].status = payload.status;
          return arr;
        });
      } else if (type === 'global_progress') {
        store.setGlobalProg(prev => ({ ...prev, ...payload }));
      } else if (type === 'file_progress') {
        store.setFileProg(payload);
      } else if (type === 'new_issue') {
        store.setIssues(prev => [...prev, payload]);
      } else if (type === 'issues_refresh') {
        store.setIssues(prev => {
          if (!payload.pdf_path) return prev;
          const targetPdf = payload.pdf_path;
          const newList = [...prev.filter(i => i.pdf_path !== targetPdf), ...(payload.issues || [])];
          if (preCascadeRef.current) {
            preCascadeRef.current.newIssueCount = (payload.issues || []).length;
          }
          return newList;
        });
      } else if (type === 'metrics') {
        if (preCascadeRef.current && preCascadeRef.current.newIssueCount !== undefined) {
          const prev_snap = preCascadeRef.current;
          const parts = [];
          const docDelta = (payload.docs || 0) - prev_snap.docs;
          if (docDelta !== 0) parts.push(`DOC ${prev_snap.docs}→${payload.docs} (${docDelta > 0 ? '+' : ''}${docDelta})`);
          const issuesDelta = prev_snap.issueCount - prev_snap.newIssueCount;
          if (issuesDelta > 0) parts.push(`${issuesDelta} issues resueltos`);
          if (issuesDelta < 0) parts.push(`${Math.abs(issuesDelta)} issues nuevos`);
          if (parts.length > 0) {
            store.setCascadeToast(parts.join(', '));
            setTimeout(() => useStore.getState().setCascadeToast(null), 5000);
          }
          preCascadeRef.current = null;
        }
        store.setMetrics(payload);
      } else if (type === 'process_finished') {
        store.setStatus('idle');
        store.setScanLine(null);
      }
    };

    ws.current.onclose = () => {
      useStore.getState().setConfirmModal({
        isOpen: true,
        title: 'Conexión Perdida',
        message: 'Se perdió la conexión con el motor (Backend CAÍDO). Por favor verifica la terminal y recarga la página.',
        isAlert: true,
        onConfirm: null
      });
      useStore.getState().setStatus('idle');
    };

    ws.current.onerror = () => {
      useStore.getState().setStatus('idle');
    };

    return () => {
      if (ws.current) {
        ws.current.onclose = null;
        ws.current.onerror = null;
        ws.current.close();
      }
    };
  }, [sessionId]);

  return ws;
};
