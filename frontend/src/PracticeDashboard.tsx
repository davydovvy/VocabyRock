import { useEffect, useState } from 'react'
import { api, type Profile } from './api'

type Attempt = {
  index: number
  word: string
  prompt: string
  correct: boolean | null
  chosen: string | null
  answer: string | string[] | null
  answered_at: string | null
  assisted: boolean
  hint_used: boolean
}
type Session = {
  id: number
  child: string
  pack: string
  kind: string
  mode: string
  direction: string
  started_at: string
  finished_at: string | null
  question_count: number
  answered_count: number
  correct_count: number
  attempts: Attempt[]
}
type Report = {
  summary: { started: number; completed: number; attempts: number; correct: number }
  packs: { date: string; pack: string; started: number; completed: number }[]
  difficult_words: {
    word_id: number | null
    word: string
    attempts: number
    correct: number
    incorrect: number
  }[]
  sessions: Session[]
  pagination: { page: number; page_size: number; total_sessions: number; total_pages: number }
}
const today = () => {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}
const daysAgo = (days: number) => {
  const date = new Date()
  date.setDate(date.getDate() - days)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}
const time = (value: string) => new Date(value).toLocaleString()
const showAnswer = (value: string | string[] | null) =>
  Array.isArray(value) ? value.join(', ') : value || '—'

export default function PracticeDashboard({ children }: { children: Profile[] }) {
  const [start, setStart] = useState(daysAgo(6))
  const [end, setEnd] = useState(today())
  const [childId, setChildId] = useState('')
  const [kind, setKind] = useState('')
  const [page, setPage] = useState(1)
  const [report, setReport] = useState<Report | null>(null)
  const [error, setError] = useState('')
  const [opened, setOpened] = useState<number | null>(null)
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  useEffect(() => {
    if (!start || !end || start > end) {
      setReport(null)
      setError('Choose a valid date range')
      return
    }
    const params = new URLSearchParams({ start, end, tz: timezone, page: String(page) })
    if (childId) params.set('child_id', childId)
    if (kind) params.set('kind', kind)
    let active = true
    setError('')
    setReport(null)
    setOpened(null)
    api<Report>(`/parent/practice-report?${params}`)
      .then((data) => {
        if (active) setReport(data)
      })
      .catch((failure: Error) => {
        if (active) {
          setError(failure.message)
          setReport(null)
        }
      })
    return () => {
      active = false
    }
  }, [start, end, childId, kind, page, timezone])

  return (
    <div className="space-y-6">
      <div>
        <h2 className="section-title">Exercise dashboard</h2>
        <p className="font-bold text-[#747995]">
          Sessions are grouped by their start date in {timezone}.
        </p>
      </div>
      <div className="card p-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="font-bold">
          From
          <input
            aria-label="From date"
            type="date"
            className="field mt-1"
            value={start}
            onChange={(e) => {
              setStart(e.target.value)
              setPage(1)
            }}
          />
        </label>
        <label className="font-bold">
          To
          <input
            aria-label="To date"
            type="date"
            className="field mt-1"
            value={end}
            onChange={(e) => {
              setEnd(e.target.value)
              setPage(1)
            }}
          />
        </label>
        <label className="font-bold">
          Child
          <select
            aria-label="Child filter"
            className="field mt-1"
            value={childId}
            onChange={(e) => {
              setChildId(e.target.value)
              setPage(1)
            }}
          >
            <option value="">All children</option>
            {children.map((child) => (
              <option value={child.id} key={child.id}>
                {child.name}
              </option>
            ))}
          </select>
        </label>
        <label className="font-bold">
          Exercise
          <select
            aria-label="Exercise filter"
            className="field mt-1"
            value={kind}
            onChange={(e) => {
              setKind(e.target.value)
              setPage(1)
            }}
          >
            <option value="">All exercises</option>
            {['match', 'flashcard', 'choice', 'type', 'listen'].map((value) => (
              <option value={value} key={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
      </div>
      {error && (
        <p role="alert" className="card p-4 text-coral font-bold">
          {error}
        </p>
      )}
      {!report && !error && <p className="card p-4 text-[#747995]">Loading exercise history…</p>}
      {report && (
        <>
          <div className="grid gap-3 sm:grid-cols-4">
            {(
              [
                ['Started', report.summary.started],
                ['Completed', report.summary.completed],
                ['Unfinished', report.summary.started - report.summary.completed],
                [
                  'Answer accuracy',
                  report.summary.attempts
                    ? `${Math.round((100 * report.summary.correct) / report.summary.attempts)}%`
                    : '—',
                ],
              ] as const
            ).map(([label, value]) => (
              <div className="card p-4" key={label}>
                <strong className="text-2xl block">{value}</strong>
                <span className="font-bold text-[#747995]">{label}</span>
              </div>
            ))}
          </div>
          <section className="card p-5 overflow-x-auto">
            <h3 className="text-xl font-black mb-3">Exercises by pack and day</h3>
            {report.packs.length ? (
              <table className="w-full text-left">
                <thead>
                  <tr>
                    <th className="py-2 pr-4">Date</th>
                    <th className="pr-4">Word pack</th>
                    <th className="pr-4">Started</th>
                    <th>Completed</th>
                  </tr>
                </thead>
                <tbody>
                  {report.packs.map((row) => (
                    <tr className="border-t" key={`${row.date}-${row.pack}`}>
                      <td className="py-2 pr-4">{row.date}</td>
                      <td className="pr-4">{row.pack}</td>
                      <td className="pr-4">{row.started}</td>
                      <td>{row.completed}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="text-[#747995]">No exercises in this period.</p>
            )}
          </section>
          <section className="card p-5 overflow-x-auto">
            <h3 className="text-xl font-black mb-1">Most difficult words</h3>
            <p className="text-sm text-[#747995] mb-3">
              Ranked by incorrect attempts in this period.
            </p>
            {report.difficult_words.length ? (
              <table className="w-full text-left">
                <thead>
                  <tr>
                    <th className="py-2 pr-4">Word</th>
                    <th className="pr-4">Incorrect</th>
                    <th className="pr-4">Correct</th>
                    <th>Accuracy</th>
                  </tr>
                </thead>
                <tbody>
                  {report.difficult_words.map((row) => (
                    <tr className="border-t" key={`${row.word_id}-${row.word}`}>
                      <td className="py-2 pr-4 font-bold">{row.word}</td>
                      <td className="pr-4">{row.incorrect}</td>
                      <td className="pr-4">{row.correct}</td>
                      <td>{Math.round((100 * row.correct) / row.attempts)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="text-[#747995]">No incorrect answers in this period.</p>
            )}
          </section>
          <section className="space-y-3">
            <h3 className="text-xl font-black">Exercise history</h3>
            <p className="text-sm font-bold text-[#747995]">
              {report.pagination.total_sessions} sessions · {report.pagination.page_size} per page
            </p>
            {report.sessions.length ? (
              report.sessions.map((session) => (
                <article className="card p-4" key={session.id}>
                  <button
                    className="w-full text-left flex flex-wrap justify-between gap-3"
                    aria-expanded={opened === session.id}
                    onClick={() => setOpened(opened === session.id ? null : session.id)}
                  >
                    <span>
                      <strong>{session.child}</strong> · {session.pack} · {session.kind} ·{' '}
                      {session.mode}
                      <small className="block text-[#747995]">
                        Started {time(session.started_at)} ·{' '}
                        {session.finished_at
                          ? `Finished ${time(session.finished_at)}`
                          : 'Unfinished'}
                      </small>
                    </span>
                    <span className="font-bold">
                      {session.correct_count}/{session.question_count} correct ·{' '}
                      {session.answered_count} answered
                    </span>
                  </button>
                  {opened === session.id && (
                    <div className="mt-4 border-t pt-3 space-y-2">
                      {session.attempts.length ? (
                        session.attempts.map((attempt, index) => (
                          <div className="rounded-xl bg-[#f7f3ff] p-3" key={index}>
                            <div className="flex justify-between gap-2">
                              <strong>
                                Question {attempt.index + 1}: {attempt.word}
                              </strong>
                              <span className={attempt.correct ? 'text-green-700' : 'text-coral'}>
                                {attempt.correct === null
                                  ? 'Not answered'
                                  : attempt.correct
                                    ? 'Correct'
                                    : 'Incorrect'}
                              </span>
                            </div>
                            <p>
                              {attempt.prompt} → {showAnswer(attempt.chosen)}
                            </p>
                            <p className="text-sm text-[#747995]">
                              Expected: {showAnswer(attempt.answer)}
                              {attempt.assisted ? ' · Assisted' : ''}
                              {attempt.hint_used ? ' · Hint used' : ''}
                              {attempt.answered_at ? ` · ${time(attempt.answered_at)}` : ''}
                            </p>
                          </div>
                        ))
                      ) : (
                        <p className="text-[#747995]">No answers submitted.</p>
                      )}
                    </div>
                  )}
                </article>
              ))
            ) : (
              <p className="card p-4 text-[#747995]">No exercises in this period.</p>
            )}
          </section>
          {report.pagination.total_pages > 1 && (
            <nav
              aria-label="Exercise history pages"
              className="flex items-center justify-between gap-3"
            >
              <button className="btn-soft" disabled={page === 1} onClick={() => setPage(page - 1)}>
                Previous
              </button>
              <span className="font-bold">
                Page {report.pagination.page} of {report.pagination.total_pages}
              </span>
              <button
                className="btn-soft"
                disabled={page >= report.pagination.total_pages}
                onClick={() => setPage(page + 1)}
              >
                Next
              </button>
            </nav>
          )}
        </>
      )}
    </div>
  )
}
