/**
 * Backend client for the Yale SOM course explorer.
 *
 * /api/courses returns the raw rows from yale_som_classes.json, whose keys
 * carry spaces ("Course Title"). RawCourse mirrors that shape exactly; the UI
 * works with the normalized `Course` returned by `toCourse`.
 */

// In production the FastAPI app serves this bundle, so an empty base keeps
// requests same-origin. Vite dev runs on :5173 and needs the explicit backend.
const BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000'

const PASSWORD_KEY = 'somcourses.password'

export function getPassword(): string {
  return localStorage.getItem(PASSWORD_KEY) ?? ''
}

export function setPassword(value: string): void {
  localStorage.setItem(PASSWORD_KEY, value)
}

export function clearPassword(): void {
  localStorage.removeItem(PASSWORD_KEY)
}

/** Thrown when the backend rejects the shared password, so the UI can re-prompt. */
export class UnauthorizedError extends Error {
  constructor() {
    super('That password was not accepted.')
    this.name = 'UnauthorizedError'
  }
}

export interface RawCourse {
  'Course ID': string
  'Course Number': string
  'Course Title': string
  'Course Category': string
  'Course Type': string
  'Course Description': string
  'Faculty 1': string
  'Faculty 1 Email': string
  faculty_bio: string
  Daytimes: string
  'Timings Day': string
  'Timings StartTime': string
  'Timings EndTime': string
  Room: string
  'Course Session': string
  Section: string
  Units: string
  'Bid Or Permission': string
  Syllabus: string
  'Old Syllabus': string
}

export interface Course {
  id: string
  number: string
  title: string
  category: string
  description: string
  faculty: string
  facultyEmail: string
  facultyBio: string
  daytimes: string
  room: string
  session: string
  section: string
  units: string
  syllabus: string
}

export interface ChatResponse {
  reply: string
  tools_used: string[]
}

/** Several fields in the source data are whitespace-only rather than absent
 *  (Room especially), so everything is trimmed — otherwise `Boolean(value)`
 *  checks in the UI render empty metadata rows. */
const t = (value: string | undefined): string => (value ?? '').trim()

export function toCourse(raw: RawCourse, index: number): Course {
  return {
    id: t(raw['Course ID']) || `row-${index}`,
    number: t(raw['Course Number']),
    title: t(raw['Course Title']),
    category: t(raw['Course Category']),
    description: t(raw['Course Description']),
    faculty: t(raw['Faculty 1']),
    facultyEmail: t(raw['Faculty 1 Email']),
    facultyBio: t(raw.faculty_bio),
    daytimes: t(raw.Daytimes),
    room: t(raw.Room),
    session: t(raw['Course Session']),
    section: t(raw.Section),
    units: t(raw.Units),
    syllabus: t(raw.Syllabus) || t(raw['Old Syllabus']),
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init)
  if (res.status === 401) {
    throw new UnauthorizedError()
  }
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText} — ${path}`)
  }
  return (await res.json()) as T
}

export async function fetchCourses(q?: string): Promise<Course[]> {
  const suffix = q && q.trim() ? `?q=${encodeURIComponent(q.trim())}` : ''
  const data = await request<{ count: number; courses: RawCourse[] }>(
    `/api/courses${suffix}`,
  )
  return data.courses.map(toCourse)
}

export async function sendChat(message: string): Promise<ChatResponse> {
  return request<ChatResponse>('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-App-Password': getPassword() },
    body: JSON.stringify({ message }),
  })
}

export async function fetchHealth(): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>('/api/health')
}

export async function fetchConfig(): Promise<{ password_required: boolean }> {
  return request<{ password_required: boolean }>('/api/config')
}
