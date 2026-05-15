import { useState, useEffect, useRef } from 'react'
import { Room, RoomEvent, Track } from 'livekit-client'

const STATUS = {
  idle: 'idle',
  connecting: 'connecting',
  connected: 'connected',
  complete: 'complete',
  ended: 'ended',
}

export default function VoiceInterview() {
  const [status, setStatus] = useState(STATUS.idle)
  const [transcript, setTranscript] = useState([])
  const [agentSpeaking, setAgentSpeaking] = useState(false)
  const agentSilenceTimer = useRef(null)
  const [error, setError] = useState(null)
  const roomRef = useRef(null)
  const audioEls = useRef([])

  async function join() {
    setError(null)
    setStatus(STATUS.connecting)
    setTranscript([])

    try {
      const res = await fetch('/voice/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role: 'commercial airline pilot' }),
      })
      if (!res.ok) throw new Error(`Server error: ${res.status}`)
      const { token, url } = await res.json()

      const room = new Room()
      roomRef.current = room

      room.on(RoomEvent.TrackSubscribed, (track) => {
        if (track.kind === Track.Kind.Audio) {
          const el = track.attach()
          el.style.display = 'none'
          document.body.appendChild(el)
          audioEls.current.push(el)
        }
      })

      room.on(RoomEvent.TrackUnsubscribed, (track) => {
        track.detach().forEach(el => el.remove())
      })

      room.on(RoomEvent.TranscriptionReceived, (segments, participant) => {
        const isAgent = participant?.identity !== 'candidate'
        segments.forEach(seg => {
          if (seg.final && seg.text.trim()) {
            setTranscript(prev => [
              ...prev,
              { speaker: isAgent ? 'interviewer' : 'candidate', text: seg.text.trim() },
            ])
          }
        })
      })

      room.on(RoomEvent.ActiveSpeakersChanged, (speakers) => {
        const agentSpeaks = speakers.some(p => p.identity !== 'candidate')
        if (agentSpeaks) {
          clearTimeout(agentSilenceTimer.current)
          setAgentSpeaking(true)
        } else {
          agentSilenceTimer.current = setTimeout(() => setAgentSpeaking(false), 800)
        }
      })

      room.on(RoomEvent.DataReceived, (data) => {
        if (new TextDecoder().decode(data) === 'interview_complete') {
          setStatus(STATUS.complete)
          setAgentSpeaking(false)
          room.localParticipant.setMicrophoneEnabled(false)
        }
      })

      room.on(RoomEvent.Disconnected, () => {
        setStatus(prev => prev === STATUS.complete ? prev : STATUS.ended)
        setAgentSpeaking(false)
      })

      await room.connect(url, token)
      await room.localParticipant.setMicrophoneEnabled(true)
      setAgentSpeaking(true)
      setStatus(STATUS.connected)
    } catch (e) {
      setError(e.message)
      setStatus(STATUS.idle)
    }
  }

  async function leave() {
    if (roomRef.current) {
      await roomRef.current.disconnect()
      roomRef.current = null
    }
    audioEls.current.forEach(el => el.remove())
    audioEls.current = []
    setStatus(STATUS.idle)
    setTranscript([])
    setAgentSpeaking(false)
  }

  useEffect(() => {
    return () => {
      roomRef.current?.disconnect()
      audioEls.current.forEach(el => el.remove())
      clearTimeout(agentSilenceTimer.current)
    }
  }, [])

  const isIdle = status === STATUS.idle || status === STATUS.ended
  const isConnected = status === STATUS.connected
  const isComplete = status === STATUS.complete

  return (
    <div className="app">
      <div className="setup-card">
        <h2>Voice Interview</h2>
        <p style={{ color: '#94a3b8', fontSize: '0.875rem', margin: '0 0 1rem' }}>
          Commercial airline pilot — 3-question structured interview. Your mic is used live.
        </p>

        <div className="form-row">
          {isIdle && (
            <button className="btn btn-primary" onClick={join}>
              {status === STATUS.ended ? 'Start Again' : 'Start Interview'}
            </button>
          )}

          {status === STATUS.connecting && (
            <div className="status">
              <div className="spinner" />
              Connecting…
            </div>
          )}

          {isConnected && (
            <>
              <MicIndicator speaking={!agentSpeaking} />
              <button className="btn btn-secondary" onClick={leave}>
                End Interview
              </button>
            </>
          )}

          {isComplete && (
            <>
              <span style={{ color: '#22c55e', fontWeight: 600, fontSize: '0.9rem' }}>
                ✓ Interview complete
              </span>
              <button className="btn btn-secondary" onClick={leave}>
                Start Again
              </button>
            </>
          )}
        </div>

        {error && <div className="error">{error}</div>}

        {isConnected && (
          <div style={{ marginTop: '0.75rem', fontSize: '0.8rem', color: '#64748b' }}>
            {agentSpeaking ? 'Interviewer is speaking…' : 'Your turn — speak now'}
          </div>
        )}
      </div>

      {transcript.length > 0 && (
        <div className="transcript">
          {transcript.map((t, i) => (
            <div key={i} className={`turn ${t.speaker}`}>
              <span className="turn-label">
                {t.speaker === 'interviewer' ? 'Interviewer' : 'You'}
              </span>
              <div className="turn-bubble">{t.text}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function MicIndicator({ speaking }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.85rem', color: speaking ? '#22c55e' : '#94a3b8' }}>
      <span style={{ width: 8, height: 8, borderRadius: '50%', background: speaking ? '#22c55e' : '#475569', display: 'inline-block', boxShadow: speaking ? '0 0 6px #22c55e' : 'none' }} />
      {speaking ? 'Mic on' : 'Listening…'}
    </div>
  )
}
