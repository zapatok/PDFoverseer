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
};
