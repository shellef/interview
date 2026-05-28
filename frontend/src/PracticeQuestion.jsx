import { useState, useEffect, useRef, useCallback } from 'react'

// ── Deepgram TTS ──────────────────────────────────────────────────────────────
async function speakText(text, onEnd) {
  try {
    const res = await fetch('/practice/speak', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    })
    if (!res.ok) throw new Error('TTS failed')
    const audio = new Audio(URL.createObjectURL(await res.blob()))
    audio.onended = onEnd
    audio.onerror = onEnd
    await audio.play()
    return audio
  } catch { onEnd(); return null }
}

// ── MediaRecorder ─────────────────────────────────────────────────────────────
function useMediaRecorder() {
  const mrRef = useRef(null), streamRef = useRef(null), chunksRef = useRef([])

  const start = useCallback(async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false })
    streamRef.current = stream
    const mr = new MediaRecorder(stream)
    mrRef.current = mr; chunksRef.current = []
    mr.ondataavailable = e => { if (e.data.size > 0) chunksRef.current.push(e.data) }
    mr.start(100)
  }, [])

  const stop = useCallback(() => new Promise(resolve => {
    const mr = mrRef.current
    if (!mr || mr.state === 'inactive') {
      streamRef.current?.getTracks().forEach(t => t.stop()); return resolve(null)
    }
    mr.onstop = () => {
      const blob = new Blob(chunksRef.current, { type: mr.mimeType || 'audio/webm' })
      streamRef.current?.getTracks().forEach(t => t.stop())
      streamRef.current = null; mrRef.current = null; resolve(blob)
    }
    mr.stop()
  }), [])

  const release = useCallback(() => {
    try { mrRef.current?.stop() } catch (_) {}
    streamRef.current?.getTracks().forEach(t => t.stop())
    streamRef.current = null; mrRef.current = null
  }, [])

  return { start, stop, release }
}

// ── Audio level meter ─────────────────────────────────────────────────────────
function AudioMeter({ active }) {
  const canvasRef = useRef(null), rafRef = useRef(null)
  const streamRef = useRef(null), audioCtxRef = useRef(null)

  useEffect(() => {
    if (!active) return
    const canvas = canvasRef.current; if (!canvas) return
    const ctx = canvas.getContext('2d'); let cancelled = false

    const stopAll = () => {
      cancelAnimationFrame(rafRef.current)
      streamRef.current?.getTracks().forEach(t => t.stop())
      streamRef.current = null; audioCtxRef.current?.close(); audioCtxRef.current = null
    }

    navigator.mediaDevices.getUserMedia({ audio: true, video: false }).then(stream => {
      if (cancelled) { stream.getTracks().forEach(t => t.stop()); return }
      streamRef.current = stream
      const audioCtx = new (window.AudioContext || window.webkitAudioContext)()
      audioCtxRef.current = audioCtx
      const analyser = audioCtx.createAnalyser(); analyser.fftSize = 64
      audioCtx.createMediaStreamSource(stream).connect(analyser)
      const data = new Uint8Array(analyser.frequencyBinCount)
      const W = canvas.width, H = canvas.height, BARS = 20, GAP = 2
      const bw = (W - GAP * (BARS - 1)) / BARS
      const draw = () => {
        analyser.getByteFrequencyData(data); ctx.clearRect(0, 0, W, H)
        for (let i = 0; i < BARS; i++) {
          const v = data[Math.floor(i * data.length / BARS)] / 255
          const h = Math.max(3, v * H)
          ctx.fillStyle = v > 0.15 ? `rgba(99,102,241,${0.5 + v * 0.5})` : 'rgba(55,65,81,0.6)'
          ctx.beginPath(); ctx.roundRect(i * (bw + GAP), (H - h) / 2, bw, h, 2); ctx.fill()
        }
        rafRef.current = requestAnimationFrame(draw)
      }
      rafRef.current = requestAnimationFrame(draw)
    }).catch(() => {})

    return () => { cancelled = true; stopAll() }
  }, [active])

  return <canvas ref={canvasRef} width={240} height={44} className="pq-meter"
    style={{ display: active ? 'block' : 'none' }} />
}

// ── Score badge ───────────────────────────────────────────────────────────────
function ScoreBadge({ score }) {
  const cfg = {
    strong:   { bg: '#0d2a1e', border: '#065f46', color: '#34d399', label: 'Strong'    },
    adequate: { bg: '#2d2a0a', border: '#713f12', color: '#fcd34d', label: 'Adequate'  },
    weak:     { bg: '#2d1515', border: '#7f1d1d', color: '#f87171', label: 'Needs Work'},
  }[score] || { bg: '#1e2433', border: '#374151', color: '#94a3b8', label: score }
  return <span style={{
    display: 'inline-block', padding: '2px 12px', borderRadius: 999,
    background: cfg.bg, border: `1px solid ${cfg.border}`, color: cfg.color,
    fontSize: '0.78rem', fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase',
  }}>{cfg.label}</span>
}

// ── Evaluation panel ──────────────────────────────────────────────────────────
function Evaluation({ result }) {
  return (
    <div className="eval-panel">
      <div className="eval-header">
        <span className="eval-title">Feedback</span>
        <ScoreBadge score={result.score} />
      </div>
      <p className="eval-summary">{result.summary}</p>
      <div className="eval-signals">
        {result.covered?.length > 0 && (
          <div className="eval-group covered">
            <h4>Covered</h4>
            <ul>{result.covered.map((p, i) => <li key={i}>{p}</li>)}</ul>
          </div>
        )}
        {result.missed?.length > 0 && (
          <div className="eval-group missed">
            <h4>Missing</h4>
            <ul>{result.missed.map((p, i) => <li key={i}>{p}</li>)}</ul>
          </div>
        )}
      </div>
      {result.advice && (
        <div className="eval-advice">
          <span className="eval-advice-label">Tip</span>{result.advice}
        </div>
      )}
    </div>
  )
}

// ── Chat bubble ───────────────────────────────────────────────────────────────
function Bubble({ role, content }) {
  return (
    <div className={`chat-bubble chat-${role}`}>
      <span className="chat-label">{role === 'interviewer' ? 'Interviewer' : 'You'}</span>
      <p>{content}</p>
    </div>
  )
}

// ── Main building block ───────────────────────────────────────────────────────
// messages: [{role: 'interviewer'|'candidate', content, visible}]
// phase: speaking | answering | submitting | done
export default function PracticeQuestion({ question, onDone, onStop }) {
  const [messages, setMessages] = useState([])
  const [phase,    setPhase]    = useState('speaking')
  const [result,   setResult]   = useState(null)
  const [error,    setError]    = useState(null)
  const [textAnswer, setTextAnswer] = useState('')
  const audioRef   = useRef(null)
  const recorder   = useMediaRecorder()
  const bottomRef  = useRef(null)

  // Scroll to bottom whenever messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [messages, phase])

  // Add an interviewer message (invisible), speak it, then reveal it
  const askQuestion = useCallback((text, token) => {
    setPhase('speaking')
    // Add invisible message
    setMessages(prev => [...prev, { role: 'interviewer', content: text, visible: false }])

    speakText(text, () => {
      if (token.current) return
      // Reveal the message text
      setMessages(prev => prev.map((m, i) =>
        i === prev.length - 1 ? { ...m, visible: true } : m
      ))
      setPhase('answering')
      recorder.start().catch(() => {})
    }).then(a => {
      if (token.current) { a?.pause(); return }
      audioRef.current = a
    })
  }, [recorder])

  // Broadcast current question so a cheatsheet tab can sync
  useEffect(() => {
    const id = question.id
    localStorage.setItem('cheatsheet-question-id', id)
    try { new BroadcastChannel('interview-sync').postMessage({ questionId: id }) } catch (_) {}
  }, [question.id])

  // Init: ask the first question
  useEffect(() => {
    const token = { current: false }
    setMessages([])
    setResult(null)
    setError(null)
    setTextAnswer('')
    askQuestion(question.question, token)

    return () => {
      token.current = true
      audioRef.current?.pause()
      audioRef.current = null
      recorder.release()
    }
  }, [question.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleSubmit = useCallback(async () => {
    setPhase('submitting')
    setError(null)

    // Transcribe
    const blob = await recorder.stop()
    let answer = ''
    if (blob && blob.size > 0) {
      const form = new FormData()
      form.append('audio', blob, 'answer.webm')
      try {
        const tRes = await fetch('/practice/transcribe', { method: 'POST', body: form })
        if (tRes.status === 401) { window.location.href = '/login'; return }
        answer = (await tRes.json()).transcript?.trim() || ''
      } catch (_) {}
    }
    if (!answer) answer = textAnswer.trim()
    if (!answer) {
      setError('No answer detected — check mic permissions or type below.')
      setPhase('answering'); recorder.start().catch(() => {})
      return
    }
    setTextAnswer('')

    // Add candidate bubble immediately
    const candidateMsg = { role: 'candidate', content: answer, visible: true }
    const updatedMessages = [...messages, candidateMsg]
    setMessages(updatedMessages)

    // Build turns for API (only visible interviewer messages + candidate answers)
    const turns = updatedMessages
      .filter(m => m.visible || m.role === 'candidate')
      .map(m => ({ role: m.role, content: m.content }))

    try {
      const res = await fetch('/practice/turn', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question_id: question.id, turns }),
      })
      if (res.status === 401) { window.location.href = '/login'; return }
      if (!res.ok) throw new Error(`Server error ${res.status}`)
      const data = await res.json()

      if (data.action === 'probe') {
        try { new BroadcastChannel('interview-sync').postMessage({ questionId: question.id, topic: data.topic }) } catch (_) {}
        askQuestion(data.probe, { current: false })
      } else {
        setResult(data.result)
        setPhase('done')
        onDone?.()
      }
    } catch (e) {
      setError(e.message)
      setPhase('answering')
      recorder.start().catch(() => {})
    }
  }, [recorder, textAnswer, messages, question.id, askQuestion, onDone])

  return (
    <div className="pq-wrap">
      <div className="pq-topbar">
        <div className="pq-category">{question.category_label}</div>
        {phase !== 'done' && (
          <button className="btn btn-secondary pq-stop" onClick={() => {
            audioRef.current?.pause()
            recorder.release()
            onStop?.()
          }}>
            Stop
          </button>
        )}
      </div>

      {/* Conversation thread */}
      <div className="chat-thread">
        {messages.map((m, i) =>
          m.visible
            ? <Bubble key={i} role={m.role} content={m.content} />
            : null
        )}

        {/* Speaking indicator — appears where next bubble will be */}
        {phase === 'speaking' && (
          <div className="chat-bubble chat-interviewer chat-pending">
            <span className="chat-label">Interviewer</span>
            <div className="pq-status" style={{ marginTop: 0 }}>
              <span className="pq-rec-dot pq-speaking-dot" />
              <span>Speaking…</span>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      {phase === 'answering' && (
        <div className="pq-answer-area">
          <div className="pq-listen-row">
            <AudioMeter active={true} />
            <button className="btn btn-primary" onClick={handleSubmit}>Submit Answer</button>
          </div>
          <textarea className="pq-textarea" placeholder="Or type your answer here…"
            value={textAnswer} onChange={e => setTextAnswer(e.target.value)} rows={3} />
          {error && <div className="error" style={{ marginTop: 8 }}>{error}</div>}
        </div>
      )}

      {phase === 'submitting' && (
        <button className="btn btn-primary" disabled style={{ alignSelf: 'flex-start' }}>
          <span className="spinner" style={{ width: 14, height: 14, marginRight: 6 }} />
          Transcribing &amp; evaluating…
        </button>
      )}

      {phase === 'done' && result && <Evaluation result={result} />}
    </div>
  )
}
