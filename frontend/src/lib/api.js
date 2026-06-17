const BASE = "http://127.0.0.1:8000/api";

async function jsonOrThrow(res) {
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json();
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
    const r = await fetch(
      `${BASE}/sessions/${sessionId}/cells/${hospital}/${sigla}/override`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        signal: opts.signal,
      }
    );
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  patchPerFileOverride: async (sessionId, hospital, sigla, filename, count, opts = {}) => {
    const r = await fetch(
      `${BASE}/sessions/${sessionId}/cells/${hospital}/${sigla}/files/${encodeURIComponent(filename)}/override`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ count }),
        signal: opts.signal,
      }
    );
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  patchWorkerCount: async (sessionId, hospital, sigla, patch, opts = {}) => {
    const r = await fetch(
      `${BASE}/sessions/${sessionId}/cells/${hospital}/${sigla}/worker-count`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
        signal: opts.signal,
      }
    );
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  patchNote: async (sessionId, hospital, sigla, patch, opts = {}) => {
    const r = await fetch(
      `${BASE}/sessions/${sessionId}/cells/${hospital}/${sigla}/note`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(patch),
        signal: opts.signal,
      }
    );
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },

  patchConfirm: async (sessionId, hospital, sigla, confirmed, opts = {}) => {
    const r = await fetch(
      `${BASE}/sessions/${sessionId}/cells/${hospital}/${sigla}/confirm`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirmed }),
        signal: opts.signal,
      }
    );
    if (!r.ok) throw new Error(await r.text());
    return r.json();
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
  scanFileOcr: (sessionId, hospital, sigla, filename) =>
    fetch(
      `${BASE}/sessions/${sessionId}/cells/${hospital}/${sigla}/files/${encodeURIComponent(filename)}/scan-ocr`,
      { method: "POST" },
    ).then(jsonOrThrow),

  // Incr 2 — apply ratio N treatment to all Pendiente files in a cell.
  // n=1 implements "Apply R1" (each page = one document).
  applyRatio: (sessionId, hospital, sigla, n) =>
    fetch(`${BASE}/sessions/${sessionId}/cells/${hospital}/${sigla}/apply-ratio`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ n }),
    }).then(jsonOrThrow),

  // E5 — clear near-match suspects for a cell. Omit `entry` = clear all;
  // pass { pdf_name, page_index } to drop a single candidate.
  clearNearMatches: (sessionId, hospital, sigla, entry) =>
    fetch(
      `${BASE}/sessions/${sessionId}/cells/${hospital}/${sigla}/near-matches/clear`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(entry ?? {}),
      },
    ).then(jsonOrThrow),

  getHistory: async (sessionId, n = 12) => {
    const r = await fetch(`${BASE}/sessions/${sessionId}/history?n=${n}`);
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
};
