import { API_BASE } from "./config";
const BASE = API_BASE;

async function jsonOrThrow(res) {
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json();
}

async function jsonOrThrowStructured(res) {
  if (res.ok) return res.json();
  let body = null;
  try {
    body = await res.json();
  } catch {
    /* non-JSON error body */
  }
  const err = new Error(body?.detail || res.statusText);
  err.status = res.status;
  err.body = body; // {detail, hospital, sigla, lock_holder} on a 409
  throw err;
}

export const api = {
  listMonths: () => fetch(`${BASE}/months`).then(jsonOrThrow),
  getMonth: (sessionId) => fetch(`${BASE}/months/${sessionId}`).then(jsonOrThrow),
  createSession: (year, month) =>
    fetch(`${BASE}/sessions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ year, month }),
    }).then(jsonOrThrow),
  getSession: (sessionId) =>
    fetch(`${BASE}/sessions/${sessionId}`).then(jsonOrThrow),
  scanSession: (sessionId, scope = "all") =>
    fetch(`${BASE}/sessions/${sessionId}/scan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scope }),
    }).then(jsonOrThrow),
  generateOutput: (sessionId) =>
    fetch(`${BASE}/sessions/${sessionId}/output`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    }).then(jsonOrThrow),

  scanOcr: (sessionId, cells) =>
    fetch(`${BASE}/sessions/${sessionId}/scan-ocr`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cells }),
    }).then(jsonOrThrow),

  cancelScan: (sessionId) =>
    fetch(`${BASE}/sessions/${sessionId}/cancel`, {
      method: "POST",
    }).then(jsonOrThrow),

  patchOverride: async (sessionId, hospital, sigla, value, opts = {}) => {
    const body = { value };
    if (opts.manual) body.manual = true;
    body.participant_id = opts.participantId ?? null;
    const r = await fetch(
      `${BASE}/sessions/${sessionId}/cells/${hospital}/${sigla}/override`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: opts.signal,
      }
    );
    return jsonOrThrowStructured(r);
  },

  patchPerFileOverride: async (sessionId, hospital, sigla, filename, count, opts = {}) => {
    const r = await fetch(
      `${BASE}/sessions/${sessionId}/cells/${hospital}/${sigla}/files/${encodeURIComponent(filename)}/override`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ count, participant_id: opts.participantId ?? null }),
        signal: opts.signal,
      }
    );
    return jsonOrThrowStructured(r);
  },

  patchWorkerCount: async (sessionId, hospital, sigla, patch, opts = {}) => {
    const body = { ...patch, participant_id: opts.participantId ?? null };
    const r = await fetch(
      `${BASE}/sessions/${sessionId}/cells/${hospital}/${sigla}/worker-count`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: opts.signal,
      }
    );
    return jsonOrThrowStructured(r);
  },

  patchNote: async (sessionId, hospital, sigla, patch, opts = {}) => {
    const body = { ...patch, participant_id: opts.participantId ?? null };
    const r = await fetch(
      `${BASE}/sessions/${sessionId}/cells/${hospital}/${sigla}/note`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: opts.signal,
      }
    );
    return jsonOrThrowStructured(r);
  },

  patchConfirm: async (sessionId, hospital, sigla, confirmed, opts = {}) => {
    const r = await fetch(
      `${BASE}/sessions/${sessionId}/cells/${hospital}/${sigla}/confirm`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirmed, participant_id: opts.participantId ?? null }),
        signal: opts.signal,
      }
    );
    return jsonOrThrowStructured(r);
  },

  getCellFiles: (sessionId, hospital, sigla) =>
    fetch(`${BASE}/sessions/${sessionId}/cells/${hospital}/${sigla}/files`).then(jsonOrThrow),

  cellPdfUrl: (sessionId, hospital, sigla, index = 0) =>
    `${BASE}/sessions/${sessionId}/cells/${hospital}/${sigla}/pdf?index=${index}`,

  // G5 — open the generated RESUMEN xlsx from the home; list all generated files.
  outputUrl: (sessionId) => `${BASE}/sessions/${sessionId}/output`,
  listOutputs: () => fetch(`${BASE}/outputs`).then(jsonOrThrow),

  // rev-2 #5 — what the sigla's OCR looks for (for the method (i) tooltip).
  getScanInfo: (sigla) => fetch(`${BASE}/siglas/${sigla}/scan-info`).then(jsonOrThrow),

  // rev-2 #1 — OCR-scan a single file of a cell (progress streams over the WS).
  // B1: carries participant_id so the backend can 409 a cell another participant
  // holds; jsonOrThrowStructured preserves the 409 body (lock_holder) for the store.
  scanFileOcr: (sessionId, hospital, sigla, filename, participantId) =>
    fetch(
      `${BASE}/sessions/${sessionId}/cells/${hospital}/${sigla}/files/${encodeURIComponent(filename)}/scan-ocr`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ participant_id: participantId ?? null }),
      },
    ).then(jsonOrThrowStructured),

  // Incr 2 — apply ratio N treatment to all Pendiente files in a cell.
  // n=1 implements "Apply R1" (each page = one document).
  applyRatio: (sessionId, hospital, sigla, n, participantId) =>
    fetch(`${BASE}/sessions/${sessionId}/cells/${hospital}/${sigla}/apply-ratio`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ n, participant_id: participantId ?? null }),
    }).then(jsonOrThrowStructured),

  // E5 — clear near-match suspects for a cell. Omit `entry` = clear all;
  // pass { pdf_name, page_index } to drop a single candidate.
  clearNearMatches: (sessionId, hospital, sigla, entry, participantId) =>
    fetch(
      `${BASE}/sessions/${sessionId}/cells/${hospital}/${sigla}/near-matches/clear`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...(entry ?? {}), participant_id: participantId ?? null }),
      },
    ).then(jsonOrThrowStructured),

  getHistory: async (sessionId, n = 12) => {
    const r = await fetch(`${BASE}/sessions/${sessionId}/history?n=${n}`);
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  // Incr J — reorg ops + manifest export.
  createReorgOp: (sessionId, op) =>
    fetch(`${BASE}/sessions/${sessionId}/reorg/ops`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(op),
    }).then(jsonOrThrow),

  deleteReorgOp: (sessionId, opId) =>
    fetch(`${BASE}/sessions/${sessionId}/reorg/ops/${opId}`, { method: "DELETE" }).then(jsonOrThrow),

  exportManifest: (sessionId) =>
    fetch(`${BASE}/sessions/${sessionId}/reorg/export`, { method: "POST" }).then(jsonOrThrow),

  // Multiplayer M2 — presence endpoints.
  presenceHeartbeat: (sessionId, body) =>
    fetch(`${BASE}/sessions/${sessionId}/presence/heartbeat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(jsonOrThrow),

  presenceFocus: (sessionId, body) =>
    fetch(`${BASE}/sessions/${sessionId}/presence/focus`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(jsonOrThrow),

  presenceLeave: (sessionId, body) =>
    fetch(`${BASE}/sessions/${sessionId}/presence/leave`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(jsonOrThrow),

  /** Fire-and-forget leave via sendBeacon (safe to call on unload). */
  beaconLeave: (sessionId, body) => {
    if (typeof navigator !== "undefined" && navigator.sendBeacon) {
      navigator.sendBeacon(
        `${BASE}/sessions/${sessionId}/presence/leave`,
        new Blob([JSON.stringify(body)], { type: "application/json" })
      );
    }
  },
};
