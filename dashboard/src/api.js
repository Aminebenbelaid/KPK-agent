const BASE = '';

export async function fetchStats() {
  const res = await fetch(`${BASE}/api/applications/stats/summary`);
  return res.json();
}

export async function fetchJobs({ limit = 20, offset = 0, sort = 'match_score_desc', source, remote_type, min_match, search } = {}) {
  const params = new URLSearchParams({ limit, offset, sort });
  if (source) params.set('source', source);
  if (remote_type) params.set('remote_type', remote_type);
  if (min_match) params.set('min_match', min_match);
  if (search) params.set('search', search);
  const res = await fetch(`${BASE}/api/jobs?${params}`);
  return res.json();
}

export async function fetchJob(jobId) {
  const res = await fetch(`${BASE}/api/jobs/${encodeURIComponent(jobId)}`);
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
