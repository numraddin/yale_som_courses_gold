import type { ReactNode } from 'react'

/**
 * Minimal markdown renderer for agent replies.
 *
 * The system prompt asks the agent for short markdown lists, so replies arrive
 * with `**bold**`, `` `code` `` and `-` bullets. This handles exactly that
 * subset and nothing else — no dependency, and no dangerouslySetInnerHTML:
 * everything is built as React elements, so reply text can never inject markup.
 */

const INLINE = /(\*\*[^*]+\*\*|`[^`]+`)/g

function inline(text: string, keyPrefix: string): ReactNode[] {
  return text.split(INLINE).filter(Boolean).map((chunk, i) => {
    const key = `${keyPrefix}-${i}`
    if (chunk.startsWith('**') && chunk.endsWith('**')) {
      return <strong key={key}>{chunk.slice(2, -2)}</strong>
    }
    if (chunk.startsWith('`') && chunk.endsWith('`')) {
      return <code key={key}>{chunk.slice(1, -1)}</code>
    }
    return <span key={key}>{chunk}</span>
  })
}

/** A bullet line: optional indent, then -, * or • */
const BULLET = /^(\s*)[-*•]\s+(.*)$/

export function Markdown({ text }: { text: string }) {
  const lines = text.split('\n')
  const blocks: ReactNode[] = []
  let bullets: { depth: number; content: string }[] = []

  const flush = () => {
    if (bullets.length === 0) return
    const items = bullets
    bullets = []
    blocks.push(
      <ul key={`ul-${blocks.length}`} className="md-list">
        {items.map((item, i) => (
          <li key={i} className={item.depth > 0 ? 'md-list__nested' : undefined}>
            {inline(item.content, `li-${blocks.length}-${i}`)}
          </li>
        ))}
      </ul>,
    )
  }

  lines.forEach((raw, i) => {
    const match = raw.match(BULLET)
    if (match) {
      bullets.push({ depth: match[1].length >= 2 ? 1 : 0, content: match[2].trim() })
      return
    }
    flush()
    if (raw.trim()) {
      blocks.push(
        <p key={`p-${i}`} className="md-p">
          {inline(raw.trim(), `p-${i}`)}
        </p>,
      )
    }
  })
  flush()

  return <>{blocks}</>
}
