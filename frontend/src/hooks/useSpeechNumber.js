import { useEffect, useRef, useState } from "react";

import { parseSpanishNumber } from "../lib/spanish-numbers";

const SR =
  typeof window !== "undefined"
    ? window.SpeechRecognition || window.webkitSpeechRecognition
    : null;

/**
 * Escucha por voz y entrega números reconocidos. Mientras `enabled` es true y
 * el navegador soporta `SpeechRecognition`, el reconocedor corre en modo
 * continuo; al pasar a false se DETIENE de verdad (spec §5.2) — no solo se
 * ignora —, así que conversar no genera marcas falsas.
 *
 * @param {object} opts
 * @param {boolean} opts.enabled - escucha cuando es true.
 * @param {(n: number) => void} opts.onNumber - número reconocido.
 * @returns {{status: "unsupported"|"listening"|"paused"|"error"}}
 */
export function useSpeechNumber({ enabled, onNumber }) {
  const [status, setStatus] = useState(SR ? "paused" : "unsupported");
  const onNumberRef = useRef(onNumber);
  onNumberRef.current = onNumber;

  useEffect(() => {
    if (!SR || !enabled) return undefined;

    const rec = new SR();
    rec.lang = "es-CL";
    rec.continuous = true;
    rec.interimResults = false;
    let stopped = false;

    rec.onresult = (e) => {
      const last = e.results[e.results.length - 1];
      const n = parseSpanishNumber(last[0].transcript);
      if (n != null) onNumberRef.current(n);
    };
    rec.onerror = (e) => {
      if (e.error !== "no-speech") setStatus("error");
    };
    rec.onend = () => {
      // el modo continuo se corta solo tras silencios; reiniciar si sigue activo
      if (!stopped) {
        try { rec.start(); } catch { /* ya estaba arrancando */ }
      }
    };

    try {
      rec.start();
      setStatus("listening");
    } catch {
      setStatus("error");
    }

    return () => {
      stopped = true;
      rec.onend = null;
      rec.stop();
      setStatus(SR ? "paused" : "unsupported");
    };
  }, [enabled]);

  return { status };
}
