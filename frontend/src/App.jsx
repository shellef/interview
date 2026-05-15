import { useState } from 'react'
import VoiceInterview from './VoiceInterview.jsx'

const API = '/interview'

function Verdict({ verdict }) {
  const level = verdict?.level ?? 'unclear'
  return (
    <div className="verdict-card">
      <h3>Judge's Assessment</h3>
      <div className={`level-badge ${level}`}>{level}</div>
      <p className="confidence">Confidence: {verdict.confidence}</p>
      <p className="verdict-summary">{verdict.summary}</p>

      <div className="signals">
        {verdict.signals?.positive?.length > 0 && (
          <div className="signal-group positive">
            <h4>Strengths</h4>
            <ul>{verdict.signals.positive.map((s, i) => <li key={i}>{s}</li>)}</ul>
          </div>
        )}
        {verdict.signals?.negative?.length > 0 && (
          <div className="signal-group negative">
            <h4>Concerns</h4>
            <ul>{verdict.signals.negative.map((s, i) => <li key={i}>{s}</li>)}</ul>
          </div>
        )}
      </div>

      {verdict.recommended_follow_ups?.length > 0 && (
        <div className="follow-ups">
          <h4>Recommended Follow-ups</h4>
          <ul>{verdict.recommended_follow_ups.map((s, i) => <li key={i}>{s}</li>)}</ul>
        </div>
      )}
    </div>
  )
}

function Transcript({ turns }) {
  return (
    <div className="transcript">
      {turns.map((turn, i) => (
        <div key={i} className={`turn ${turn.speaker}`}>
          <span className="turn-label">
            {turn.speaker === 'interviewer' ? 'Interviewer' : 'Candidate'}
          </span>
          <div className="turn-bubble">{turn.text}</div>
        </div>
      ))}
    </div>
  )
}

export default function App() {
  const [mode, setMode] = useState('ai') // 'ai' | 'voice'
  const [role, setRole] = useState('senior backend engineer')
  const [numTurns, setNumTurns] = useState(3)
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState('')
  const [sessionId, setSessionId] = useState(null)
  const [turns, setTurns] = useState([])
  const [verdict, setVerdict] = useState(null)
  const [error, setError] = useState(null)

  async function startInterview() {
    setLoading(true)
    setError(null)
    setTurns([])
    setVerdict(null)
    setSessionId(null)
    setStatus(`Running ${numTurns}-turn interview for "${role}"…`)

    try {
      const res = await fetch(`${API}/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role, num_turns: numTurns }),
      })
      if (!res.ok) throw new Error(`Server error: ${res.status}`)
      const data = await res.json()
      setSessionId(data.session_id)
      setTurns(data.turns)
      setVerdict(data.verdict)
      setStatus('')
    } catch (e) {
      setError(e.message)
      setStatus('')
    } finally {
      setLoading(false)
    }
  }

  async function addTurn() {
    if (!sessionId) return
    setLoading(true)
    setStatus('Running next exchange…')
    try {
      const res = await fetch(`${API}/${sessionId}/next`, { method: 'POST' })
      if (!res.ok) throw new Error(`Server error: ${res.status}`)
      const data = await res.json()
      setTurns(data.turns)
      setStatus('')
    } catch (e) {
      setError(e.message)
      setStatus('')
    } finally {
      setLoading(false)
    }
  }

  async function runJudge() {
    if (!sessionId) return
    setLoading(true)
    setStatus('Judge is evaluating the transcript…')
    try {
      const res = await fetch(`${API}/${sessionId}/judge`, { method: 'POST' })
      if (!res.ok) throw new Error(`Server error: ${res.status}`)
      const data = await res.json()
      setVerdict(data.verdict)
      setStatus('')
    } catch (e) {
      setError(e.message)
      setStatus('')
    } finally {
      setLoading(false)
    }
  }

  function reset() {
    setSessionId(null)
    setTurns([])
    setVerdict(null)
    setError(null)
    setStatus('')
  }

  const hasSession = turns.length > 0

  if (mode === 'voice') {
    return (
      <>
        <div className="header">
          <h1>AI Interview</h1>
          <div className="mode-tabs">
            <button className="tab" onClick={() => setMode('ai')}>AI vs AI</button>
            <button className="tab active">Voice</button>
          </div>
        </div>
        <VoiceInterview />
      </>
    )
  }

  return (
    <div className="app">
      <div className="header">
        <h1>AI Interview</h1>
        <div className="mode-tabs">
          <button className="tab active">AI vs AI</button>
          <button className="tab" onClick={() => setMode('voice')}>Voice</button>
        </div>
      </div>

      {!hasSession ? (
        <div className="setup-card">
          <h2>New Interview</h2>
          <div className="form-row">
            <div className="field">
              <label>Role</label>
              <input
                value={role}
                onChange={e => setRole(e.target.value)}
                placeholder="e.g. senior backend engineer"
                disabled={loading}
              />
            </div>
            <div className="field">
              <label>Exchanges</label>
              <select value={numTurns} onChange={e => setNumTurns(Number(e.target.value))} disabled={loading}>
                {[1, 2, 3, 5, 8, 10].map(n => <option key={n} value={n}>{n}</option>)}
              </select>
            </div>
            <button className="btn btn-primary" onClick={startInterview} disabled={loading || !role.trim()}>
              {loading ? 'Running…' : 'Start Interview'}
            </button>
          </div>
          {loading && (
            <div className="status">
              <div className="spinner" />
              {status}
            </div>
          )}
          {error && <div className="error">{error}</div>}
        </div>
      ) : (
        <>
          <div className="setup-card">
            <div className="form-row">
              <span style={{ color: '#94a3b8', fontSize: '0.875rem' }}>
                <strong style={{ color: '#e2e8f0' }}>{role}</strong>
                {' · '}{turns.length / 2} exchange{turns.length / 2 !== 1 ? 's' : ''}
              </span>
              <div style={{ marginLeft: 'auto', display: 'flex', gap: '0.5rem' }}>
                {!verdict && (
                  <>
                    <button className="btn btn-secondary" onClick={addTurn} disabled={loading}>
                      + Exchange
                    </button>
                    <button className="btn btn-primary" onClick={runJudge} disabled={loading}>
                      Judge
                    </button>
                  </>
                )}
                <button className="btn btn-secondary" onClick={reset} disabled={loading}>
                  New Interview
                </button>
              </div>
            </div>
            {loading && (
              <div className="status">
                <div className="spinner" />
                {status}
              </div>
            )}
            {error && <div className="error">{error}</div>}
          </div>

          <Transcript turns={turns} />
          {verdict && <Verdict verdict={verdict} />}
        </>
      )}
    </div>
  )
}
