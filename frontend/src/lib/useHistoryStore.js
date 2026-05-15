// Module-level cache singleton — sobrevive entre mounts. Cache por session_id.
// Spec FASE 4 §5.1.

import { useEffect, useState } from "react";
import { api } from "./api";

const _cache = new Map();
const _listeners = new Set();

export function invalidateHistory(sessionId) {
  if (sessionId) _cache.delete(sessionId);
  _listeners.forEach((l) => l());
}

export function useHistory(sessionId, n = 12) {
  const [data, setData] = useState(_cache.get(sessionId)?.data ?? null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!sessionId) {
      setData(null);
      return;
    }
    const cached = _cache.get(sessionId);
    if (cached) {
      setData(cached.data);
      return;
    }
    let cancelled = false;
    api
      .getHistory(sessionId, n)
      .then((d) => {
        if (cancelled) return;
        _cache.set(sessionId, { data: d });
        setData(d);
      })
      .catch((err) => !cancelled && setError(err));
    return () => {
      cancelled = true;
    };
  }, [sessionId, n]);

  useEffect(() => {
    const listener = () => {
      const cached = _cache.get(sessionId);
      setData(cached ? cached.data : null);
    };
    _listeners.add(listener);
    return () => _listeners.delete(listener);
  }, [sessionId]);

  return { data, error };
}
