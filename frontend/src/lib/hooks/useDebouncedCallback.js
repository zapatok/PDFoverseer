import { useCallback, useEffect, useRef } from "react";

/**
 * Returns a debounced version of `callback` that delays invocation until
 * `delayMs` have elapsed since the last call. Cancels in-flight timer on
 * unmount.
 *
 * Also exposes `.cancel()` to abort any pending invocation.
 */
export function useDebouncedCallback(callback, delayMs) {
  const timerRef = useRef(null);
  const callbackRef = useRef(callback);

  useEffect(() => {
    callbackRef.current = callback;
  }, [callback]);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const debounced = useCallback(
    (...args) => {
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => {
        callbackRef.current(...args);
        timerRef.current = null;
      }, delayMs);
    },
    [delayMs],
  );

  debounced.cancel = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  return debounced;
}
