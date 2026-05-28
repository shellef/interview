import { useState, useEffect } from 'react'

export default function CheatsheetMode() {
  const [data,    setData]    = useState(null)
  const [loading, setLoading] = useState(false)

  async function load(questionId, topic = null) {
    setLoading(true)
    setData(null)
    try {
      const url = topic
        ? `/practice/cheatsheet?question_id=${questionId}&topic=${encodeURIComponent(topic)}`
        : `/practice/cheatsheet?question_id=${questionId}`
      const res = await fetch(url)
      if (res.ok) setData(await res.json())
    } catch (_) {}
    setLoading(false)
  }

  useEffect(() => {
    let ch
    try {
      ch = new BroadcastChannel('interview-sync')
      ch.onmessage = e => {
        if (e.data?.questionId != null) load(e.data.questionId, e.data.topic || null)
      }
    } catch (_) {}
    return () => { try { ch?.close() } catch (_) {} }
  }, [])

  if (!data && !loading) {
    return (
      <div className="cs-waiting">
        <div className="cs-dot" />
        <p>Waiting for practice session…</p>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="cs-waiting">
        <div className="cs-dot" style={{ background: '#6366f1' }} />
        <p>Generating…</p>
      </div>
    )
  }

  return (
    <div className="cs-wrap">
      {data.topic ? (
        // Follow-up: show focused topic + short answer
        <>
          <div className="cs-topic-focus">{data.topic}</div>
          <div className="cs-answer-block">{data.answer}</div>
        </>
      ) : (
        // Initial question: show category + question + answer
        <>
          <div className="cs-category">{data.category_label}</div>
          <div className="cs-question">{data.question}</div>
          <div className="cs-answer-block">{data.answer}</div>
        </>
      )}
    </div>
  )
}
