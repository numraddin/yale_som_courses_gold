import { useState } from 'react'
import type { Course } from '../api'

interface Props {
  course: Course
}

/** Session labels in the data are "fall-1" / "fall-2" / "full-term". */
function sessionLabel(session: string): string {
  if (!session) return ''
  return session
    .split('-')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

export function CourseCard({ course }: Props) {
  const [open, setOpen] = useState(false)
  const hasDetail = Boolean(course.description || course.facultyBio)

  return (
    <article className={`course-card${open ? ' is-open' : ''}`}>
      <header className="course-card__head">
        <span className="course-card__number">{course.number || '—'}</span>
        {course.session && (
          <span className="course-card__session">{sessionLabel(course.session)}</span>
        )}
      </header>

      <h3 className="course-card__title">{course.title || 'Untitled course'}</h3>

      <dl className="course-card__meta">
        {course.faculty && (
          <div>
            <dt>Faculty</dt>
            <dd>{course.faculty}</dd>
          </div>
        )}
        {course.daytimes && (
          <div>
            <dt>Meets</dt>
            <dd>{course.daytimes}</dd>
          </div>
        )}
        {course.room && (
          <div>
            <dt>Room</dt>
            <dd>{course.room}</dd>
          </div>
        )}
        {course.units && (
          <div>
            <dt>Units</dt>
            <dd>{course.units}</dd>
          </div>
        )}
      </dl>

      {course.category && <span className="course-card__tag">{course.category}</span>}

      {hasDetail && (
        <>
          <button
            type="button"
            className="course-card__toggle"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
          >
            {open ? 'Hide details' : 'Details'}
          </button>

          {open && (
            <div className="course-card__detail">
              {course.description && (
                <p className="course-card__desc">{course.description}</p>
              )}
              {course.facultyBio && (
                <p className="course-card__bio">
                  <strong>{course.faculty}</strong> — {course.facultyBio}
                </p>
              )}
              {course.facultyEmail && (
                <a className="course-card__link" href={`mailto:${course.facultyEmail}`}>
                  {course.facultyEmail}
                </a>
              )}
              {course.syllabus && (
                <a
                  className="course-card__link"
                  href={course.syllabus}
                  target="_blank"
                  rel="noreferrer"
                >
                  Syllabus →
                </a>
              )}
            </div>
          )}
        </>
      )}
    </article>
  )
}
