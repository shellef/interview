import { useState, useEffect } from 'react'
import PracticeQuestion from './PracticeQuestion.jsx'

export default function RandomMode() {
  const [question, setQuestion] = useState(null)
  const [categories, setCategories] = useState([])
  const [selectedCat, setSelectedCat] = useState('')
  const [loading, setLoading] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState(null)

  // Load categories once
  useEffect(() => {
    fetch('/practice/categories')
      .then(r => r.json())
      .then(d => setCategories(d.categories))
      .catch(() => {})
  }, [])

  async function fetchQuestion() {
    setLoading(true)
    setDone(false)
    setError(null)
    setQuestion(null)
    try {
      const url = selectedCat
        ? `/practice/question?category=${selectedCat}`
        : '/practice/question'
      const res = await fetch(url)
      if (res.status === 401) { window.location.href = '/login'; return }
      if (!res.ok) throw new Error(`Server error ${res.status}`)
      setQuestion(await res.json())
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="random-mode">
      {/* Controls */}
      <div className="random-controls">
        <div className="field">
          <label>Category</label>
          <select value={selectedCat} onChange={e => setSelectedCat(e.target.value)}>
            <option value="">Any</option>
            {categories.map(c => (
              <option key={c.slug} value={c.slug}>{c.label}</option>
            ))}
          </select>
        </div>

        <button
          className="btn btn-primary"
          onClick={fetchQuestion}
          disabled={loading}
        >
          {loading
            ? <><span className="spinner" style={{ width: 14, height: 14, marginRight: 6 }} />Loading…</>
            : question ? 'Next Question' : 'Get Question'
          }
        </button>
      </div>

      {error && <div className="error">{error}</div>}

      {question && (
        <PracticeQuestion
          key={question.id}
          question={question}
          onDone={() => setDone(true)}
        />
      )}

      {done && (
        <div style={{ textAlign: 'center', marginTop: '1.5rem' }}>
          <button className="btn btn-primary" onClick={fetchQuestion}>
            Next Question →
          </button>
        </div>
      )}

      {!question && !loading && !error && (
        <div className="random-empty">
          <p>Pick a category and get a question to practice.</p>
          <p style={{ marginTop: '0.4rem', fontSize: '0.8rem', color: '#475569' }}>
            230 questions across 9 categories. Voice input supported in Chrome.
          </p>
        </div>
      )}
    </div>
  )
}
