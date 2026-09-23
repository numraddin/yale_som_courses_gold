import { useEffect, useRef, useState } from 'react'
import {
  UnauthorizedError,
  fetchConfig,
  getPassword,
  sendChat,
  setPassword,
} from '../api'
import { Markdown } from './Markdown'

interface Message {
  role: 'user' | 'assistant'
  text: string
  tools?: string[]
  error?: boolean
}

const SUGGESTIONS = [
  'Which courses cover negotiation?',
  'What does Daylian Cain teach?',
  'Show me fall-1 accounting courses',
]

/** Friendly labels for the two tools the agent can reach for. */
const TOOL_LABELS: Record<string, string> = {
  search_courses: 'course catalog',
  web_search: 'web search',
}

export function ChatPanel() {
  const [messages, setMessages] = useState<Message[]>([])
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  // null until /api/config answers, so the gate does not flash on local dev.
  const [locked, setLocked] = useState<boolean | null>(null)
  const [pwDraft, setPwDraft] = useState('')
  const [pwError, setPwError] = useState('')
  const logRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, busy])

  useEffect(() => {
    fetchConfig()
      .then((cfg) => setLocked(cfg.password_required && !getPassword()))
      .catch(() => setLocked(false))
  }, [])

  function unlock(e: React.FormEvent) {
    e.preventDefault()
    if (!pwDraft.trim()) return
    setPassword(pwDraft.trim())
    setPwDraft('')
    setPwError('')
    setLocked(false)
  }

  async function submit(text: string) {
    const message = text.trim()
    if (!message || busy || locked) return

    setMessages((prev) => [...prev, { role: 'user', text: message }])
    setDraft('')
    setBusy(true)

    try {
      const res = await sendChat(message)
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', text: res.reply, tools: res.tools_used },
      ])
    } catch (err) {
      // A rejected password sends the visitor back to the gate rather than
      // leaving a dead-end error in the log.
      if (err instanceof UnauthorizedError) {
        setPwError('That password was not accepted. Try again.')
        setLocked(true)
        setMessages((prev) => prev.slice(0, -1))
        return
      }
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          text:
            err instanceof Error
              ? `Could not reach the agent — ${err.message}`
              : 'Could not reach the agent.',
          error: true,
        },
      ])
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="chat" aria-label="Course assistant">
      <header className="chat__head">
        <span className="chat__aura" aria-hidden="true" />
        <div>
          <h2 className="chat__title">Course Assistant</h2>
          <p className="chat__sub">Powered up on the SOM catalog</p>
        </div>
      </header>

      {locked && (
        <div className="chat__gate">
          <p className="chat__gate-copy">
            This assistant is password protected. Enter the shared password to
            start asking questions.
          </p>
          <form className="chat__form" onSubmit={unlock}>
            <input
              className="chat__input"
              type="password"
              value={pwDraft}
              onChange={(e) => setPwDraft(e.target.value)}
              placeholder="Password"
              aria-label="Shared password"
            />
            <button className="chat__send" type="submit" disabled={!pwDraft.trim()}>
              Unlock
            </button>
          </form>
          {pwError && <p className="chat__gate-error">{pwError}</p>}
        </div>
      )}

      <div className="chat__log" ref={logRef}>
        {messages.length === 0 && !busy && (
          <div className="chat__empty">
            <p>Ask about courses, faculty, or schedules.</p>
            <div className="chat__suggestions">
              {SUGGESTIONS.map((s) => (
                <button key={s} type="button" onClick={() => submit(s)}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <div
            key={i}
            className={`bubble bubble--${m.role}${m.error ? ' bubble--error' : ''}`}
          >
            <div className="bubble__text">
              {m.role === 'assistant' && !m.error ? (
                <Markdown text={m.text} />
              ) : (
                m.text
              )}
            </div>
            {m.tools && m.tools.length > 0 && (
              <div className="bubble__tools">
                {m.tools.map((t) => (
                  <span key={t} className="tool-chip">
                    {TOOL_LABELS[t] ?? t}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}

        {busy && (
          <div className="bubble bubble--assistant bubble--thinking">
            <span className="charge" aria-hidden="true">
              <i />
              <i />
              <i />
            </span>
            <span className="charge__label">Charging up…</span>
          </div>
        )}
      </div>

      <form
        className="chat__form"
        onSubmit={(e) => {
          e.preventDefault()
          submit(draft)
        }}
      >
        <input
          className="chat__input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Ask about a course…"
          disabled={busy || !!locked}
          aria-label="Message"
        />
        <button
          className="chat__send"
          type="submit"
          disabled={busy || !!locked || !draft.trim()}
        >
          {busy ? '…' : 'Send'}
        </button>
      </form>
    </section>
  )
}
