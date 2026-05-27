import { useState, useEffect, useRef, useCallback } from 'react'

// ── Deepgram TTS ──────────────────────────────────────────────────────────────
async function speakQuestion(text, onEnd) {
  try {
    const res = await fetch('/practice/speak', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    })
    if (!res.ok) throw new Error('TTS failed')
    const blob  = await res.blob()
    const url   = URL.createObjectURL(blob)
    const audio = new Audio(url)
    audio.onended = () => { URL.revokeObjectURL(url); onEnd() }
    audio.onerror = () => { URL.revokeObjectURL(url); onEnd() }
    await audio.play()
    return audio
  } catch {
    onEnd()
    return null
  }
}

// ── MediaRecorder — records audio for Deepgram transcription ─────────────────
function useMediaRecorder() {
  const mrRef     = useRef(null)
  const streamRef = useRef(null)
  const chunksRef = useRef([])

  const start = useCallback(async () => {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false })
    streamRef.current  = stream
    const mr           = new MediaRecorder(stream)
    mrRef.current      = mr
    chunksRef.current  = []
    mr.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data) }
    mr.start(100)
  }, [])

  const stop = useCallback(() => new Promise(resolve => {
    const mr = mrRef.current
    if (!mr || mr.state === 'inactive') {
      streamRef.current?.getTracks().forEach(t => t.stop())
      return resolve(null)
    }
    mr.onstop = () => {
      const blob = new Blob(chunksRef.current, { type: mr.mimeType || 'audio/webm' })
      streamRef.current?.getTracks().forEach(t => t.stop())
      streamRef.current = null
      mrRef.current     = null
      resolve(blob)
    }
    mr.stop()
  }), [])

  const release = useCallback(() => {
    try { mrRef.current?.stop() } catch (_) {}
    streamRef.current?.getTracks().forEach(t => t.stop())
    streamRef.current = null
    mrRef.current     = null
  }, [])

  return { start, stop, release }
}

// ── Audio level meter via Web Audio API ──────────────────────────────────────
function AudioMeter({ active }) {
  const canvasRef   = useRef(null)
  const rafRef      = useRef(null)
  const streamRef   = useRef(null)
  const audioCtxRef = useRef(null)

  useEffect(() => {
    if (!active) return
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx     = canvas.getContext('2d')
    let cancelled = false

    const stopAll = () => {
      cancelAnimationFrame(rafRef.current)
      streamRef.current?.getTracks().forEach(t => t.stop())
      streamRef.current = null
      audioCtxRef.current?.close()
      audioCtxRef.current = null
    }

    navigator.mediaDevices.getUserMedia({ audio: true, video: false })
      .then(stream => {
        if (cancelled) { stream.getTracks().forEach(t => t.stop()); return }
        streamRef.current     = stream
        const audioCtx        = new (window.AudioContext || window.webkitAudioContext)()
        audioCtxRef.current   = audioCtx
        const analyser        = audioCtx.createAnalyser()
        analyser.fftSize      = 64
        audioCtx.createMediaStreamSource(stream).connect(analyser)

        const data = new Uint8Array(analyser.frequencyBinCount)
        const W = canvas.width, H = canvas.height
        const BARS = 20, GAP = 2
        const bw   = (W - GAP * (BARS - 1)) / BARS

        const draw = () => {
          analyser.getByteFrequencyData(data)
          ctx.clearRect(0, 0, W, H)
          for (let i = 0; i < BARS; i++) {
            const v = data[Math.floor(i * data.length / BARS)] / 255
            const h = Math.max(3, v * H)
            ctx.fillStyle = v > 0.15
              ? `rgba(99, 102, 241, ${0.5 + v * 0.5})`
              : 'rgba(55, 65, 81, 0.6)'
            ctx.beginPath()
            ctx.roundRect(i * (bw + GAP), (H - h) / 2, bw, h, 2)
            ctx.fill()
          }
          rafRef.current = requestAnimationFrame(draw)
        }
        rafRef.current = requestAnimationFrame(draw)
      })
      .catch(() => {})

    return () => { cancelled = true; stopAll() }
  }, [active])

  return (
    <canvas
      ref={canvasRef}
      width={240}
      height={44}
      className="pq-meter"
      style={{ display: active ? 'block' : 'none' }}
    />
  )
}

// ── Score badge ───────────────────────────────────────────────────────────────
function ScoreBadge({ score }) {
  const cfg = {
    strong:   { bg: '#0d2a1e', border: '#065f46', color: '#34d399', label: 'Strong'    },
    adequate: { bg: '#2d2a0a', border: '#713f12', color: '#fcd34d', label: 'Adequate'  },
    weak:     { bg: '#2d1515', border: '#7f1d1d', color: '#f87171', label: 'Needs Work'},
  }[score] || { bg: '#1e2433', border: '#374151', color: '#94a3b8', label: score }
  return (
    <span style={{
      display: 'inline-block', padding: '2px 12px', borderRadius: 999,
      background: cfg.bg, border: `1px solid ${cfg.border}`, color: cfg.color,
      fontSize: '0.78rem', fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase',
    }}>
      {cfg.label}
    </span>
  )
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
          <span className="eval-advice-label">Tip</span>
          {result.advice}
        </div>
      )}
    </div>
  )
}

// ── Main building block ───────────────────────────────────────────────────────
export default function PracticeQuestion({ question, onDone }) {
  const [phase,      setPhase]      = useState('speaking')
  const [result,     setResult]     = useState(null)
  const [error,      setError]      = useState(null)
  const [textAnswer, setTextAnswer] = useState('')
  const [transcript, setTranscript] = useState('')
  const audioRef = useRef(null)
  const recorder = useMediaRecorder()

  // Speak question; start recording when TTS ends
  useEffect(() => {
    let cancelled = false
    setPhase('speaking')
    setResult(null)
    setError(null)
    setTextAnswer('')

    speakQuestion(question.question, () => {
      if (!cancelled) {
        setPhase('answering')
        recorder.start().catch(() => {})
      }
    }).then(a => {
      if (cancelled) { a?.pause(); return }
      audioRef.current = a
    })

    return () => {
      cancelled = true
      audioRef.current?.pause()
      audioRef.current = null
      recorder.release()
    }
  }, [question.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleSubmit = useCallback(async () => {
    setPhase('submitting')
    setError(null)
    try {
      const blob = await recorder.stop()
      let answer = ''

      if (blob && blob.size > 0) {
        const form = new FormData()
        form.append('audio', blob, 'answer.webm')
        const tRes = await fetch('/practice/transcribe', { method: 'POST', body: form })
        if (tRes.status === 401) { window.location.href = '/login'; return }
        if (!tRes.ok) throw new Error(`Transcription error ${tRes.status}`)
        answer = (await tRes.json()).transcript?.trim() || ''
      }

      // Fall back to typed text
      if (!answer) answer = textAnswer.trim()
      setTranscript(answer)

      if (!answer) {
        setError('No answer detected — check microphone permissions or type your answer below.')
        setPhase('answering')
        recorder.start().catch(() => {})
        return
      }

      const eRes = await fetch('/practice/evaluate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question_id: question.id, answer }),
      })
      if (eRes.status === 401) { window.location.href = '/login'; return }
      if (!eRes.ok) throw new Error(`Evaluation error ${eRes.status}`)
      setResult(await eRes.json())
      setPhase('done')
      onDone?.()
    } catch (e) {
      setError(e.message)
      setPhase('answering')
      recorder.start().catch(() => {})
    }
  }, [recorder, textAnswer, question.id, onDone])

  return (
    <div className="pq-wrap">
      <div className="pq-category">{question.category_label}</div>
      {phase !== 'speaking' && (
        <div className="pq-question">{question.question}</div>
      )}

      {phase === 'speaking' && (
        <div className="pq-status">
          <span className="pq-rec-dot pq-speaking-dot" />
          <span>Asking question…</span>
          <button
            className="btn btn-primary"
            onClick={() => {
              audioRef.current?.pause()
              setPhase('answering')
              recorder.start().catch(() => {})
            }}
          >
            Skip →
          </button>
        </div>
      )}

      {phase === 'answering' && (
        <div className="pq-answer-area">
          <div className="pq-listen-row">
            <AudioMeter active={true} />
            <button className="btn btn-primary" onClick={handleSubmit}>
              Submit Answer
            </button>
          </div>
          <textarea
            className="pq-textarea"
            placeholder="Or type your answer here…"
            value={textAnswer}
            onChange={e => setTextAnswer(e.target.value)}
            rows={3}
          />
          {error && <div className="error" style={{ marginTop: 8 }}>{error}</div>}
        </div>
      )}

      {phase === 'submitting' && (
        <button className="btn btn-primary" disabled style={{ alignSelf: 'flex-start' }}>
          <span className="spinner" style={{ width: 14, height: 14, marginRight: 6 }} />
          Transcribing &amp; evaluating…
        </button>
      )}

      {phase === 'done' && result && (
        <>
          {transcript && (
            <div className="pq-your-answer">
              <span className="pq-your-answer-label">Your answer</span>
              <p>{transcript}</p>
            </div>
          )}
          <Evaluation result={result} />
        </>
      )}
    </div>
  )
}
