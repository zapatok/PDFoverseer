import { useCallback, useEffect, useRef } from "react";

/**
 * Returns a debounced version of `callback` that delays invocation until
 * `delayMs` have elapsed since the last call. Cancels in-flight timer on
 * unmount.
 *
 * Also exposes `.cancel()` to abort any pending invocation.
 *
 * FOOTGUN — when the timer fires it invokes the LATEST render's callback, not
 * the one current when the call was scheduled. Anything identifying the save
 * TARGET (hospital/sigla/filename…) must therefore travel as call-time args
 * (captured at schedule time), never be read from the callback's closure — a
 * re-render with new props inside the delay window misdirects the save
 * (bitten twice: OverridePanel, NotePanel). Alternative mitigation: cancel +
 * flush synchronously from an identity-keyed effect cleanup (WorkerCountViewer).
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
