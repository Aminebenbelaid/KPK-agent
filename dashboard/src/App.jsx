import { useState, useEffect, useCallback, useRef } from 'react';
import { fetchStats, fetchJobs, updateApplication, fetchHealth, triggerScrape, getScrapeStatus, fetchSettings, saveSettings } from './api';
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

function JobDetail({ job, onClose }) {
  if (!job) return null;
  const data = job.job_data || {};
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
        <div className="detail-section">
          <h3>Skills & Technologies</h3>
          <div className="tag-list">
            {(data.skills_required || []).map((s, i) => <span key={i} className="tech-tag">{s}</span>)}
          </div>
        </div>
        {job.match_details && (
          <div className="detail-section">
            <h3>Match Details</h3>
            <pre className="match-json">{JSON.stringify(job.match_details, null, 2)}</pre>
          </div>
        )}
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
      setScrapeState({ taskId: res.task_id, status: 'running', error: null });

      pollRef.current = setInterval(async () => {
        try {
          const status = await getScrapeStatus(res.task_id);
          setScrapeState(prev => ({ ...prev, status: status.status, result: status.result }));
          if (status.status !== 'running' && status.status !== 'starting') {
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

  const isRunning = scrapeState?.status === 'running' || scrapeState?.status === 'starting';

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
          {isRunning ? 'Searching...' : 'Search'}
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
          <span>Scraping {selected.length} source{selected.length > 1 ? 's' : ''} in parallel...</span>
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
        <option value="indeed">Indeed</option>
        <option value="stepstone">StepStone</option>
        <option value="arbeitsagentur">Arbeitsagentur</option>
        <option value="xing">Xing</option>
        <option value="remotive">Remotive</option>
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

const SETTING_FIELDS = [
  { key: 'kisski_api_key', label: 'Kisski API Key', type: 'password', placeholder: 'Your Kisski LLM API key' },
  { key: 'kisski_base_url', label: 'Kisski Base URL', type: 'text', placeholder: 'https://chat-ai.academiccloud.de/v1' },
  { key: 'llm_model', label: 'LLM Model', type: 'text', placeholder: 'meta-llama/llama-3.3-70b-instruct' },
  { key: 'internal_api_key', label: 'Internal API Key', type: 'password', placeholder: 'Key for scraper auth' },
  { key: 'scraper_default_location', label: 'Default Location', type: 'text', placeholder: 'Nordrhein-Westfalen' },
  { key: 'scraper_max_jobs', label: 'Max Jobs per Scraper', type: 'number', placeholder: '10' },
];

function SettingsPanel() {
  const [values, setValues] = useState({});
  const [loading, setLoading] = useState(true);
  const [saved, setSaved] = useState(false);
  const [showPasswords, setShowPasswords] = useState({});

  useEffect(() => {
    fetchSettings().then(data => {
      setValues(data);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    const toSave = {};
    for (const field of SETTING_FIELDS) {
      const val = values[field.key];
      if (val && !val.includes('****')) {
        toSave[field.key] = val;
      }
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
      <div className="settings-grid">
        {SETTING_FIELDS.map(field => (
          <div key={field.key} className="setting-row">
            <label className="setting-label">{field.label}</label>
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
          </div>
        ))}
      </div>
      <button className="search-btn settings-save-btn" onClick={handleSave}>Save Settings</button>
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

  const totalPages = Math.ceil(total / (filters.limit || 20));
  const currentPage = Math.floor((filters.offset || 0) / (filters.limit || 20)) + 1;

  return (
    <div className="app">
      <header className="header">
        <div className="header-left">
          <h1>keinplan<span className="logo-accent">karriere</span></h1>
          <nav className="header-tabs">
            <button className={`tab-btn ${tab === 'jobs' ? 'active' : ''}`} onClick={() => setTab('jobs')}>Jobs</button>
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
            <button className="refresh-btn" onClick={loadData} disabled={loading}>
              {loading ? '...' : 'Refresh'}
            </button>
          )}
        </div>
      </header>

      {tab === 'settings' ? (
        <SettingsPanel />
      ) : (
        <>
          <SearchPanel onComplete={loadData} />
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
                  <tr><td colSpan="6" className="empty-row">No jobs found</td></tr>
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

          <JobDetail job={selectedJob} onClose={() => setSelectedJob(null)} />
        </>
      )}
    </div>
  );
}
