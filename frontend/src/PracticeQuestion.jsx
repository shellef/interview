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
    const blob = await res.blob()
    const url  = URL.createObjectURL(blob)
    const audio = new Audio(url)
    audio.onended = () => { URL.revokeObjectURL(url); onEnd() }
    audio.onerror = () => { URL.revokeObjectURL(url); onEnd() }
    await audio.play()
    return audio
  } catch {
    onEnd()   // if TTS fails, still start listening
    return null
  }
}

// ── Silent speech recognition ─────────────────────────────────────────────────
function useSpeechInput(active) {
  const recogRef   = useRef(null)
  const finalRef   = useRef('')
  const supported  = !!(window.SpeechRecognition || window.webkitSpeechRecognition)

  useEffect(() => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR || !active) return

    const r          = new SR()
    r.continuous     = true
    r.interimResults = false   // final only — no display needed
    r.lang           = 'en-US'
    recogRef.current = r
    finalRef.current = ''

    r.onresult = (e) => {
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal)
          finalRef.current += (finalRef.current ? ' ' : '') + e.results[i][0].transcript
      }
    }
    r.onerror = (e) => { if (e.error !== 'no-speech') console.warn('STT:', e.error) }
    r.onend   = () => { if (active && recogRef.current === r) try { r.start() } catch (_) {} }

    try { r.start() } catch (_) {}
    return () => { recogRef.current = null; try { r.stop() } catch (_) {} }
  }, [active])

  return { supported, getTranscript: useCallback(() => finalRef.current, []) }
}

// ── Audio level meter via Web Audio API ───────────────────────────────────────
function AudioMeter({ active }) {
  const canvasRef = useRef(null)
  const rafRef    = useRef(null)

  useEffect(() => {
    if (!active) return
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    let audioCtx, source

    navigator.mediaDevices.getUserMedia({ audio: true, video: false })
      .then(stream => {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)()
        const analyser = audioCtx.createAnalyser()
        analyser.fftSize = 64
        source = audioCtx.createMediaStreamSource(stream)
        source.connect(analyser)

        const data = new Uint8Array(analyser.frequencyBinCount)
        const W = canvas.width, H = canvas.height
        const BARS = 20, GAP = 2
        const bw = (W - GAP * (BARS - 1)) / BARS

        const draw = () => {
          analyser.getByteFrequencyData(data)
          ctx.clearRect(0, 0, W, H)
          for (let i = 0; i < BARS; i++) {
            const v = data[Math.floor(i * data.length / BARS)] / 255
            const h = Math.max(3, v * H)
            ctx.fillStyle = v > 0.15
              ? `rgba(99, 102, 241, ${0.5 + v * 0.5})`   // speaking — indigo
              : 'rgba(55, 65, 81, 0.6)'                   // silent — grey
            ctx.beginPath()
            ctx.roundRect(i * (bw + GAP), (H - h) / 2, bw, h, 2)
            ctx.fill()
          }
          rafRef.current = requestAnimationFrame(draw)
        }
        rafRef.current = requestAnimationFrame(draw)
      })
      .catch(() => {})   // no permission — meter just won't show

    return () => {
      cancelAnimationFrame(rafRef.current)
      source?.disconnect()
      audioCtx?.close()
    }
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
    strong:   { bg: '#0d2a1e', border: '#065f46', color: '#34d399', label: 'Strong'     },
    adequate: { bg: '#2d2a0a', border: '#713f12', color: '#fcd34d', label: 'Adequate'   },
    weak:     { bg: '#2d1515', border: '#7f1d1d', color: '#f87171', label: 'Needs Work' },
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
  // phases: speaking → answering → submitting → done
  const [phase,      setPhase]     = useState('speaking')
  const [result,     setResult]    = useState(null)
  const [error,      setError]     = useState(null)
  const [textAnswer, setTextAnswer] = useState('')
  const audioRef = useRef(null)

  const { supported: voiceSupported, getTranscript } = useSpeechInput(phase === 'answering')

  // Speak question when it appears; start listening when audio ends
  useEffect(() => {
    let cancelled = false

    setPhase('speaking')
    setResult(null)
    setError(null)
    setTextAnswer('')

    speakQuestion(
      question.question,
      () => { if (!cancelled) setPhase('answering') }
    ).then(a => {
      if (cancelled) { a?.pause(); return }
      audioRef.current = a
    })

    return () => {
      cancelled = true
      audioRef.current?.pause()
      audioRef.current = null
    }
  }, [question.id])

  const handleSubmit = useCallback(async () => {
    const text = voiceSupported ? getTranscript().trim() : textAnswer.trim()
    if (!text) {
      setError('No answer recorded — check your microphone permissions.')
      return
    }
    setPhase('submitting')
    try {
      const res = await fetch('/practice/evaluate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question_id: question.id, answer: text }),
      })
      if (res.status === 401) { window.location.href = '/login'; return }
      if (!res.ok) throw new Error(`Server error ${res.status}`)
      setResult(await res.json())
      setPhase('done')
      onDone?.()
    } catch (e) {
      setError(e.message)
      setPhase('answering')
    }
  }, [voiceSupported, getTranscript, textAnswer, question.id, onDone])

  return (
    <div className="pq-wrap">
      <div className="pq-category">{question.category_label}</div>
      <div className="pq-question">{question.question}</div>

      {/* Speaking — waiting for TTS to finish */}
      {phase === 'speaking' && (
        <div className="pq-status">
          <span className="pq-rec-dot pq-speaking-dot" />
          Asking question…
          <button
            className="btn btn-secondary pq-skip"
            onClick={() => { audioRef.current?.pause(); setPhase('answering') }}
          >
            Skip
          </button>
        </div>
      )}

      {/* Answering */}
      {phase === 'answering' && (
        <div className="pq-answer-area">
          {voiceSupported ? (
            <div className="pq-listen-row">
              <AudioMeter active={true} />
              <button className="btn btn-primary" onClick={handleSubmit}>
                Submit Answer
              </button>
            </div>
          ) : (
            <>
              <textarea
                className="pq-textarea"
                placeholder="Type your answer here…"
                value={textAnswer}
                onChange={e => setTextAnswer(e.target.value)}
                autoFocus
                rows={5}
              />
              <button
                className="btn btn-primary"
                onClick={handleSubmit}
                disabled={!textAnswer.trim()}
              >
                Submit Answer
              </button>
            </>
          )}
          {error && <div className="error" style={{ marginTop: 8 }}>{error}</div>}
        </div>
      )}

      {/* Submitting */}
      {phase === 'submitting' && (
        <button className="btn btn-primary" disabled style={{ alignSelf: 'flex-start' }}>
          <span className="spinner" style={{ width: 14, height: 14, marginRight: 6 }} />
          Evaluating…
        </button>
      )}

      {/* Done */}
      {phase === 'done' && result && <Evaluation result={result} />}
    </div>
  )
}
