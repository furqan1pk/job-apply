import React, { useState, useEffect, useCallback } from 'react'
import { Routes, Route, NavLink, useNavigate } from 'react-router-dom'

const C = {
  bg: '#0d1117', surface: '#161b22', surfaceHover: '#1c2129',
  border: '#30363d', text: '#c9d1d9', textMuted: '#8b949e', textBright: '#f0f6fc',
  accent: '#58a6ff', green: '#3fb950', red: '#f85149', yellow: '#d29922',
  blue: '#58a6ff', purple: '#bc8cff', radius: '8px', radiusSm: '4px',
}
const API = '/api'
function api(path, opts = {}) {
  return fetch(`${API}${path}`, { headers: { 'Content-Type': 'application/json', ...opts.headers }, ...opts }).then(r => r.json())
}
function Badge({ status }) {
  const colors = { queued: C.textMuted, running: C.blue, applied: C.green, failed: C.red, captcha: C.yellow, skipped: '#484f58', dry_run: C.purple }
  return <span style={{ display: 'inline-block', padding: '2px 10px', borderRadius: '12px', fontSize: '11px', fontWeight: 600, color: C.bg, backgroundColor: colors[status] || C.textMuted, textTransform: 'uppercase', letterSpacing: '0.5px' }}>{status?.replace('_', ' ')}</span>
}
function StatCard({ label, value, color }) {
  return <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.radius, padding: '14px 20px', minWidth: '100px', textAlign: 'center' }}>
    <div style={{ fontSize: '24px', fontWeight: 700, color: color || C.textBright }}>{value}</div>
    <div style={{ fontSize: '12px', color: C.textMuted, marginTop: '2px' }}>{label}</div>
  </div>
}

// ============================================================
// JOBS PAGE — with checkboxes, per-row actions, bulk operations
// ============================================================
function JobsPage() {
  const [jobs, setJobs] = useState([])
  const [stats, setStats] = useState({})
  const [filter, setFilter] = useState('')
  const [expanded, setExpanded] = useState(null)
  const [review, setReview] = useState(null)
  const [selected, setSelected] = useState(new Set())

  const load = useCallback(() => { api('/jobs').then(setJobs); api('/stats').then(setStats) }, [])
  useEffect(() => { load(); const t = setInterval(load, 5000); return () => clearInterval(t) }, [load])

  const filtered = filter ? jobs.filter(j => j.status === filter) : jobs
  const allChecked = filtered.length > 0 && filtered.every(j => selected.has(j.id))

  const toggleAll = () => {
    if (allChecked) setSelected(new Set())
    else setSelected(new Set(filtered.map(j => j.id)))
  }
  const toggle = (id) => {
    const s = new Set(selected)
    s.has(id) ? s.delete(id) : s.add(id)
    setSelected(s)
  }

  const applySelected = (dryRun) => {
    const ids = [...selected]
    if (!ids.length) return alert('Select jobs first')
    api('/jobs/apply-selected?dry_run=' + dryRun + '&headed=true', { method: 'POST', body: JSON.stringify({ job_ids: ids }) })
      .then(() => { load(); setSelected(new Set()) })
      .catch(e => alert(e.message || 'Error'))
  }

  const applyAll = (dryRun) => {
    api('/apply', { method: 'POST', body: JSON.stringify({ dry_run: dryRun, headed: true }) })
      .then(() => load()).catch(e => alert(e.message || 'Already running'))
  }

  const removeSelected = () => {
    if (!selected.size || !confirm(`Delete ${selected.size} jobs?`)) return
    api('/jobs/remove-selected', { method: 'POST', body: JSON.stringify({ job_ids: [...selected] }) })
      .then(() => { load(); setSelected(new Set()) })
  }

  const act = (e, id, action) => {
    e.stopPropagation()
    const actions = {
      retry: () => api(`/jobs/${id}/retry`, { method: 'POST' }),
      skip: () => api(`/jobs/${id}/skip`, { method: 'POST' }),
      markApplied: () => api(`/jobs/${id}/mark-applied`, { method: 'POST' }),
      applyOne: () => api(`/jobs/${id}/apply-one?headed=true`, { method: 'POST' }),
      dryOne: () => api(`/jobs/${id}/apply-one?dry_run=true&headed=true`, { method: 'POST' }),
      delete: () => confirm('Delete?') && api(`/jobs/${id}`, { method: 'DELETE' }),
    }
    actions[action]?.().then(load)
  }

  const actionBtns = (job) => {
    const s = job.status
    const btns = []
    if (s === 'queued') {
      btns.push(<button key="a" onClick={e => act(e, job.id, 'applyOne')} style={{ ...sBtn, color: C.green }}>Apply</button>)
      btns.push(<button key="d" onClick={e => act(e, job.id, 'dryOne')} style={{ ...sBtn, color: C.purple }}>Dry</button>)
      btns.push(<button key="s" onClick={e => act(e, job.id, 'skip')} style={sBtn}>Skip</button>)
    }
    if (s === 'dry_run') {
      btns.push(<button key="a" onClick={e => act(e, job.id, 'applyOne')} style={{ ...sBtn, color: C.green }}>Submit</button>)
    }
    if (s === 'failed' || s === 'captcha') {
      btns.push(<button key="r" onClick={e => act(e, job.id, 'retry')} style={{ ...sBtn, color: C.yellow }}>Retry</button>)
    }
    if (s === 'queued' || s === 'dry_run') {
      btns.push(<button key="m" onClick={e => act(e, job.id, 'markApplied')} style={{ ...sBtn, color: C.textMuted }}>Done</button>)
    }
    if (s === 'skipped') {
      btns.push(<button key="q" onClick={e => act(e, job.id, 'retry')} style={{ ...sBtn, color: C.accent }}>Requeue</button>)
    }
    btns.push(<button key="x" onClick={e => act(e, job.id, 'delete')} style={{ ...sBtn, color: C.red }}>X</button>)
    return <div style={{ display: 'flex', gap: '3px', flexWrap: 'wrap' }}>{btns}</div>
  }

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <h1 style={{ fontSize: '22px', fontWeight: 700, color: C.textBright }}>Job Queue</h1>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <a href="/api/jobs/export" style={{ ...btnStyle(C.textMuted), textDecoration: 'none', fontSize: '12px' }}>Export CSV</a>
          <button onClick={() => api('/jobs/reset-failed', { method: 'POST' }).then(load)} style={btnStyle(C.yellow)}>Retry Failed</button>
          <button onClick={() => applyAll(true)} style={btnStyle(C.purple)}>Dry Run All</button>
          <button onClick={() => applyAll(false)} style={btnStyle(C.green)}>Apply All</button>
        </div>
      </div>

      {/* Stats */}
      <div style={{ display: 'flex', gap: '10px', marginBottom: '20px', flexWrap: 'wrap' }}>
        <StatCard label="Total" value={stats.total || 0} />
        <StatCard label="Queued" value={stats.queued || 0} color={C.textMuted} />
        <StatCard label="Running" value={stats.running || 0} color={C.blue} />
        <StatCard label="Applied" value={stats.applied || 0} color={C.green} />
        <StatCard label="Failed" value={stats.failed || 0} color={C.red} />
        <StatCard label="Captcha" value={stats.captcha || 0} color={C.yellow} />
      </div>

      {/* Bulk actions bar (shows when items selected) */}
      {selected.size > 0 && (
        <div style={{ background: C.accent + '15', border: `1px solid ${C.accent}40`, borderRadius: C.radius, padding: '10px 16px', marginBottom: '12px', display: 'flex', gap: '8px', alignItems: 'center' }}>
          <span style={{ color: C.accent, fontWeight: 600, fontSize: '13px' }}>{selected.size} selected</span>
          <button onClick={() => applySelected(false)} style={btnStyle(C.green)}>Apply Selected</button>
          <button onClick={() => applySelected(true)} style={btnStyle(C.purple)}>Dry Run Selected</button>
          <button onClick={removeSelected} style={btnStyle(C.red)}>Remove</button>
          <button onClick={() => setSelected(new Set())} style={{ ...sBtn, marginLeft: 'auto' }}>Clear</button>
        </div>
      )}

      {/* Filters */}
      <div style={{ display: 'flex', gap: '6px', marginBottom: '12px' }}>
        {['', 'queued', 'running', 'applied', 'dry_run', 'failed', 'captcha', 'skipped'].map(s => (
          <button key={s} onClick={() => setFilter(s)} style={{ ...chipStyle, background: filter === s ? C.accent : C.surface, color: filter === s ? C.bg : C.text }}>{s || 'All'}</button>
        ))}
      </div>

      {/* Table */}
      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.radius, overflow: 'hidden' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr style={{ borderBottom: `1px solid ${C.border}` }}>
              <th style={{ ...thStyle, width: '30px' }}><input type="checkbox" checked={allChecked} onChange={toggleAll} /></th>
              {['Company', 'Title', 'Score', 'Platform', 'Status', 'Time', 'Actions'].map(h => <th key={h} style={thStyle}>{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {filtered.map(job => (
              <React.Fragment key={job.id}>
                <tr onClick={() => { const n = expanded === job.id ? null : job.id; setExpanded(n); if (n) api(`/jobs/${job.id}/review`).then(setReview); else setReview(null) }}
                  style={{ ...trStyle, cursor: 'pointer', background: expanded === job.id ? C.surfaceHover : 'transparent' }}>
                  <td style={tdStyle}><input type="checkbox" checked={selected.has(job.id)} onChange={() => toggle(job.id)} onClick={e => e.stopPropagation()} /></td>
                  <td style={tdStyle}>{job.company}</td>
                  <td style={{ ...tdStyle, maxWidth: '250px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{job.title}</td>
                  <td style={tdStyle}><span style={{ color: job.score >= 80 ? C.green : job.score >= 70 ? C.yellow : C.textMuted, fontWeight: 600 }}>{job.score}</span></td>
                  <td style={tdStyle}>{job.platform}</td>
                  <td style={tdStyle}><Badge status={job.status} /></td>
                  <td style={tdStyle}>{job.duration_sec ? `${job.duration_sec}s` : '-'}</td>
                  <td style={tdStyle}>{actionBtns(job)}</td>
                </tr>
                {expanded === job.id && (
                  <tr><td colSpan={8} style={{ padding: '20px', background: C.surfaceHover, borderBottom: `1px solid ${C.border}` }}>
                    <div style={{ marginBottom: '14px' }}>
                      <p style={{ color: C.textMuted, fontSize: '13px' }}>URL: <a href={job.url} target="_blank" rel="noreferrer" style={{ color: C.accent }}>{job.url}</a></p>
                      {job.error && <p style={{ color: C.red, fontSize: '13px', marginTop: '6px' }}>Error: {job.error}</p>}
                      {job.location && <p style={{ color: C.textMuted, fontSize: '13px', marginTop: '4px' }}>Location: {job.location}</p>}
                      {job.salary && <p style={{ color: C.textMuted, fontSize: '13px', marginTop: '4px' }}>Salary: {job.salary}</p>}
                    </div>
                    {review?.resume_used && (
                      <div style={{ marginBottom: '10px', padding: '8px 12px', background: C.surface, borderRadius: C.radiusSm, border: `1px solid ${C.border}` }}>
                        <span style={{ fontSize: '11px', color: C.textMuted, fontWeight: 600 }}>RESUME: </span>
                        <span style={{ fontSize: '13px', color: C.accent }}>{review.resume_used.name}</span>
                      </div>
                    )}
                    <div style={{ display: 'flex', gap: '10px', marginBottom: '12px' }}>
                      {review?.form_pdf && <a href={review.form_pdf.url} target="_blank" rel="noreferrer" style={linkBtn(C.accent)}>View Filled Form</a>}
                      {review?.video && <a href={review.video.url} target="_blank" rel="noreferrer" style={linkBtn(C.purple)}>Watch Recording</a>}
                    </div>
                    <div style={{ fontSize: '11px', color: C.textMuted, fontWeight: 600, marginBottom: '6px' }}>SCREENSHOTS</div>
                    <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
                      {(review?.screenshots || []).map((s, i) => (
                        <a key={i} href={s.url} target="_blank" rel="noreferrer"><img src={s.url} alt={s.name} style={{ width: '160px', height: '100px', objectFit: 'cover', borderRadius: C.radiusSm, border: `1px solid ${C.border}` }} /></a>
                      ))}
                      {(!review?.screenshots?.length) && <span style={{ color: C.textMuted, fontSize: '13px' }}>No screenshots</span>}
                    </div>
                  </td></tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
        {!filtered.length && <div style={{ padding: '40px', textAlign: 'center', color: C.textMuted }}>No jobs. Upload a CSV or add URLs.</div>}
      </div>
    </div>
  )
}

// ============================================================
// UPLOAD PAGE
// ============================================================
function UploadPage() {
  const [dragOver, setDragOver] = useState(false)
  const [result, setResult] = useState(null)
  const [url, setUrl] = useState('')
  const navigate = useNavigate()

  const handleFile = async (e) => {
    e.preventDefault(); setDragOver(false)
    const file = e.dataTransfer?.files?.[0] || e.target?.files?.[0]
    if (!file) return
    const form = new FormData(); form.append('file', file)
    const res = await fetch(`${API}/jobs/upload`, { method: 'POST', body: form }).then(r => r.json())
    setResult(res)
  }
  const addSingle = async () => {
    if (!url.trim()) return
    await api('/jobs/add', { method: 'POST', body: JSON.stringify({ url: url.trim() }) })
    setUrl(''); setResult({ imported: 1, skipped: 0 })
  }
  const handleResumes = async (e) => {
    const files = e.target.files; if (!files.length) return
    const form = new FormData()
    for (const f of files) form.append('files', f)
    const res = await fetch(`${API}/resumes/upload`, { method: 'POST', body: form }).then(r => r.json())
    setResult({ resumes_uploaded: res.uploaded.length })
  }

  return (
    <div>
      <h1 style={{ fontSize: '22px', fontWeight: 700, color: C.textBright, marginBottom: '20px' }}>Upload Jobs</h1>
      <div onDragOver={e => { e.preventDefault(); setDragOver(true) }} onDragLeave={() => setDragOver(false)} onDrop={handleFile}
        style={{ background: C.surface, border: `2px dashed ${dragOver ? C.accent : C.border}`, borderRadius: C.radius, padding: '40px', textAlign: 'center', marginBottom: '20px', cursor: 'pointer' }}
        onClick={() => document.getElementById('csv-input').click()}>
        <input id="csv-input" type="file" accept=".csv,.tsv,.xlsx" onChange={handleFile} style={{ display: 'none' }} />
        <div style={{ fontSize: '16px', fontWeight: 600, color: C.textBright, marginBottom: '6px' }}>Drop your scored job sheet here</div>
        <div style={{ color: C.textMuted, fontSize: '13px' }}>CSV or TSV with columns: Company, Title, Score, Link</div>
      </div>
      <div style={{ display: 'flex', gap: '8px', marginBottom: '20px' }}>
        <input value={url} onChange={e => setUrl(e.target.value)} onKeyDown={e => e.key === 'Enter' && addSingle()} placeholder="Or paste a job URL..." style={inputStyle} />
        <button onClick={addSingle} style={btnStyle(C.accent)}>Add</button>
      </div>
      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.radius, padding: '20px', marginBottom: '20px' }}>
        <div style={{ fontSize: '14px', fontWeight: 600, color: C.textBright, marginBottom: '8px' }}>Upload Tailored Resumes (optional)</div>
        <div style={{ color: C.textMuted, fontSize: '13px', marginBottom: '10px' }}>Name PDFs like CompanyName_Title.pdf. Unmatched jobs use default resume.</div>
        <input type="file" accept=".pdf" multiple onChange={handleResumes} style={{ color: C.text }} />
        <button onClick={() => api('/resumes/match', { method: 'POST' }).then(r => setResult(r))} style={{ ...btnStyle(C.accent), marginLeft: '10px' }}>Auto-Match</button>
      </div>
      {result && (
        <div style={{ background: C.surface, border: `1px solid ${C.green}`, borderRadius: C.radius, padding: '14px', color: C.green, display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span>{result.imported !== undefined && `Imported ${result.imported} jobs (${result.skipped} skipped)`}{result.matched !== undefined && `Matched ${result.matched}/${result.total} resumes`}{result.resumes_uploaded !== undefined && `Uploaded ${result.resumes_uploaded} resumes`}</span>
          <button onClick={() => navigate('/')} style={btnStyle(C.accent)}>Go to Queue</button>
        </div>
      )}
    </div>
  )
}

// ============================================================
// LIVE PAGE — with queue preview and time estimate
// ============================================================
function LivePage() {
  const [status, setStatus] = useState({})
  const [logs, setLogs] = useState([])
  const [queue, setQueue] = useState([])

  useEffect(() => {
    const poll = () => { api('/status').then(setStatus); api('/logs?limit=20').then(setLogs); api('/queue-preview').then(setQueue) }
    poll(); const t = setInterval(poll, 3000); return () => clearInterval(t)
  }, [])

  const progress = status.total ? Math.round((status.completed / status.total) * 100) : 0
  const remaining = (status.total || 0) - (status.completed || 0)
  const estMin = Math.round(remaining * 0.5) // ~30s per job

  return (
    <div>
      <h1 style={{ fontSize: '22px', fontWeight: 700, color: C.textBright, marginBottom: '20px' }}>Live View</h1>

      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.radius, padding: '20px', marginBottom: '20px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '10px' }}>
          <span style={{ fontWeight: 600, color: status.running ? C.green : C.textMuted }}>
            {status.running ? `Applying ${(status.completed || 0) + 1} of ${status.total}...` : 'Idle'}
          </span>
          <span style={{ color: C.textMuted }}>{progress}% {remaining > 0 && `(~${estMin} min left)`}</span>
        </div>
        <div style={{ height: '6px', background: C.border, borderRadius: '3px', overflow: 'hidden' }}>
          <div style={{ height: '100%', width: `${progress}%`, background: C.green, borderRadius: '3px', transition: 'width 0.5s' }} />
        </div>
        <div style={{ display: 'flex', gap: '20px', marginTop: '10px', fontSize: '13px', color: C.textMuted }}>
          <span>Applied: <strong style={{ color: C.green }}>{status.applied || 0}</strong></span>
          <span>Failed: <strong style={{ color: C.red }}>{status.failed || 0}</strong></span>
        </div>
        {status.running && (
          <div style={{ display: 'flex', gap: '8px', marginTop: '10px' }}>
            <button onClick={() => api('/apply/pause', { method: 'POST' })} style={btnStyle(C.yellow)}>{status.paused ? 'Resume' : 'Pause'}</button>
            <button onClick={() => api('/apply/cancel', { method: 'POST' })} style={btnStyle(C.red)}>Cancel</button>
          </div>
        )}
      </div>

      {/* Current + Queue */}
      <div style={{ display: 'flex', gap: '16px', marginBottom: '20px' }}>
        {status.current_job && (
          <div style={{ flex: 1, background: C.surface, border: `1px solid ${C.blue}`, borderRadius: C.radius, padding: '16px' }}>
            <div style={{ fontSize: '11px', color: C.blue, fontWeight: 600, marginBottom: '6px' }}>NOW APPLYING</div>
            <div style={{ fontSize: '15px', fontWeight: 600, color: C.textBright }}>{status.current_job.title}</div>
            <div style={{ color: C.textMuted, fontSize: '13px' }}>{status.current_job.company} - {status.current_job.platform}</div>
          </div>
        )}
        {queue.length > 0 && (
          <div style={{ flex: 1, background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.radius, padding: '16px' }}>
            <div style={{ fontSize: '11px', color: C.textMuted, fontWeight: 600, marginBottom: '6px' }}>UP NEXT</div>
            {queue.slice(0, 3).map((j, i) => (
              <div key={j.id} style={{ fontSize: '13px', color: C.text, padding: '4px 0', display: 'flex', justifyContent: 'space-between' }}>
                <span>{j.company} - {j.title.substring(0, 30)}</span>
                <span style={{ color: C.textMuted }}>{j.score}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Log */}
      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.radius, padding: '14px' }}>
        <div style={{ fontSize: '13px', fontWeight: 600, color: C.textBright, marginBottom: '10px' }}>Activity Log</div>
        {!logs.length && <div style={{ color: C.textMuted, fontSize: '13px' }}>No activity yet.</div>}
        {logs.map((log, i) => (
          <div key={i} style={{ padding: '4px 0', borderBottom: i < logs.length - 1 ? `1px solid ${C.border}` : 'none', fontSize: '12px', display: 'flex', gap: '10px' }}>
            <span style={{ color: C.textMuted, minWidth: '130px' }}>{log.timestamp}</span>
            <Badge status={log.action} />
            <span style={{ color: C.text }}>{log.detail}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ============================================================
// SETTINGS PAGE
// ============================================================
function SettingsPage() {
  const [profile, setProfile] = useState(null)
  const [resumes, setResumes] = useState([])
  const [saved, setSaved] = useState(false)

  useEffect(() => { api('/profile').then(setProfile); api('/resumes').then(setResumes) }, [])
  if (!profile) return <div style={{ color: C.textMuted, padding: '40px' }}>Loading...</div>

  return (
    <div>
      <h1 style={{ fontSize: '22px', fontWeight: 700, color: C.textBright, marginBottom: '20px' }}>Settings</h1>
      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.radius, padding: '20px', marginBottom: '20px' }}>
        <h2 style={{ fontSize: '15px', fontWeight: 600, color: C.textBright, marginBottom: '14px' }}>Profile</h2>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
          {[['full_name','Name'],['email','Email'],['phone','Phone'],['city','City'],['state','State'],['postal_code','Zip'],['linkedin','LinkedIn'],['github','GitHub'],['salary','Salary'],['years_experience','YOE'],['authorized_to_work','Work Auth'],['require_sponsorship','Sponsorship']].map(([k,l]) => (
            <div key={k}>
              <label style={{ fontSize: '11px', color: C.textMuted, marginBottom: '3px', display: 'block' }}>{l}</label>
              <input value={profile[k]||''} onChange={e => setProfile({...profile,[k]:e.target.value})} style={inputStyle} />
            </div>
          ))}
        </div>
        <button onClick={() => { setSaved(true); setTimeout(() => setSaved(false), 2000) }} style={{ ...btnStyle(C.green), marginTop: '14px' }}>{saved ? 'Saved!' : 'Save'}</button>
      </div>
      <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.radius, padding: '20px' }}>
        <h2 style={{ fontSize: '15px', fontWeight: 600, color: C.textBright, marginBottom: '14px' }}>Resumes</h2>
        {resumes.map((r, i) => (
          <div key={i} style={{ padding: '6px 0', borderBottom: `1px solid ${C.border}`, fontSize: '13px', display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ color: C.text }}>{r.name}</span>
            <span style={{ color: C.textMuted }}>{(r.size / 1024).toFixed(0)} KB</span>
          </div>
        ))}
        {!resumes.length && <div style={{ color: C.textMuted, fontSize: '13px' }}>No resumes uploaded.</div>}
      </div>
    </div>
  )
}

// ============================================================
// LAYOUT
// ============================================================
function App() {
  const nav = [{ path: '/', label: 'Jobs', icon: 'Q' }, { path: '/upload', label: 'Upload', icon: '+' }, { path: '/live', label: 'Live', icon: '>' }, { path: '/settings', label: 'Settings', icon: '*' }]
  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <nav style={{ width: '180px', background: C.surface, borderRight: `1px solid ${C.border}`, padding: '16px 0', display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '0 16px 16px', borderBottom: `1px solid ${C.border}`, marginBottom: '8px' }}>
          <div style={{ fontWeight: 700, fontSize: '15px', color: C.textBright }}>Job Apply</div>
          <div style={{ fontSize: '11px', color: C.textMuted }}>Engine v2.0</div>
        </div>
        {nav.map(item => (
          <NavLink key={item.path} to={item.path} end={item.path === '/'}
            style={({ isActive }) => ({ display: 'flex', alignItems: 'center', gap: '8px', padding: '9px 16px', textDecoration: 'none', fontSize: '13px', fontWeight: 500, color: isActive ? C.textBright : C.textMuted, background: isActive ? '#1c2129' : 'transparent', borderLeft: isActive ? `2px solid ${C.accent}` : '2px solid transparent' })}>
            <span style={{ width: '16px', textAlign: 'center', opacity: 0.6 }}>{item.icon}</span>{item.label}
          </NavLink>
        ))}
      </nav>
      <main style={{ flex: 1, padding: '28px 36px', maxWidth: '1200px', overflowY: 'auto' }}>
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

// Styles
const btnStyle = (c) => ({ padding: '7px 14px', borderRadius: C.radiusSm, border: 'none', background: c, color: C.bg, fontWeight: 600, fontSize: '12px', cursor: 'pointer' })
const sBtn = { padding: '2px 7px', borderRadius: C.radiusSm, border: `1px solid ${C.border}`, background: 'transparent', color: C.textMuted, fontSize: '11px', cursor: 'pointer' }
const chipStyle = { padding: '4px 12px', borderRadius: '14px', border: `1px solid ${C.border}`, fontSize: '12px', cursor: 'pointer', fontWeight: 500 }
const inputStyle = { flex: 1, padding: '7px 10px', borderRadius: C.radiusSm, border: `1px solid ${C.border}`, background: C.surface, color: C.text, fontSize: '13px', outline: 'none' }
const thStyle = { padding: '8px 10px', textAlign: 'left', fontSize: '11px', fontWeight: 600, color: C.textMuted, textTransform: 'uppercase', letterSpacing: '0.5px' }
const tdStyle = { padding: '8px 10px', fontSize: '13px' }
const trStyle = { borderBottom: `1px solid ${C.border}`, transition: 'background 0.15s' }
const linkBtn = (c) => ({ padding: '6px 14px', background: C.surface, border: `1px solid ${C.border}`, borderRadius: C.radiusSm, color: c, fontSize: '12px', fontWeight: 600, textDecoration: 'none' })

export default App
