import { useState, useEffect, useCallback, useRef } from 'react';
import {
  fetchStats, fetchJobs, fetchJob, updateApplication, fetchHealth, triggerScrape, getScrapeStatus,
  fetchSettings, saveSettings, fetchProfile, saveProfile, triggerScoring, getScoringStatus,
  fetchScoringOverview, listExperiences, createExperience, updateExperience, deleteExperience,
  parseCvText, parseCvFile, confirmCv, matchExperiences, deleteAllJobs, tailorCv,
  applyKit, fetchReport, awaitQueue, fetchSession, claimOwner, uploadCvPhoto, deleteCvPhoto,
} from './api';
import './App.css';

const STATUSES = [
  'wishlist', 'ready', 'applied', 'phone_screen', 'interview',
  'technical_test', 'onsite', 'offer', 'accepted', 'declined', 'rejected', 'withdrawn'
];

const STATUS_COLORS = {
  wishlist: '#9CA3B0', ready: '#3B6FE0', applied: '#6D48D8',
  phone_screen: '#B45309', interview: '#2B5BC4', technical_test: '#8B5CF6',
  onsite: '#D93025', offer: '#1A7A3A', accepted: '#0D6856',
  declined: '#9CA3B0', rejected: '#D93025', withdrawn: '#6B7080',
};

function ScoreBadge({ score }) {
  if (score == null) return <span className="badge badge-gray">Unscored</span>;
  const color = score >= 80 ? 'green' : score >= 60 ? 'yellow' : score >= 40 ? 'orange' : 'red';
  return <span className={`badge badge-${color}`}>{Math.round(score)}</span>;
}

function StatusBadge({ status }) {
  return (
    <span className="status-badge" style={{ backgroundColor: STATUS_COLORS[status] || '#6b7280' }}>
      {status.replace('_', ' ')}
    </span>
  );
}

function StatsBar({ stats, onFilter }) {
  const total = Object.values(stats).reduce((a, b) => a + b, 0);
  const active = ['applied', 'phone_screen', 'interview', 'technical_test', 'onsite', 'offer'];
  const activeCount = active.reduce((sum, s) => sum + (stats[s] || 0), 0);

  return (
    <div className="stats-bar">
      <div className="stat-card" onClick={() => onFilter(null)}>
        <div className="stat-number">{total}</div>
        <div className="stat-label">Total Jobs</div>
      </div>
      <div className="stat-card" onClick={() => onFilter('wishlist')}>
        <div className="stat-number">{stats.wishlist || 0}</div>
        <div className="stat-label">Wishlist</div>
      </div>
      <div className="stat-card stat-active" onClick={() => onFilter('applied')}>
        <div className="stat-number">{activeCount}</div>
        <div className="stat-label">Active</div>
      </div>
      <div className="stat-card stat-success" onClick={() => onFilter('offer')}>
        <div className="stat-number">{(stats.offer || 0) + (stats.accepted || 0)}</div>
        <div className="stat-label">Offers</div>
      </div>
      <div className="stat-card stat-rejected" onClick={() => onFilter('rejected')}>
        <div className="stat-number">{stats.rejected || 0}</div>
        <div className="stat-label">Rejected</div>
      </div>
    </div>
  );
}

function JobRow({ job, onSelect, onStatusChange }) {
  const data = job.job_data || {};
  return (
    <tr className="job-row" onClick={() => onSelect(job)}>
      <td>
        <div className="job-title">{data.title || 'Untitled'}</div>
        <div className="job-company">{data.company || 'Unknown'}</div>
      </td>
      <td>{data.location || '-'}</td>
      <td><span className={`source-tag source-${data.source}`}>{data.source || '-'}</span></td>
      <td><span className="remote-tag">{data.remote_type || '-'}</span></td>
      <td><ScoreBadge score={job.match_score} /></td>
      <td onClick={(e) => e.stopPropagation()}>
        <select
          className="status-select"
          value={job.status}
          onChange={(e) => onStatusChange(job.id, e.target.value)}
          style={{ borderColor: STATUS_COLORS[job.status] }}
        >
          {STATUSES.map(s => <option key={s} value={s}>{s.replace('_', ' ')}</option>)}
        </select>
      </td>
    </tr>
  );
}

function MatchBreakdown({ details }) {
  if (!details) return null;
  const rule = details.rule || {};
  const breakdown = rule.breakdown || {};
  const points = breakdown.points || {};
  const weights = breakdown.weights || {};
  const labels = {
    skills: 'Skills', role: 'Role', location: 'Location',
    remote: 'Remote', seniority: 'Seniority', salary: 'Salary',
  };
  return (
    <div className="match-breakdown">
      <div className="match-score-head">
        <span className="match-score-big">{Math.round(details.score)}</span>
        <span className="match-method">{details.method === 'llm' ? 'AI-scored' : 'Rule-based'}</span>
      </div>
      {details.llm?.explanation && (
        <p className="match-explanation">{details.llm.explanation}</p>
      )}
      {details.boost > 0 && (
        <p className="match-boost">+{details.boost} re-rank boost — matches skills from your past responses{details.boost_skills?.length ? ` (${details.boost_skills.join(', ')})` : ''}</p>
      )}
      <div className="match-bars">
        {Object.keys(labels).map(key => {
          const pts = points[key] ?? 0;
          const max = weights[key] ?? 0;
          const pct = max ? (pts / max) * 100 : 0;
          return (
            <div key={key} className="match-bar-row">
              <span className="match-bar-label">{labels[key]}</span>
              <div className="match-bar-track">
                <div className="match-bar-fill" style={{ width: `${pct}%` }} />
              </div>
              <span className="match-bar-val">{pts}/{max}</span>
            </div>
          );
        })}
      </div>
      {breakdown.skills_matched?.length > 0 && (
        <div className="match-skills">
          <strong>Matched:</strong>
          {breakdown.skills_matched.map((s, i) => <span key={i} className="tech-tag tech-match">{s}</span>)}
        </div>
      )}
      {breakdown.skills_missing?.length > 0 && (
        <div className="match-skills">
          <strong>Missing:</strong>
          {breakdown.skills_missing.map((s, i) => <span key={i} className="tech-tag tech-miss">{s}</span>)}
        </div>
      )}
    </div>
  );
}

function queueLabel(q, fallback) {
  if (!q) return fallback;
  if (q.status === 'queued') return q.position > 1 ? `In queue (#${q.position})…` : 'In queue…';
  return fallback;
}

function JobExperienceMatch({ job, onGenerated }) {
  const cached = job.match_details?.experience_match || null;
  const [result, setResult] = useState(cached);
  const [loading, setLoading] = useState(false);
  const [qstate, setQstate] = useState(null);
  const [error, setError] = useState(null);

  const run = async () => {
    setLoading(true); setError(null); setQstate(null);
    try {
      const sub = await matchExperiences(job.job_id);
      const r = await awaitQueue(sub, setQstate);
      setResult(r);
      onGenerated && onGenerated();
    } catch (err) {
      setError(err.message);
    }
    setLoading(false); setQstate(null);
  };

  return (
    <div className="detail-section">
      <div className="exp-match-head">
        <h3>Best matching experiences</h3>
        <button className="refresh-btn" onClick={run} disabled={loading}>
          {loading ? queueLabel(qstate, 'Matching…') : result ? 'Re-match' : 'Find best experiences'}
        </button>
      </div>
      {error && <p className="scrape-error">{error}</p>}
      {result?.overall && <p className="match-explanation">{result.overall}</p>}
      {result?.matches?.length > 0 ? (
        <div className="exp-match-list">
          {result.matches.map((m, i) => (
            <div key={i} className="exp-match-row">
              <div className="exp-match-top">
                <span className="exp-match-title">{m.title || m.id}</span>
                <span className="badge badge-blue">{m.relevance}</span>
              </div>
              {m.organization && <div className="exp-match-org">{m.organization}</div>}
              <div className="exp-match-reason">{m.reason}</div>
            </div>
          ))}
        </div>
      ) : result && !loading ? (
        <p className="muted">No experiences on file yet — add some in the Experience tab.</p>
      ) : null}
    </div>
  );
}

function JobCVGen({ job, onGenerated }) {
  const existing = job.cv_path ? `/api/applications/${job.id}/cv` : null;
  const [state, setState] = useState(existing ? { download: existing } : null);
  const [loading, setLoading] = useState(false);
  const [qstate, setQstate] = useState(null);
  const [error, setError] = useState(null);

  const run = async () => {
    setLoading(true); setError(null); setQstate(null);
    try {
      const sub = await tailorCv(job.job_id);
      const r = await awaitQueue(sub, setQstate);
      setState(r);
      onGenerated && onGenerated();
    } catch (err) {
      setError(err.message);
    }
    setLoading(false); setQstate(null);
  };

  return (
    <div className="detail-section">
      <div className="exp-match-head">
        <h3>Tailored CV</h3>
        <button className="refresh-btn" onClick={run} disabled={loading}>
          {loading ? queueLabel(qstate, 'Generating…') : state ? 'Regenerate' : 'Generate tailored CV'}
        </button>
      </div>
      {error && <p className="scrape-error">{error}</p>}
      {loading && <p className="muted">Tailoring your bullet points to this job and compiling the PDF — can take up to a minute.</p>}
      {state?.download && (
        <div className="cv-result">
          <a className="search-btn cv-download" href={state.download} target="_blank" rel="noreferrer">Download CV PDF</a>
          {state.tailored === false && <span className="muted"> used base template (tailored version didn't compile)</span>}
          {state.emphasized?.length > 0 && (
            <div className="cv-emph-wrap">
              <strong>Emphasized for this job:</strong>
              <ul className="cv-emph">{state.emphasized.map((b, i) => <li key={i}>{b}</li>)}</ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const APPLY_CHECKLIST = [
  'Review the tailored CV and cover letter',
  'Open the original posting and start the application',
  'Paste / upload the CV and cover letter',
  'Double-check name, contact details and any custom questions',
  'Submit, then mark this job as Applied',
];

function ApplyAssistant({ job, onStatusChange, onGenerated }) {
  // Rebuild from persisted data so closing/reopening the job keeps the prepared files.
  const persisted = (job.cv_path || job.cover_letter_path) ? {
    cv_download: job.cv_path ? `/api/applications/${job.id}/cv` : null,
    cover_letter_download: job.cover_letter_path ? `/api/applications/${job.id}/cover-letter` : null,
    cover_letter_text: null,
    apply_url: (job.job_data || {}).url || '',
    checklist: APPLY_CHECKLIST,
  } : null;
  const [kit, setKit] = useState(persisted);
  const [loading, setLoading] = useState(false);
  const [qstate, setQstate] = useState(null);
  const [error, setError] = useState(null);

  const run = async () => {
    setLoading(true); setError(null); setQstate(null);
    try {
      const sub = await applyKit(job.job_id);
      setKit(await awaitQueue(sub, setQstate));
      onGenerated && onGenerated();
    }
    catch (err) { setError(err.message); }
    setLoading(false); setQstate(null);
  };

  return (
    <div className="detail-section">
      <div className="exp-match-head">
        <h3>Apply Assistant</h3>
        <button className="search-btn" onClick={run} disabled={loading}>
          {loading ? queueLabel(qstate, 'Preparing…') : kit ? 'Re-prepare' : 'Prepare application'}
        </button>
      </div>
      {error && <p className="scrape-error">{error}</p>}
      {loading && <p className="muted">Tailoring your CV and writing a cover letter for this job — up to a minute.</p>}
      {kit && (
        <div className="kit">
          <div className="kit-actions">
            {kit.cv_download && <a className="search-btn" href={kit.cv_download} target="_blank" rel="noreferrer">CV (PDF)</a>}
            {kit.cover_letter_download && <a className="search-btn" href={kit.cover_letter_download} target="_blank" rel="noreferrer">Cover letter (PDF)</a>}
            {kit.apply_url && <a className="refresh-btn" href={kit.apply_url} target="_blank" rel="noreferrer">Open posting ↗</a>}
            <button className="refresh-btn" onClick={() => onStatusChange(job.id, 'applied')}>Mark as applied</button>
          </div>
          {kit.cover_letter_text && (
            <details className="kit-letter">
              <summary>Preview cover letter</summary>
              <p>{kit.cover_letter_text}</p>
            </details>
          )}
          <ol className="kit-checklist">
            {kit.checklist.map((c, i) => <li key={i}>{c}</li>)}
          </ol>
        </div>
      )}
    </div>
  );
}

function JobDetail({ job, onClose, onStatusChange, onGenerated }) {
  if (!job) return null;
  const data = job.job_data || {};
  const alsoOn = data.also_on || [];
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose}>X</button>
        <h2>{data.title}</h2>
        <div className="detail-meta">
          <span>{data.company}</span>
          <span>{data.location}</span>
          <span className={`source-tag source-${data.source}`}>{data.source}</span>
          <span className="remote-tag">{data.remote_type}</span>
          <ScoreBadge score={job.match_score} />
          <StatusBadge status={job.status} />
        </div>
        {data.url && <a href={data.url} target="_blank" rel="noreferrer" className="job-link">View original posting</a>}
        {alsoOn.length > 0 && (
          <div className="also-on">
            Also posted on:
            {alsoOn.map((a, i) => (
              a.url
                ? <a key={i} href={a.url} target="_blank" rel="noreferrer" className={`source-tag source-${a.source}`}>{a.source}</a>
                : <span key={i} className={`source-tag source-${a.source}`}>{a.source}</span>
            ))}
          </div>
        )}
        <div className="detail-section">
          <h3>Skills & Technologies</h3>
          <div className="tag-list">
            {(data.skills_required || []).map((s, i) => <span key={i} className="tech-tag">{s}</span>)}
            {(data.skills_required || []).length === 0 && <span className="muted">None detected</span>}
          </div>
        </div>
        {job.match_details && (
          <div className="detail-section">
            <h3>Match Details</h3>
            <MatchBreakdown details={job.match_details} />
          </div>
        )}
        <JobExperienceMatch job={job} onGenerated={onGenerated} />
        <JobCVGen job={job} onGenerated={onGenerated} />
        <ApplyAssistant job={job} onStatusChange={onStatusChange} onGenerated={onGenerated} />
        {data.description_clean && (
          <div className="detail-section">
            <h3>Description</h3>
            <div className="job-description">{data.description_clean.substring(0, 1500)}</div>
          </div>
        )}
        <div className="detail-section detail-dates">
          <span>Created: {job.created_at?.split('T')[0]}</span>
          <span>Scraped: {data.scraped_date?.split('T')[0]}</span>
          {job.applied_date && <span>Applied: {job.applied_date.split('T')[0]}</span>}
        </div>
      </div>
    </div>
  );
}

const SCRAPERS = [
  { id: 'linkedin', label: 'LinkedIn' },
  { id: 'stepstone', label: 'StepStone' },
  { id: 'xing', label: 'Xing' },
  { id: 'arbeitsagentur', label: 'Arbeitsagentur' },
];

function SearchPanel({ onComplete }) {
  const [query, setQuery] = useState('');
  const [location, setLocation] = useState('Nordrhein-Westfalen');
  const [selected, setSelected] = useState(['linkedin', 'stepstone', 'xing', 'arbeitsagentur']);
  const [scrapeState, setScrapeState] = useState(null); // null | {taskId, status, error}
  const pollRef = useRef(null);

  const toggleScraper = (id) => {
    setSelected(prev => prev.includes(id) ? prev.filter(s => s !== id) : [...prev, id]);
  };

  const handleSearch = async () => {
    if (selected.length === 0) return;
    try {
      setScrapeState({ status: 'starting', error: null });
      const res = await triggerScrape({
        scrapers: selected,
        query: query || null,
        location: location || null,
        parallel: true,
      });
      setScrapeState({ taskId: res.task_id, status: res.status || 'queued', position: res.position, error: null });

      pollRef.current = setInterval(async () => {
        try {
          const status = await getScrapeStatus(res.task_id);
          setScrapeState(prev => ({ ...prev, status: status.status, position: status.position, result: status.result }));
          if (!['running', 'starting', 'queued'].includes(status.status)) {
            clearInterval(pollRef.current);
            pollRef.current = null;
            if (status.status === 'completed') {
              onComplete();
            }
          }
        } catch {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
      }, 2000);
    } catch (err) {
      setScrapeState({ status: 'error', error: err.message });
    }
  };

  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  const isRunning = ['running', 'starting', 'queued'].includes(scrapeState?.status);
  const isQueued = scrapeState?.status === 'queued';

  return (
    <div className="search-panel">
      <div className="search-panel-header">
        <h2>Search Jobs</h2>
        {scrapeState?.status === 'completed' && (
          <span className="scrape-done">Scraping complete!</span>
        )}
        {scrapeState?.status === 'failed' && (
          <span className="scrape-error">Scraping failed</span>
        )}
        {scrapeState?.status === 'error' && (
          <span className="scrape-error">{scrapeState.error}</span>
        )}
      </div>
      <div className="search-inputs">
        <input
          type="text"
          placeholder="Job title (e.g. Python Developer)..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="filter-input search-query-input"
          disabled={isRunning}
          onKeyDown={(e) => e.key === 'Enter' && !isRunning && handleSearch()}
        />
        <input
          type="text"
          placeholder="Location..."
          value={location}
          onChange={(e) => setLocation(e.target.value)}
          className="filter-input search-location-input"
          disabled={isRunning}
          onKeyDown={(e) => e.key === 'Enter' && !isRunning && handleSearch()}
        />
        <button
          className="search-btn"
          onClick={handleSearch}
          disabled={isRunning || selected.length === 0}
        >
          {isQueued ? (scrapeState.position > 1 ? `Queued (#${scrapeState.position})…` : 'Queued…') : isRunning ? 'Searching…' : 'Search'}
        </button>
      </div>
      <div className="scraper-toggles">
        {SCRAPERS.map(s => (
          <label key={s.id} className={`scraper-toggle ${selected.includes(s.id) ? 'active' : ''}`}>
            <input
              type="checkbox"
              checked={selected.includes(s.id)}
              onChange={() => toggleScraper(s.id)}
              disabled={isRunning}
            />
            <span className={`source-tag source-${s.id}`}>{s.label}</span>
          </label>
        ))}
      </div>
      {isRunning && (
        <div className="scrape-progress">
          <div className="scrape-spinner" />
          <span>
            {isQueued
              ? `Waiting in line${scrapeState.position > 1 ? ` — ${scrapeState.position - 1} task(s) ahead` : ''}…`
              : `Scraping ${selected.length} source${selected.length > 1 ? 's' : ''} in parallel…`}
          </span>
        </div>
      )}
    </div>
  );
}

function Filters({ filters, onChange }) {
  return (
    <div className="filters">
      <input
        type="text"
        placeholder="Search title or company..."
        value={filters.search || ''}
        onChange={(e) => onChange({ ...filters, search: e.target.value, offset: 0 })}
        className="filter-input search-input"
      />
      <select
        value={filters.source || ''}
        onChange={(e) => onChange({ ...filters, source: e.target.value, offset: 0 })}
        className="filter-input"
      >
        <option value="">All sources</option>
        <option value="linkedin">LinkedIn</option>
        <option value="stepstone">StepStone</option>
        <option value="arbeitsagentur">Arbeitsagentur</option>
        <option value="xing">Xing</option>
      </select>
      <select
        value={filters.remote_type || ''}
        onChange={(e) => onChange({ ...filters, remote_type: e.target.value, offset: 0 })}
        className="filter-input"
      >
        <option value="">All types</option>
        <option value="remote">Remote</option>
        <option value="on-site">On-site</option>
      </select>
      <select
        value={filters.sort || 'match_score_desc'}
        onChange={(e) => onChange({ ...filters, sort: e.target.value, offset: 0 })}
        className="filter-input"
      >
        <option value="match_score_desc">Score (high first)</option>
        <option value="match_score_asc">Score (low first)</option>
        <option value="created_at_desc">Newest first</option>
        <option value="created_at_asc">Oldest first</option>
        <option value="company_asc">Company A-Z</option>
      </select>
      <input
        type="number"
        placeholder="Min score"
        value={filters.min_match || ''}
        onChange={(e) => onChange({ ...filters, min_match: e.target.value, offset: 0 })}
        className="filter-input score-input"
        min="0"
        max="100"
      />
    </div>
  );
}

const GLOBAL_SETTING_FIELDS = [
  { key: 'kisski_api_key', label: 'Kisski API Key', type: 'password', placeholder: 'Your Kisski LLM API key' },
  { key: 'kisski_base_url', label: 'Kisski Base URL', type: 'text', placeholder: 'https://chat-ai.academiccloud.de/v1' },
  { key: 'llm_model', label: 'LLM Model', type: 'text', placeholder: 'auto (leave blank to auto-pick an available model)' },
];

const VISITOR_LLM_FIELDS = [
  { key: 'llm_api_key', label: 'Your LLM API key', type: 'password',
    placeholder: 'Groq (free at console.groq.com), OpenRouter, Kisski… any OpenAI-compatible key' },
  { key: 'llm_base_url', label: 'Provider base URL', type: 'text',
    placeholder: 'default: https://api.groq.com/openai/v1 · OpenRouter: https://openrouter.ai/api/v1' },
  { key: 'llm_model_session', label: 'Model', type: 'text',
    placeholder: 'auto — e.g. llama-3.3-70b-versatile (Groq)' },
];

const SESSION_SETTING_FIELDS = [
  { key: 'cv_instructions', label: 'CV prompt add-ons', type: 'textarea',
    placeholder: 'Extra guidance applied when tailoring your CV — e.g. "emphasise leadership and metrics", "keep it to one page", "use British spelling".' },
  { key: 'cover_letter_instructions', label: 'Cover letter prompt add-ons', type: 'textarea',
    placeholder: 'Extra guidance applied to cover letters — e.g. "warm, confident tone", "mention willingness to relocate", "max 250 words".' },
];

function CvPhotoSection() {
  const [ts, setTs] = useState(Date.now());
  const [hasPhoto, setHasPhoto] = useState(false);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef(null);

  useEffect(() => {
    fetch(`/api/cv/photo?ts=${ts}`).then(r => setHasPhoto(r.ok)).catch(() => setHasPhoto(false));
  }, [ts]);

  const onFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true); setError(null);
    try {
      await uploadCvPhoto(file);
      setTs(Date.now());
    } catch (err) { setError(err.message); }
    setBusy(false);
    if (fileRef.current) fileRef.current.value = '';
  };

  const onRemove = async () => {
    setBusy(true);
    try { await deleteCvPhoto(); setTs(Date.now()); } catch { /* ignore */ }
    setBusy(false);
  };

  return (
    <div className="photo-section">
      <label className="setting-label">CV photo <span className="muted">(shown top-right of the generated CV)</span></label>
      <div className="photo-row">
        {hasPhoto ? (
          <img className="photo-preview" src={`/api/cv/photo?ts=${ts}`} alt="CV" />
        ) : (
          <div className="photo-placeholder">No photo</div>
        )}
        <div className="photo-actions">
          <label className="refresh-btn upload-btn">
            {busy ? 'Working…' : hasPhoto ? 'Replace photo' : 'Upload photo'}
            <input ref={fileRef} type="file" accept="image/png,image/jpeg" onChange={onFile} disabled={busy} hidden />
          </label>
          {hasPhoto && <button className="link-btn del" onClick={onRemove} disabled={busy}>Remove</button>}
        </div>
      </div>
      {error && <p className="scrape-error">{error}</p>}
    </div>
  );
}

function AdminSection({ isOwner, onClaimed }) {
  const [key, setKey] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  if (isOwner) {
    return <p className="owner-badge">Owner workspace — you are managing the server settings and the owner's data.</p>;
  }

  const doClaim = async () => {
    setBusy(true); setError(null);
    try {
      await claimOwner(key);
      onClaimed();
    } catch (err) { setError(err.message); }
    setBusy(false);
  };

  return (
    <div className="admin-box">
      <label className="setting-label">Admin access <span className="muted">(owner only)</span></label>
      <div className="setting-input-wrap">
        <input type="password" className="filter-input setting-input" placeholder="Admin key"
          value={key} onChange={e => setKey(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && key && doClaim()} />
        <button className="refresh-btn" onClick={doClaim} disabled={busy || !key}>Unlock</button>
      </div>
      {error && <p className="scrape-error">{error}</p>}
    </div>
  );
}

function SettingsPanel() {
  const [values, setValues] = useState({});
  const [isOwner, setIsOwner] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saved, setSaved] = useState(false);
  const [showPasswords, setShowPasswords] = useState({});

  const load = useCallback(() => {
    fetchSettings().then(data => {
      setValues(data);
      setIsOwner(!!data._is_owner);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);
  useEffect(() => { load(); }, [load]);

  const fields = isOwner
    ? [...SESSION_SETTING_FIELDS, ...GLOBAL_SETTING_FIELDS]
    : [...VISITOR_LLM_FIELDS, ...SESSION_SETTING_FIELDS];

  const handleSave = async () => {
    const toSave = {};
    for (const field of fields) {
      const val = values[field.key];
      if (val === undefined || val === null) continue;
      if (typeof val === 'string' && val.includes('****')) continue; // unchanged masked secret
      toSave[field.key] = val; // allow empty string so a field can be cleared
    }
    await saveSettings(toSave);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const toggleShow = (key) => {
    setShowPasswords(prev => ({ ...prev, [key]: !prev[key] }));
  };

  if (loading) return <div className="settings-panel"><p>Loading settings...</p></div>;

  return (
    <div className="settings-panel">
      <div className="settings-header">
        <h2>Settings</h2>
        {saved && <span className="settings-saved">Saved!</span>}
      </div>
      <p className="panel-hint">Your settings live in this browser's workspace. The CV photo and prompt add-ons are used when generating your documents.</p>
      {!isOwner && (
        <div className="card flat" style={{ marginBottom: '1.4rem' }}>
          <p style={{ fontSize: '0.92rem' }}>
            <b>AI features run with your own key.</b> Scraping and rule-based ranking work without one —
            but scoring refinement, CV parsing and CV/cover-letter generation need an LLM.
            Get a free key at <a href="https://console.groq.com" target="_blank" rel="noreferrer">console.groq.com</a>,
            paste it below, save — done. OpenRouter, Kisski or any OpenAI-compatible provider also work.
          </p>
        </div>
      )}

      <CvPhotoSection />

      <div className="settings-grid">
        {fields.map(field => (
          <div key={field.key} className={`setting-row ${field.type === 'textarea' ? 'setting-row-wide' : ''}`}>
            <label className="setting-label">{field.label}</label>
            {field.type === 'textarea' ? (
              <textarea
                className="filter-input setting-input"
                rows="3"
                placeholder={field.placeholder}
                value={values[field.key] || ''}
                onChange={(e) => setValues(prev => ({ ...prev, [field.key]: e.target.value }))}
              />
            ) : (
              <div className="setting-input-wrap">
                <input
                  type={field.type === 'password' && !showPasswords[field.key] ? 'password' : 'text'}
                  className="filter-input setting-input"
                  placeholder={field.placeholder}
                  value={values[field.key] || ''}
                  onChange={(e) => setValues(prev => ({ ...prev, [field.key]: e.target.value }))}
                />
                {field.type === 'password' && (
                  <button className="toggle-pw" onClick={() => toggleShow(field.key)}>
                    {showPasswords[field.key] ? 'Hide' : 'Show'}
                  </button>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
      <button className="search-btn settings-save-btn" onClick={handleSave}>Save Settings</button>

      <AdminSection isOwner={isOwner} onClaimed={load} />
    </div>
  );
}

const REMOTE_OPTIONS = ['', 'remote', 'hybrid', 'on-site'];

function toList(str) {
  return str.split(',').map(s => s.trim()).filter(Boolean);
}

function PreferencesSection() {
  const [p, setP] = useState(null);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);
  const [open, setOpen] = useState(true);

  useEffect(() => {
    fetchProfile().then(setP).catch(() => {});
  }, []);

  const set = (key, val) => setP(prev => ({ ...prev, [key]: val }));

  const handleSave = async () => {
    setError(null);
    try {
      const payload = {
        ...p,  // keep any other stored fields (name/email/notes) untouched
        target_roles: Array.isArray(p.target_roles) ? p.target_roles : toList(p.target_roles || ''),
        experience_years: p.experience_years === '' ? 0 : Number(p.experience_years),
        min_salary: p.min_salary === '' || p.min_salary == null ? null : Number(p.min_salary),
      };
      const updated = await saveProfile(payload);
      setP(updated);
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      setError(err.message);
    }
  };

  if (!p) return null;
  const asText = (v) => Array.isArray(v) ? v.join(', ') : (v || '');

  return (
    <div className="prefs-card">
      <div className="prefs-head" onClick={() => setOpen(o => !o)}>
        <h3>Preferences <span className="muted">— what you want (location, remote, salary, roles)</span></h3>
        <div className="prefs-head-right">
          {saved && <span className="settings-saved">Saved!</span>}
          {error && <span className="scrape-error">{error}</span>}
          <span className="prefs-toggle">{open ? '▲' : '▼'}</span>
        </div>
      </div>
      {open && (
        <>
          <div className="settings-grid">
            <div className="setting-row">
              <label className="setting-label">Target roles <span className="muted">(comma-separated)</span></label>
              <input className="filter-input setting-input" value={asText(p.target_roles)} onChange={e => set('target_roles', e.target.value)} placeholder="Python Developer, Backend Engineer" />
            </div>
            <div className="setting-row">
              <label className="setting-label">Location</label>
              <input className="filter-input setting-input" value={p.location || ''} onChange={e => set('location', e.target.value)} placeholder="e.g. Köln, NRW" />
            </div>
            <div className="setting-row">
              <label className="setting-label">Preferred remote type</label>
              <select className="filter-input setting-input" value={p.preferred_remote_type || ''} onChange={e => set('preferred_remote_type', e.target.value)}>
                {REMOTE_OPTIONS.map(o => <option key={o} value={o}>{o || 'No preference'}</option>)}
              </select>
            </div>
            <div className="setting-row">
              <label className="setting-label">Minimum salary (EUR)</label>
              <input type="number" min="0" className="filter-input setting-input" value={p.min_salary ?? ''} onChange={e => set('min_salary', e.target.value)} placeholder="e.g. 45000" />
            </div>
            <div className="setting-row">
              <label className="setting-label">Years of experience</label>
              <input type="number" min="0" className="filter-input setting-input" value={p.experience_years ?? 0} onChange={e => set('experience_years', e.target.value)} />
            </div>
          </div>
          <button className="search-btn" onClick={handleSave}>Save Preferences</button>
        </>
      )}
    </div>
  );
}

function ScoreBar({ onComplete }) {
  const [overview, setOverview] = useState(null);
  const [state, setState] = useState(null); // null | {taskId,status,done,total}
  const pollRef = useRef(null);

  const refresh = useCallback(() => {
    fetchScoringOverview().then(setOverview).catch(() => {});
  }, []);

  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  const runScoring = async (onlyUnscored) => {
    try {
      setState({ status: 'starting', done: 0, total: 0 });
      const res = await triggerScoring({ only_unscored: onlyUnscored, use_llm: true });
      setState({ taskId: res.task_id, status: res.status || 'queued', position: res.position, done: 0, total: 0 });
      pollRef.current = setInterval(async () => {
        try {
          const s = await getScoringStatus(res.task_id);
          setState({ taskId: res.task_id, status: s.status, position: s.position, done: s.done, total: s.total, llm_done: s.llm_done, llm_total: s.llm_total });
          if (!['running', 'starting', 'queued'].includes(s.status)) {
            clearInterval(pollRef.current);
            pollRef.current = null;
            refresh();
            if (s.status === 'completed') onComplete();
          }
        } catch {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
      }, 1500);
    } catch (err) {
      setState({ status: 'error', error: err.message });
    }
  };

  const running = ['running', 'starting', 'queued'].includes(state?.status);

  return (
    <div className="score-bar">
      <div className="score-bar-info">
        <strong>Matching</strong>
        {overview && (
          <span className="muted">
            {overview.scored_jobs}/{overview.total_jobs} scored
            {' · '}{overview.llm_available ? 'AI refinement on' : 'rule-based (no LLM key)'}
          </span>
        )}
      </div>
      <div className="score-bar-actions">
        <button className="search-btn score-btn" disabled={running} onClick={() => runScoring(false)}>
          {running
            ? (state.status === 'queued'
                ? (state.position > 1 ? `Queued (#${state.position})…` : 'Queued…')
                : state.done >= state.total && state.llm_total > 0
                  ? `AI-refining ${state.llm_done}/${state.llm_total}...`
                  : `Scoring ${state.done}/${state.total}...`)
            : 'Score all jobs'}
        </button>
        <button className="refresh-btn" disabled={running} onClick={() => runScoring(true)}>
          Score new only
        </button>
      </div>
      {state?.status === 'completed' && <span className="scrape-done">Scoring complete!</span>}
      {state?.status === 'error' && <span className="scrape-error">{state.error}</span>}
    </div>
  );
}

const EMPTY_EXP = { kind: 'job', title: '', organization: '', description: '', stack: '', start_date: '', end_date: '' };

function ExperienceForm({ initial, onSubmit, onCancel, busy }) {
  const [f, setF] = useState(initial || EMPTY_EXP);
  const set = (k, v) => setF(prev => ({ ...prev, [k]: v }));
  return (
    <div className="exp-form">
      <div className="exp-form-grid">
        <select className="filter-input" value={f.kind} onChange={e => set('kind', e.target.value)}>
          <option value="job">Job</option>
          <option value="project">Project</option>
        </select>
        <input className="filter-input" placeholder="Title / role" value={f.title} onChange={e => set('title', e.target.value)} />
        <input className="filter-input" placeholder="Organization" value={f.organization} onChange={e => set('organization', e.target.value)} />
        <input className="filter-input" placeholder="Start (YYYY-MM)" value={f.start_date || ''} onChange={e => set('start_date', e.target.value)} />
        <input className="filter-input" placeholder="End (YYYY-MM / present)" value={f.end_date || ''} onChange={e => set('end_date', e.target.value)} />
      </div>
      <textarea className="filter-input" rows="3" placeholder="What did you do? The AI will summarize the type of experience." value={f.description} onChange={e => set('description', e.target.value)} />
      <input className="filter-input" placeholder="Stack (comma-separated): Python, FastAPI, Docker" value={f.stack} onChange={e => set('stack', e.target.value)} />
      <div className="exp-form-actions">
        <button className="search-btn" disabled={busy || !f.title} onClick={() => onSubmit(f)}>
          {busy ? 'Saving...' : 'Save experience'}
        </button>
        {onCancel && <button className="refresh-btn" onClick={onCancel}>Cancel</button>}
      </div>
    </div>
  );
}

function CVReviewModal({ review, setReview, onConfirm, busy }) {
  if (!review) return null;
  const update = (i, key, val) => setReview(r => {
    const exps = r.experiences.map((e, idx) => idx === i ? { ...e, [key]: val } : e);
    return { ...r, experiences: exps };
  });
  const removeItem = (i) => setReview(r => ({ ...r, experiences: r.experiences.filter((_, idx) => idx !== i) }));
  return (
    <div className="modal-overlay" onClick={() => setReview(null)}>
      <div className="modal modal-wide" onClick={e => e.stopPropagation()}>
        <button className="modal-close" onClick={() => setReview(null)}>X</button>
        <h2>Review parsed experiences</h2>
        <p className="panel-hint">The AI extracted {review.experiences.length} item(s). Edit anything that's off, then save.</p>
        <div className="review-list">
          {review.experiences.map((e, i) => (
            <div key={i} className="review-item">
              <div className="review-item-head">
                <select className="filter-input review-kind" value={e.kind} onChange={ev => update(i, 'kind', ev.target.value)}>
                  <option value="job">Job</option>
                  <option value="project">Project</option>
                </select>
                <input className="filter-input" value={e.title} onChange={ev => update(i, 'title', ev.target.value)} placeholder="Title" />
                <button className="del-btn" onClick={() => removeItem(i)}>Remove</button>
              </div>
              <input className="filter-input" value={e.organization || ''} onChange={ev => update(i, 'organization', ev.target.value)} placeholder="Organization" />
              <textarea className="filter-input" rows="2" value={e.description || ''} onChange={ev => update(i, 'description', ev.target.value)} placeholder="Description" />
              <input className="filter-input" value={Array.isArray(e.stack) ? e.stack.join(', ') : (e.stack || '')} onChange={ev => update(i, 'stack', toList(ev.target.value))} placeholder="Stack" />
              {e.ai_summary && <div className="exp-ai-summary">{e.ai_summary}</div>}
            </div>
          ))}
          {review.experiences.length === 0 && <p className="muted">Nothing to save.</p>}
        </div>
        <label className="review-replace">
          <input type="checkbox" checked={review.replace} onChange={e => setReview(r => ({ ...r, replace: e.target.checked }))} />
          Replace previously imported CV experiences
        </label>
        <div className="exp-form-actions">
          <button className="search-btn" disabled={busy || review.experiences.length === 0} onClick={onConfirm}>
            {busy ? 'Saving...' : `Save ${review.experiences.length} experience(s)`}
          </button>
          <button className="refresh-btn" onClick={() => setReview(null)}>Cancel</button>
        </div>
      </div>
    </div>
  );
}

function ExperienceCard({ exp, onEdit, onDelete }) {
  return (
    <div className="exp-card">
      <div className="exp-card-head">
        <div>
          <span className={`exp-kind exp-kind-${exp.kind}`}>{exp.kind}</span>
          <span className="exp-title">{exp.title}</span>
          {exp.organization && <span className="exp-org"> · {exp.organization}</span>}
        </div>
        <div className="exp-card-actions">
          <button className="link-btn" onClick={() => onEdit(exp)}>Edit</button>
          <button className="link-btn del" onClick={() => onDelete(exp.id)}>Delete</button>
        </div>
      </div>
      {(exp.start_date || exp.end_date) && (
        <div className="exp-dates">{exp.start_date || '?'} – {exp.end_date || 'present'}</div>
      )}
      {exp.ai_summary && <div className="exp-ai-summary">{exp.ai_summary}</div>}
      {exp.description && <div className="exp-desc">{exp.description}</div>}
      <div className="tag-list">
        {(exp.stack || []).map((s, i) => <span key={i} className="tech-tag">{s}</span>)}
        {(exp.ai_tags || []).map((t, i) => <span key={`t${i}`} className="tech-tag exp-tag">{t}</span>)}
      </div>
      {exp.source === 'cv' && <span className="exp-source">from CV</span>}
    </div>
  );
}

function ExperiencePanel() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [pasteText, setPasteText] = useState('');
  const [parsing, setParsing] = useState(false);
  const [qstate, setQstate] = useState(null);
  const [review, setReview] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(null); // experience object or null
  const [showAdd, setShowAdd] = useState(false);
  const fileRef = useRef(null);

  const load = useCallback(() => {
    setLoading(true);
    listExperiences().then(d => { setItems(d || []); setLoading(false); }).catch(() => setLoading(false));
  }, []);
  useEffect(() => { load(); }, [load]);

  const openReview = (exps) => {
    if (!exps || exps.length === 0) { setError('No experiences found in that CV.'); return; }
    setReview({ experiences: exps.map(e => ({ ...e })), replace: false });
  };

  const onFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setParsing(true); setError(null);
    try {
      const sub = await parseCvFile(file);
      const r = await awaitQueue(sub, setQstate);
      openReview(r.experiences);
    }
    catch (err) { setError(err.message); }
    setParsing(false); setQstate(null);
    if (fileRef.current) fileRef.current.value = '';
  };

  const onParseText = async () => {
    if (!pasteText.trim()) return;
    setParsing(true); setError(null);
    try {
      const sub = await parseCvText(pasteText);
      const r = await awaitQueue(sub, setQstate);
      openReview(r.experiences);
    }
    catch (err) { setError(err.message); }
    setParsing(false); setQstate(null);
  };

  const confirmReview = async () => {
    setBusy(true); setError(null);
    try {
      const exps = review.experiences.map(e => ({
        ...e, stack: Array.isArray(e.stack) ? e.stack : toList(e.stack || ''), source: 'cv',
      }));
      await confirmCv(exps, review.replace);
      setReview(null); setPasteText(''); load();
    } catch (err) { setError(err.message); }
    setBusy(false);
  };

  const submitForm = async (form) => {
    setBusy(true); setError(null);
    try {
      const payload = {
        kind: form.kind, title: form.title, organization: form.organization,
        description: form.description, stack: toList(form.stack || ''),
        start_date: form.start_date || null, end_date: form.end_date || null, source: 'manual',
      };
      if (editing) await updateExperience(editing.id, payload);
      else await createExperience(payload);
      setEditing(null); setShowAdd(false); load();
    } catch (err) { setError(err.message); }
    setBusy(false);
  };

  const startEdit = (exp) => {
    setShowAdd(false);
    setEditing({ ...exp, stack: (exp.stack || []).join(', '), start_date: exp.start_date || '', end_date: exp.end_date || '' });
  };
  const remove = async (id) => { await deleteExperience(id); load(); };

  return (
    <div className="settings-panel">
      <div className="settings-header">
        <h2>Experience Base</h2>
        {error && <span className="scrape-error">{error}</span>}
      </div>
      <p className="panel-hint">Upload your CV or add experiences manually. The AI understands what you did and uses it to rank and tailor job matches.</p>

      <PreferencesSection />

      <div className="exp-import-card">
        <h3>Import from CV</h3>
        <div className="exp-import-row">
          <label className="search-btn upload-btn">
            {parsing ? queueLabel(qstate, 'Parsing…') : 'Upload CV (PDF / text)'}
            <input ref={fileRef} type="file" accept=".pdf,.tex,.txt,.md,text/plain,application/pdf" onChange={onFile} disabled={parsing} hidden />
          </label>
          <span className="muted">or paste below</span>
        </div>
        <textarea className="filter-input" rows="4" placeholder="Paste your CV / LaTeX text here..." value={pasteText} onChange={e => setPasteText(e.target.value)} disabled={parsing} />
        <button className="refresh-btn" onClick={onParseText} disabled={parsing || !pasteText.trim()}>
          {parsing ? queueLabel(qstate, 'Parsing…') : 'Parse text with AI'}
        </button>
      </div>

      <div className="exp-add-bar">
        <h3>Your experiences <span className="muted">({items.length})</span></h3>
        {!showAdd && !editing && <button className="search-btn" onClick={() => setShowAdd(true)}>+ Add experience</button>}
      </div>

      {showAdd && !editing && (
        <ExperienceForm initial={EMPTY_EXP} busy={busy} onSubmit={submitForm} onCancel={() => setShowAdd(false)} />
      )}
      {editing && (
        <ExperienceForm key={editing.id} initial={editing} busy={busy} onSubmit={submitForm} onCancel={() => setEditing(null)} />
      )}

      {loading ? <p>Loading...</p> : (
        <div className="exp-list">
          {items.map(exp => <ExperienceCard key={exp.id} exp={exp} onEdit={startEdit} onDelete={remove} />)}
          {items.length === 0 && <p className="muted">No experiences yet. Upload a CV or add one above.</p>}
        </div>
      )}

      <CVReviewModal review={review} setReview={setReview} onConfirm={confirmReview} busy={busy} />
    </div>
  );
}

function renderEmphasis(text) {
  // Render the LLM summary's **bold** markup, and drop stray markdown chars.
  const clean = (text || '').replace(/^#+\s*/gm, '').replace(/`/g, '');
  return clean.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    /^\*\*[^*]+\*\*$/.test(part)
      ? <strong key={i}>{part.slice(2, -2)}</strong>
      : <span key={i}>{part.replace(/\*/g, '')}</span>
  );
}

function RankList({ items }) {
  const max = items?.[0]?.count || 1;
  return (
    <ul className="rank-list">
      {items.map((it, i) => (
        <li key={i}>
          <span className="rank-name" title={it.name}>{it.name}</span>
          <span className="rank-bar"><span style={{ width: `${(it.count / max) * 100}%` }} /></span>
          <span className="rank-count">{it.count}</span>
        </li>
      ))}
    </ul>
  );
}

function TrendsPanel() {
  const [q, setQ] = useState('');
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback((query) => {
    setLoading(true);
    fetchReport(query).then(r => { setReport(r); setLoading(false); }).catch(() => setLoading(false));
  }, []);
  useEffect(() => { load(''); }, [load]);

  const rsplit = report?.remote_split || {};

  return (
    <div className="settings-panel">
      <div className="settings-header"><h2>Market Trends</h2></div>
      <p className="panel-hint">Aggregated across your tracked jobs — what the market is asking for.</p>
      <div className="search-inputs" style={{ marginBottom: '1.5rem' }}>
        <input className="filter-input search-query-input" placeholder="Filter by keyword (title / company)…"
          value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => e.key === 'Enter' && load(q)} />
        <button className="search-btn" onClick={() => load(q)} disabled={loading}>{loading ? '…' : 'Analyze'}</button>
      </div>

      {loading ? <p className="muted">Loading…</p> : !report || report.total_jobs === 0 ? (
        <p className="muted">No jobs to analyze yet — run a search first.</p>
      ) : (
        <>
          <div className="trend-stats">
            <div className="trend-stat"><div className="ts-num">{report.total_jobs}</div><div className="ts-lbl">Jobs analyzed</div></div>
            <div className="trend-stat"><div className="ts-num">{rsplit.remote || 0}</div><div className="ts-lbl">Remote</div></div>
            <div className="trend-stat"><div className="ts-num">{rsplit.hybrid || 0}</div><div className="ts-lbl">Hybrid</div></div>
            <div className="trend-stat"><div className="ts-num">{rsplit['on-site'] || 0}</div><div className="ts-lbl">On-site</div></div>
            {report.salary && (
              <div className="trend-stat trend-stat-wide">
                <div className="ts-num">{Math.round(report.salary.min / 1000)}k–{Math.round(report.salary.max / 1000)}k €</div>
                <div className="ts-lbl">Salary range ({report.salary.count})</div>
              </div>
            )}
          </div>

          <div className="card flat trend-summary"><p>{renderEmphasis(report.summary)}</p></div>

          <div className="card trend-card">
            <h3>Most requested skills</h3>
            <RankList items={report.top_skills} />
          </div>

          <div className="trends-grid">
            <div className="card trend-card">
              <h3>Top locations</h3>
              <RankList items={report.top_locations} />
            </div>
            <div className="card trend-card">
              <h3>Top companies</h3>
              <RankList items={report.top_companies} />
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export default function App() {
  const [stats, setStats] = useState({});
  const [jobs, setJobs] = useState([]);
  const [total, setTotal] = useState(0);
  const [filters, setFilters] = useState({ limit: 20, offset: 0, sort: 'match_score_desc' });
  const [selectedJob, setSelectedJob] = useState(null);
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('jobs');

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [statsData, jobsData, healthData] = await Promise.all([
        fetchStats(),
        fetchJobs(filters),
        fetchHealth(),
      ]);
      setStats(statsData);
      setJobs(jobsData.items || []);
      setTotal(jobsData.total || 0);
      setHealth(healthData);
    } catch (err) {
      console.error('Failed to load data:', err);
    }
    setLoading(false);
  }, [filters]);

  useEffect(() => { loadData(); }, [loadData]);

  const handleStatusChange = async (applicationId, newStatus) => {
    await updateApplication(applicationId, { status: newStatus });
    loadData();
  };

  const handleStatFilter = (status) => {
    setFilters(f => ({ ...f, offset: 0, status: status || undefined }));
  };

  const handleClearAll = async () => {
    if (!window.confirm(`Delete ALL ${total} tracked job(s)? This cannot be undone.`)) return;
    try {
      await deleteAllJobs();
      setFilters(f => ({ ...f, offset: 0 }));
      loadData();
    } catch (err) {
      alert(`Failed to delete: ${err.message}`);
    }
  };

  const totalPages = Math.ceil(total / (filters.limit || 20));
  const currentPage = Math.floor((filters.offset || 0) / (filters.limit || 20)) + 1;

  return (
    <div className="app">
      <header className="header">
        <div className="header-left">
          <h1>keinplan<span className="logo-accent">karriere</span></h1>
          <nav className="header-tabs">
            <button className={`tab-btn ${tab === 'jobs' ? 'active' : ''}`} onClick={() => setTab('jobs')}>Jobs</button>
            <button className={`tab-btn ${tab === 'experience' ? 'active' : ''}`} onClick={() => setTab('experience')}>Experience</button>
            <button className={`tab-btn ${tab === 'trends' ? 'active' : ''}`} onClick={() => setTab('trends')}>Trends</button>
            <button className={`tab-btn ${tab === 'settings' ? 'active' : ''}`} onClick={() => setTab('settings')}>Settings</button>
          </nav>
        </div>
        <div className="header-right">
          {health && (
            <span className="health-dot" title={`API: ${health.status}, ${health.jobs_count} jobs`}>
              {health.jobs_count} jobs tracked
            </span>
          )}
          {tab === 'jobs' && (
            <>
              <button className="refresh-btn danger-btn" onClick={handleClearAll} disabled={loading || total === 0}>
                Clear all
              </button>
              <button className="refresh-btn" onClick={loadData} disabled={loading}>
                {loading ? '...' : 'Refresh'}
              </button>
            </>
          )}
        </div>
      </header>

      {tab === 'settings' ? (
        <SettingsPanel />
      ) : tab === 'experience' ? (
        <ExperiencePanel />
      ) : tab === 'trends' ? (
        <TrendsPanel />
      ) : (
        <>
          <SearchPanel onComplete={loadData} />
          <ScoreBar onComplete={loadData} />
          <StatsBar stats={stats} onFilter={handleStatFilter} />
          <Filters filters={filters} onChange={setFilters} />

          <div className="table-container">
            <table className="jobs-table">
              <thead>
                <tr>
                  <th>Job</th>
                  <th>Location</th>
                  <th>Source</th>
                  <th>Remote</th>
                  <th>Score</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map(job => (
                  <JobRow
                    key={job.id}
                    job={job}
                    onSelect={setSelectedJob}
                    onStatusChange={handleStatusChange}
                  />
                ))}
                {jobs.length === 0 && !loading && (
                  <tr><td colSpan="6" className="empty-row">
                    <div className="onboarding">
                      <strong>Welcome — your workspace is empty.</strong>
                      <ol>
                        <li>Add your background in the <b>Experience</b> tab (upload a CV or add entries)</li>
                        <li>Run a <b>Search</b> above to pull jobs from the four boards</li>
                        <li>Hit <b>Score all jobs</b> to rank them against you</li>
                        <li>Open a job → <b>Prepare application</b> for a tailored CV + cover letter</li>
                      </ol>
                    </div>
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="pagination">
            <button
              disabled={currentPage <= 1}
              onClick={() => setFilters(f => ({ ...f, offset: Math.max(0, (f.offset || 0) - (f.limit || 20)) }))}
            >
              Previous
            </button>
            <span>Page {currentPage} of {totalPages || 1} ({total} total)</span>
            <button
              disabled={currentPage >= totalPages}
              onClick={() => setFilters(f => ({ ...f, offset: (f.offset || 0) + (f.limit || 20) }))}
            >
              Next
            </button>
          </div>

          <JobDetail
            job={selectedJob}
            onClose={() => setSelectedJob(null)}
            onStatusChange={handleStatusChange}
            onGenerated={async () => {
              if (!selectedJob) return;
              const fresh = await fetchJob(selectedJob.job_id);
              if (fresh && fresh.id) setSelectedJob(fresh);
              loadData();
            }}
          />
        </>
      )}
    </div>
  );
}
