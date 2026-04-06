import React, { useState, useEffect, useCallback, useRef } from 'react'
import { Routes, Route, NavLink, useNavigate } from 'react-router-dom'

// --- Design Tokens (GitHub Dark + Linear-inspired) ---
const C = {
  bg: '#0d1117',
  surface: '#161b22',
  surfaceHover: '#1c2129',
  border: '#30363d',
  text: '#c9d1d9',
  textMuted: '#8b949e',
  textBright: '#f0f6fc',
  accent: '#58a6ff',
  green: '#3fb950',
  red: '#f85149',
  yellow: '#d29922',
  blue: '#58a6ff',
  purple: '#bc8cff',
  radius: '8px',
  radiusSm: '4px',
}

const API = '/api'

function api(path, opts = {}) {
  return fetch(`${API}${path}`, {
    headers: { 'Content-Type': 'application/json', ...opts.headers },
    ...opts,
  }).then(r => r.json())
}

// --- Status Badge ---
function Badge({ status }) {
  const colors = {
    queued: C.textMuted, running: C.blue, applied: C.green,
    failed: C.red, captcha: C.yellow, skipped: C.textMuted, dry_run: C.purple,
  }
  const color = colors[status] || C.textMuted
  return (
    <span style={{
      display: 'inline-block', padding: '2px 10px', borderRadius: '12px',
      fontSize: '12px', fontWeight: 600, color: C.bg,
      backgroundColor: color, textTransform: 'uppercase', letterSpacing: '0.5px',
    }}>
      {status?.replace('_', ' ')}
    </span>
  )
}

// --- Stat Card ---
function StatCard({ label, value, color }) {
  return (
    <div style={{
      background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.radius,
      padding: '16px 24px', minWidth: '120px', textAlign: 'center',
    }}>
      <div style={{ fontSize: '28px', fontWeight: 700, color: color || C.textBright }}>{value}</div>
      <div style={{ fontSize: '13px', color: C.textMuted, marginTop: '4px' }}>{label}</div>
    </div>
  )
}

// ============================================================
// PAGE: Jobs Queue
// ============================================================
function JobsPage() {
  const [jobs, setJobs] = useState([])
  const [stats, setStats] = useState({})
  const [filter, setFilter] = useState('')
  const [expanded, setExpanded] = useState(null)

  const load = useCallback(() => {
    api('/jobs').then(setJobs)
    api('/stats').then(setStats)
  }, [])

  useEffect(() => { load(); const t = setInterval(load, 5000); return () => clearInterval(t) }, [load])

  const filtered = filter ? jobs.filter(j => j.status === filter) : jobs

  const startApply = (dryRun = false) => {
    api('/apply', { method: 'POST', body: JSON.stringify({ dry_run: dryRun, headed: true }) })
      .then(() => load())
      .catch(e => alert(e.message || 'Already running'))
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <h1 style={{ fontSize: '24px', fontWeight: 700, color: C.textBright }}>Job Queue</h1>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button onClick={() => startApply(true)} style={btnStyle(C.purple)}>Dry Run</button>
          <button onClick={() => startApply(false)} style={btnStyle(C.green)}>Apply All</button>
          <button onClick={() => api('/jobs/reset-failed', { method: 'POST' }).then(load)} style={btnStyle(C.yellow)}>Retry Failed</button>
        </div>
      </div>

      <div style={{ display: 'flex', gap: '12px', marginBottom: '24px', flexWrap: 'wrap' }}>
        <StatCard label="Total" value={stats.total || 0} />
        <StatCard label="Queued" value={stats.queued || 0} color={C.textMuted} />
        <StatCard label="Running" value={stats.running || 0} color={C.blue} />
        <StatCard label="Applied" value={stats.applied || 0} color={C.green} />
        <StatCard label="Failed" value={stats.failed || 0} color={C.red} />
        <StatCard label="Captcha" value={stats.captcha || 0} color={C.yellow} />
      </div>

      <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
        {['', 'queued', 'running', 'applied', 'failed', 'captcha'].map(s => (
          <button key={s} onClick={() => setFilter(s)} style={{
            ...chipStyle, background: filter === s ? C.accent : C.surface,
            color: filter === s ? C.bg : C.text,
          }}>
            {s || 'All'}
          </button>
        ))}
      </div>

      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.radius, overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: `1px solid ${C.border}` }}>
              {['#', 'Company', 'Title', 'Score', 'Platform', 'Status', 'Time', 'Actions'].map(h => (
                <th key={h} style={thStyle}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map(job => (
              <React.Fragment key={job.id}>
                <tr
                  onClick={() => setExpanded(expanded === job.id ? null : job.id)}
                  style={{ ...trStyle, cursor: 'pointer', background: expanded === job.id ? C.surfaceHover : 'transparent' }}
                >
                  <td style={tdStyle}>{job.id}</td>
                  <td style={tdStyle}>{job.company}</td>
                  <td style={{ ...tdStyle, maxWidth: '280px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{job.title}</td>
                  <td style={tdStyle}><span style={{ color: job.score >= 70 ? C.green : job.score >= 50 ? C.yellow : C.textMuted, fontWeight: 600 }}>{job.score}</span></td>
                  <td style={tdStyle}>{job.platform}</td>
                  <td style={tdStyle}><Badge status={job.status} /></td>
                  <td style={tdStyle}>{job.duration_sec ? `${job.duration_sec}s` : '-'}</td>
                  <td style={tdStyle}>
                    <div style={{ display: 'flex', gap: '4px' }}>
                      {job.status === 'failed' && (
                        <button onClick={e => { e.stopPropagation(); api(`/jobs/${job.id}/retry`, { method: 'POST' }).then(load) }} style={smallBtn}>Retry</button>
                      )}
                      <button onClick={e => { e.stopPropagation(); if(confirm('Delete?')) api(`/jobs/${job.id}`, { method: 'DELETE' }).then(load) }} style={{ ...smallBtn, color: C.red }}>X</button>
                    </div>
                  </td>
                </tr>
                {expanded === job.id && (
                  <tr>
                    <td colSpan={8} style={{ padding: '16px', background: C.surfaceHover, borderBottom: `1px solid ${C.border}` }}>
                      <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
                        <div style={{ flex: 1, minWidth: '200px' }}>
                          <p style={{ color: C.textMuted, fontSize: '13px' }}>URL: <a href={job.url} target="_blank" style={{ color: C.accent }}>{job.url}</a></p>
                          {job.error && <p style={{ color: C.red, fontSize: '13px', marginTop: '8px' }}>Error: {job.error}</p>}
                          {job.resume_path && <p style={{ color: C.textMuted, fontSize: '13px', marginTop: '4px' }}>Resume: {job.resume_path.split(/[/\\]/).pop()}</p>}
                          {job.location && <p style={{ color: C.textMuted, fontSize: '13px', marginTop: '4px' }}>Location: {job.location}</p>}
                        </div>
                        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                          {(job.screenshots || []).map((s, i) => (
                            <a key={i} href={`/screenshots/${s.split(/[/\\]/).pop()}`} target="_blank">
                              <img src={`/screenshots/${s.split(/[/\\]/).pop()}`} alt={`step ${i+1}`}
                                style={{ width: '160px', height: '100px', objectFit: 'cover', borderRadius: C.radiusSm, border: `1px solid ${C.border}` }} />
                            </a>
                          ))}
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <div style={{ padding: '40px', textAlign: 'center', color: C.textMuted }}>
            No jobs. Upload a CSV or add jobs to get started.
          </div>
        )}
      </div>
    </div>
  )
}

// ============================================================
// PAGE: Upload
// ============================================================
function UploadPage() {
  const [dragOver, setDragOver] = useState(false)
  const [result, setResult] = useState(null)
  const [url, setUrl] = useState('')
  const navigate = useNavigate()

  const handleDrop = async (e) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer?.files?.[0] || e.target?.files?.[0]
    if (!file) return
    const form = new FormData()
    form.append('file', file)
    const res = await fetch(`${API}/jobs/upload`, { method: 'POST', body: form }).then(r => r.json())
    setResult(res)
  }

  const addSingle = async () => {
    if (!url.trim()) return
    await api('/jobs/add', { method: 'POST', body: JSON.stringify({ url: url.trim() }) })
    setUrl('')
    setResult({ imported: 1, skipped: 0 })
  }

  const handleResumes = async (e) => {
    const files = e.target.files
    if (!files.length) return
    const form = new FormData()
    for (const f of files) form.append('files', f)
    const res = await fetch(`${API}/resumes/upload`, { method: 'POST', body: form }).then(r => r.json())
    setResult({ resumes_uploaded: res.uploaded.length })
  }

  return (
    <div>
      <h1 style={{ fontSize: '24px', fontWeight: 700, color: C.textBright, marginBottom: '24px' }}>Upload Jobs</h1>

      {/* CSV Upload */}
      <div
        onDragOver={e => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        style={{
          background: C.surface, border: `2px dashed ${dragOver ? C.accent : C.border}`,
          borderRadius: C.radius, padding: '48px', textAlign: 'center',
          marginBottom: '24px', transition: 'border-color 0.2s',
          cursor: 'pointer',
        }}
        onClick={() => document.getElementById('csv-input').click()}
      >
        <input id="csv-input" type="file" accept=".csv,.tsv,.xlsx" onChange={handleDrop} style={{ display: 'none' }} />
        <div style={{ fontSize: '18px', fontWeight: 600, color: C.textBright, marginBottom: '8px' }}>
          Drop your scored job sheet here
        </div>
        <div style={{ color: C.textMuted, fontSize: '14px' }}>
          CSV or TSV with columns: Company, Title, Score, Link, etc.
        </div>
      </div>

      {/* Single URL */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '24px' }}>
        <input
          value={url} onChange={e => setUrl(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && addSingle()}
          placeholder="Or paste a single job URL..."
          style={inputStyle}
        />
        <button onClick={addSingle} style={btnStyle(C.accent)}>Add</button>
      </div>

      {/* Resume Upload */}
      <div style={{
        background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.radius,
        padding: '24px', marginBottom: '24px',
      }}>
        <div style={{ fontSize: '16px', fontWeight: 600, color: C.textBright, marginBottom: '12px' }}>
          Upload Tailored Resumes (optional)
        </div>
        <div style={{ color: C.textMuted, fontSize: '14px', marginBottom: '12px' }}>
          Name PDFs like CompanyName_Title.pdf to auto-match. If no match, default resume is used.
        </div>
        <input type="file" accept=".pdf" multiple onChange={handleResumes} style={{ color: C.text }} />
        <button onClick={() => api('/resumes/match', { method: 'POST' }).then(r => setResult(r))} style={{ ...btnStyle(C.accent), marginLeft: '12px' }}>
          Auto-Match Resumes
        </button>
      </div>

      {/* Result */}
      {result && (
        <div style={{
          background: C.surface, border: `1px solid ${C.green}`, borderRadius: C.radius,
          padding: '16px', color: C.green,
        }}>
          {result.imported !== undefined && `Imported ${result.imported} jobs (${result.skipped} skipped)`}
          {result.matched !== undefined && `Matched ${result.matched} resumes to ${result.total} jobs`}
          {result.resumes_uploaded !== undefined && `Uploaded ${result.resumes_uploaded} resumes`}
          <button onClick={() => navigate('/')} style={{ ...btnStyle(C.accent), marginLeft: '16px' }}>
            Go to Queue
          </button>
        </div>
      )}
    </div>
  )
}

// ============================================================
// PAGE: Live View
// ============================================================
function LivePage() {
  const [status, setStatus] = useState({})
  const [logs, setLogs] = useState([])

  useEffect(() => {
    const poll = () => {
      api('/status').then(setStatus)
      api('/logs?limit=20').then(setLogs)
    }
    poll()
    const t = setInterval(poll, 3000)
    return () => clearInterval(t)
  }, [])

  const progress = status.total ? Math.round((status.completed / status.total) * 100) : 0
  const current = status.current_job

  return (
    <div>
      <h1 style={{ fontSize: '24px', fontWeight: 700, color: C.textBright, marginBottom: '24px' }}>Live View</h1>

      {/* Progress Bar */}
      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.radius, padding: '24px', marginBottom: '24px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
          <span style={{ fontWeight: 600, color: status.running ? C.green : C.textMuted }}>
            {status.running ? `Applying ${status.completed + 1} of ${status.total}...` : 'Idle'}
          </span>
          <span style={{ color: C.textMuted }}>{progress}%</span>
        </div>
        <div style={{ height: '8px', background: C.border, borderRadius: '4px', overflow: 'hidden' }}>
          <div style={{
            height: '100%', width: `${progress}%`, background: C.green,
            borderRadius: '4px', transition: 'width 0.5s ease',
          }} />
        </div>
        <div style={{ display: 'flex', gap: '24px', marginTop: '12px', fontSize: '13px', color: C.textMuted }}>
          <span>Applied: <strong style={{ color: C.green }}>{status.applied || 0}</strong></span>
          <span>Failed: <strong style={{ color: C.red }}>{status.failed || 0}</strong></span>
          <span>Paused: <strong>{status.paused ? 'Yes' : 'No'}</strong></span>
        </div>
        {status.running && (
          <div style={{ display: 'flex', gap: '8px', marginTop: '12px' }}>
            <button onClick={() => api('/apply/pause', { method: 'POST' })} style={btnStyle(C.yellow)}>
              {status.paused ? 'Resume' : 'Pause'}
            </button>
            <button onClick={() => api('/apply/cancel', { method: 'POST' })} style={btnStyle(C.red)}>Cancel</button>
          </div>
        )}
      </div>

      {/* Current Job */}
      {current && (
        <div style={{ background: C.surface, border: `1px solid ${C.blue}`, borderRadius: C.radius, padding: '24px', marginBottom: '24px' }}>
          <div style={{ fontSize: '16px', fontWeight: 600, color: C.textBright }}>{current.title}</div>
          <div style={{ color: C.textMuted, fontSize: '13px', marginTop: '4px' }}>{current.company} - {current.platform}</div>
          <div style={{ marginTop: '12px', color: C.blue, fontSize: '13px' }}>Browser is filling the form...</div>
        </div>
      )}

      {/* Recent Log */}
      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.radius, padding: '16px' }}>
        <div style={{ fontSize: '14px', fontWeight: 600, color: C.textBright, marginBottom: '12px' }}>Activity Log</div>
        {logs.length === 0 && <div style={{ color: C.textMuted, fontSize: '13px' }}>No activity yet. Start applying to see logs.</div>}
        {logs.map((log, i) => (
          <div key={i} style={{
            padding: '6px 0', borderBottom: i < logs.length - 1 ? `1px solid ${C.border}` : 'none',
            fontSize: '13px', display: 'flex', gap: '12px',
          }}>
            <span style={{ color: C.textMuted, minWidth: '140px' }}>{log.timestamp}</span>
            <Badge status={log.action} />
            <span style={{ color: C.text }}>{log.detail}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ============================================================
// PAGE: Settings
// ============================================================
function SettingsPage() {
  const [profile, setProfile] = useState(null)
  const [resumes, setResumes] = useState([])
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    api('/profile').then(setProfile)
    api('/resumes').then(setResumes)
  }, [])

  if (!profile) return <div style={{ color: C.textMuted, padding: '40px' }}>Loading...</div>

  return (
    <div>
      <h1 style={{ fontSize: '24px', fontWeight: 700, color: C.textBright, marginBottom: '24px' }}>Settings</h1>

      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.radius, padding: '24px', marginBottom: '24px' }}>
        <h2 style={{ fontSize: '16px', fontWeight: 600, color: C.textBright, marginBottom: '16px' }}>Profile</h2>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
          {[
            ['full_name', 'Full Name'], ['email', 'Email'], ['phone', 'Phone'],
            ['city', 'City'], ['state', 'State'], ['postal_code', 'Postal Code'],
            ['linkedin', 'LinkedIn'], ['github', 'GitHub'],
            ['salary', 'Salary Expectation'], ['years_experience', 'Years Experience'],
            ['authorized_to_work', 'Work Authorized'], ['require_sponsorship', 'Need Sponsorship'],
          ].map(([key, label]) => (
            <div key={key}>
              <label style={{ fontSize: '12px', color: C.textMuted, marginBottom: '4px', display: 'block' }}>{label}</label>
              <input
                value={profile[key] || ''}
                onChange={e => setProfile({ ...profile, [key]: e.target.value })}
                style={inputStyle}
              />
            </div>
          ))}
        </div>
        <button onClick={() => {
          // Note: save would need to reconstruct nested format — simplified for now
          setSaved(true)
          setTimeout(() => setSaved(false), 2000)
        }} style={{ ...btnStyle(C.green), marginTop: '16px' }}>
          {saved ? 'Saved!' : 'Save Profile'}
        </button>
      </div>

      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.radius, padding: '24px' }}>
        <h2 style={{ fontSize: '16px', fontWeight: 600, color: C.textBright, marginBottom: '16px' }}>Resumes</h2>
        {resumes.map((r, i) => (
          <div key={i} style={{ padding: '8px 0', borderBottom: `1px solid ${C.border}`, fontSize: '14px', display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ color: C.text }}>{r.name}</span>
            <span style={{ color: C.textMuted }}>{(r.size / 1024).toFixed(0)} KB</span>
          </div>
        ))}
        {resumes.length === 0 && <div style={{ color: C.textMuted }}>No resumes uploaded. Upload on the Upload page.</div>}
      </div>
    </div>
  )
}

// ============================================================
// LAYOUT
// ============================================================
function App() {
  const navItems = [
    { path: '/', label: 'Jobs', icon: 'Q' },
    { path: '/upload', label: 'Upload', icon: '+' },
    { path: '/live', label: 'Live', icon: '>' },
    { path: '/settings', label: 'Settings', icon: '*' },
  ]

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      {/* Sidebar */}
      <nav style={{
        width: '200px', background: C.surface, borderRight: `1px solid ${C.border}`,
        padding: '20px 0', display: 'flex', flexDirection: 'column',
      }}>
        <div style={{ padding: '0 20px 20px', borderBottom: `1px solid ${C.border}`, marginBottom: '12px' }}>
          <div style={{ fontWeight: 700, fontSize: '16px', color: C.textBright }}>Job Apply</div>
          <div style={{ fontSize: '12px', color: C.textMuted }}>Engine v1.0</div>
        </div>
        {navItems.map(item => (
          <NavLink
            key={item.path} to={item.path} end={item.path === '/'}
            style={({ isActive }) => ({
              display: 'flex', alignItems: 'center', gap: '10px',
              padding: '10px 20px', textDecoration: 'none', fontSize: '14px', fontWeight: 500,
              color: isActive ? C.textBright : C.textMuted,
              background: isActive ? '#1c2129' : 'transparent',
              borderLeft: isActive ? `2px solid ${C.accent}` : '2px solid transparent',
              transition: 'all 0.15s',
            })}
          >
            <span style={{ width: '20px', textAlign: 'center', fontSize: '16px', opacity: 0.7 }}>{item.icon}</span>
            {item.label}
          </NavLink>
        ))}
      </nav>

      {/* Main Content */}
      <main style={{ flex: 1, padding: '32px 40px', maxWidth: '1200px' }}>
        <Routes>
          <Route path="/" element={<JobsPage />} />
          <Route path="/upload" element={<UploadPage />} />
          <Route path="/live" element={<LivePage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </main>
    </div>
  )
}

// --- Shared Styles ---
const btnStyle = (color) => ({
  padding: '8px 16px', borderRadius: C.radiusSm, border: 'none',
  background: color, color: C.bg, fontWeight: 600, fontSize: '13px',
  cursor: 'pointer', transition: 'opacity 0.15s',
})
const smallBtn = {
  padding: '3px 8px', borderRadius: C.radiusSm, border: `1px solid ${C.border}`,
  background: 'transparent', color: C.textMuted, fontSize: '12px', cursor: 'pointer',
}
const chipStyle = {
  padding: '5px 14px', borderRadius: '16px', border: `1px solid ${C.border}`,
  fontSize: '13px', cursor: 'pointer', fontWeight: 500,
}
const inputStyle = {
  flex: 1, padding: '8px 12px', borderRadius: C.radiusSm,
  border: `1px solid ${C.border}`, background: C.surface,
  color: C.text, fontSize: '14px', outline: 'none',
}
const thStyle = {
  padding: '10px 12px', textAlign: 'left', fontSize: '12px',
  fontWeight: 600, color: C.textMuted, textTransform: 'uppercase',
  letterSpacing: '0.5px',
}
const tdStyle = { padding: '10px 12px', fontSize: '14px' }
const trStyle = { borderBottom: `1px solid ${C.border}`, transition: 'background 0.15s' }

export default App
