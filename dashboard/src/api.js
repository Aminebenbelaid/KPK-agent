const BASE = '';

export async function fetchStats() {
  const res = await fetch(`${BASE}/api/applications/stats/summary`);
  return res.json();
}

export async function fetchJobs({ limit = 20, offset = 0, sort = 'match_score_desc', source, remote_type, min_match, search, status } = {}) {
  const params = new URLSearchParams({ limit, offset, sort });
  if (source) params.set('source', source);
  if (remote_type) params.set('remote_type', remote_type);
  if (min_match !== undefined && min_match !== '' && min_match !== null) params.set('min_match', min_match);
  if (search) params.set('search', search);
  if (status) params.set('status', status);
  const res = await fetch(`${BASE}/api/jobs?${params}`);
  return res.json();
}

export async function fetchJob(jobId) {
  const res = await fetch(`${BASE}/api/jobs/${encodeURIComponent(jobId)}`);
  if (!res.ok) return null;
  return res.json();
}

export async function deleteAllJobs(source) {
  const url = source ? `${BASE}/api/jobs?source=${encodeURIComponent(source)}` : `${BASE}/api/jobs`;
  const res = await fetch(url, { method: 'DELETE' });
  if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || `HTTP ${res.status}`); }
  return res.json();
}

export async function updateApplication(applicationId, data) {
  const res = await fetch(`${BASE}/api/applications/${applicationId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return res.json();
}

export async function fetchHealth() {
  const res = await fetch(`${BASE}/health`);
  return res.json();
}

export async function triggerScrape({ scrapers, query, location, parallel = true }) {
  const res = await fetch(`${BASE}/api/scrape`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scrapers, query: query || null, location: location || null, parallel }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function getScrapeStatus(taskId) {
  const res = await fetch(`${BASE}/api/scrape/${taskId}`);
  return res.json();
}

export async function listScrapes() {
  const res = await fetch(`${BASE}/api/scrape`);
  return res.json();
}

export async function fetchSearchHistory(limit = 10) {
  const res = await fetch(`${BASE}/api/search-history?limit=${limit}`);
  return res.json();
}

export async function fetchProfile() {
  const res = await fetch(`${BASE}/api/profile`);
  return res.json();
}

export async function saveProfile(profile) {
  const res = await fetch(`${BASE}/api/profile`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(profile),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function triggerScoring({ only_unscored = false, use_llm = true } = {}) {
  const res = await fetch(`${BASE}/api/score`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ only_unscored, use_llm }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function getScoringStatus(taskId) {
  const res = await fetch(`${BASE}/api/score/${taskId}`);
  return res.json();
}

export async function fetchScoringOverview() {
  const res = await fetch(`${BASE}/api/score`);
  return res.json();
}

// ── Experience base ──
export async function listExperiences() {
  const res = await fetch(`${BASE}/api/experiences`);
  return res.json();
}

export async function createExperience(exp) {
  const res = await fetch(`${BASE}/api/experiences`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(exp),
  });
  if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || `HTTP ${res.status}`); }
  return res.json();
}

export async function updateExperience(id, patch) {
  const res = await fetch(`${BASE}/api/experiences/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  });
  if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || `HTTP ${res.status}`); }
  return res.json();
}

export async function deleteExperience(id) {
  const res = await fetch(`${BASE}/api/experiences/${id}`, { method: 'DELETE' });
  return res.json();
}

export async function parseCvText(text) {
  const res = await fetch(`${BASE}/api/cv/parse-text`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || `HTTP ${res.status}`); }
  return res.json();
}

export async function parseCvFile(file) {
  const fd = new FormData();
  fd.append('file', file);
  const res = await fetch(`${BASE}/api/cv/parse-file`, { method: 'POST', body: fd });
  if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || `HTTP ${res.status}`); }
  return res.json();
}

export async function confirmCv(experiences, replace_existing = false) {
  const res = await fetch(`${BASE}/api/cv/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ experiences, replace_existing }),
  });
  if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || `HTTP ${res.status}`); }
  return res.json();
}

export async function matchExperiences(jobId) {
  const res = await fetch(`${BASE}/api/match/experiences/${encodeURIComponent(jobId)}`, { method: 'POST' });
  if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || `HTTP ${res.status}`); }
  return res.json();
}

export async function tailorCv(jobId) {
  const res = await fetch(`${BASE}/api/cv/tailor/${encodeURIComponent(jobId)}`, { method: 'POST' });
  if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || `HTTP ${res.status}`); }
  return res.json();
}

export async function applyKit(jobId) {
  const res = await fetch(`${BASE}/api/apply-kit/${encodeURIComponent(jobId)}`, { method: 'POST' });
  if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || `HTTP ${res.status}`); }
  return res.json();
}

export async function fetchReport(q) {
  const url = q ? `${BASE}/api/report?q=${encodeURIComponent(q)}` : `${BASE}/api/report`;
  const res = await fetch(url);
  return res.json();
}

export async function fetchSettings() {
  const res = await fetch(`${BASE}/api/settings`);
  return res.json();
}

export async function saveSettings(settings) {
  const res = await fetch(`${BASE}/api/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ settings }),
  });
  return res.json();
}
