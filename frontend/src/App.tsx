import { useEffect, useMemo, useState } from 'react'
import { fetchCourses, type Course } from './api'
import { CourseCard } from './components/CourseCard'
import { ChatPanel } from './components/ChatPanel'
import './App.css'

export default function App() {
  const [courses, setCourses] = useState<Course[]>([])
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Debounced server-side search so typing doesn't fire a request per keystroke.
  // `cancelled` lives in the effect body, not inside the timeout callback — a
  // cleanup returned from setTimeout is never called, which would let a slow
  // response for an old query overwrite a newer one.
  useEffect(() => {
    let cancelled = false

    const handle = setTimeout(() => {
      setLoading(true)
      fetchCourses(query)
        .then((rows) => {
          if (cancelled) return
          setCourses(rows)
          setError(null)
        })
        .catch((err: unknown) => {
          if (cancelled) return
          setError(
            err instanceof Error
              ? `${err.message} — is the backend running on port 8000?`
              : 'Could not load courses.',
          )
        })
        .finally(() => {
          if (!cancelled) setLoading(false)
        })
    }, 250)

    return () => {
      cancelled = true
      clearTimeout(handle)
    }
  }, [query])

  const categories = useMemo(() => {
    const seen = new Set(courses.map((c) => c.category).filter(Boolean))
    return seen.size
  }, [courses])

  return (
    <div className="app">
      <div className="app__glow" aria-hidden="true" />

      <header className="masthead">
        <div className="masthead__brand">
          <span className="masthead__orb" aria-hidden="true" />
          <div>
            <h1 className="masthead__title">
              Yale SOM <span>Course Explorer</span>
            </h1>
            <p className="masthead__tag">Scout the catalog. Ask the assistant.</p>
          </div>
        </div>

        <div className="masthead__stats">
          <div className="stat">
            <span className="stat__value">{loading ? '—' : courses.length}</span>
            <span className="stat__label">courses</span>
          </div>
          <div className="stat">
            <span className="stat__value">{loading ? '—' : categories}</span>
            <span className="stat__label">categories</span>
          </div>
        </div>
      </header>

      <div className="layout">
        <main className="catalog">
          <div className="search">
            <input
              className="search__input"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search title, faculty, number, day…"
              aria-label="Search courses"
            />
            {query && (
              <button
                type="button"
                className="search__clear"
                onClick={() => setQuery('')}
                aria-label="Clear search"
              >
                ×
              </button>
            )}
          </div>

          {error && <div className="notice notice--error">{error}</div>}

          {loading && <div className="notice">Loading catalog…</div>}

          {!loading && !error && courses.length === 0 && (
            <div className="notice">
              No courses match <strong>{query}</strong>.
            </div>
          )}

          <div className="grid">
            {courses.map((c, i) => (
              <CourseCard key={`${c.id}-${c.section}-${i}`} course={c} />
            ))}
          </div>
        </main>

        <aside className="sidebar">
          <ChatPanel />
        </aside>
      </div>
    </div>
  )
}
