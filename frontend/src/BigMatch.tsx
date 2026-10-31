import { useRef, useState, type PointerEvent } from 'react'
import { ArrowLeft, RotateCcw } from 'lucide-react'
import { api, json, type Practice } from './api'

type Drag = {
  token: number
  pointerId: number
  x: number
  y: number
  startX: number
  startY: number
  moved: boolean
}

export default function BigMatch({
  practice,
  onHome,
  onUpdate,
  onFinish,
  onSuccess,
}: {
  practice: Practice
  onHome: () => void
  onUpdate: (session: Practice) => void
  onFinish: () => void
  onSuccess: () => void
}) {
  const [placements, setPlacements] = useState<Record<number, number>>(() =>
    Object.fromEntries(
      practice.tasks.flatMap((task, index) =>
        task.last_token === undefined ? [] : [[index, task.last_token]],
      ),
    ),
  )
  const [selected, setSelected] = useState<number | null>(null)
  const [drag, setDrag] = useState<Drag | null>(null)
  const [hovered, setHovered] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const dragRef = useRef<Drag | null>(null)
  const options = practice.match_options || []
  const ownerOf = (token: number) =>
    Object.keys(placements).find((index) => placements[Number(index)] === token)
  const placed = Object.keys(placements).length
  const checked = practice.results.length > 0
  const lockedCount = practice.tasks.filter((task) => task.locked).length
  const changed = practice.tasks.some((task, index) => placements[index] !== task.last_token)

  const place = (token: number, index: number) => {
    if (practice.tasks[index].locked || busy) return
    setPlacements((current) => {
      const next = { ...current }
      const previous = Object.keys(next).find((key) => next[Number(key)] === token)
      if (previous !== undefined && practice.tasks[Number(previous)].locked) return current
      if (previous !== undefined) delete next[Number(previous)]
      next[index] = token
      return next
    })
    setSelected(null)
  }
  const returnToPool = (token: number) => {
    setPlacements((current) => {
      const next = { ...current }
      const previous = Object.keys(next).find((key) => next[Number(key)] === token)
      if (previous !== undefined && !practice.tasks[Number(previous)].locked)
        delete next[Number(previous)]
      return next
    })
    setSelected(null)
  }
  const check = async () => {
    setBusy(true)
    setError('')
    try {
      const updated = await api<Practice>(
        `/practice/${practice.id}/match-all`,
        json('POST', {
          pairs: practice.tasks.map((_, index) => ({ index, option_id: placements[index] })),
        }),
      )
      onUpdate(updated)
      if (updated.finished) {
        onSuccess()
        onFinish()
      }
    } catch (cause) {
      setError((cause as Error).message)
    } finally {
      setBusy(false)
    }
  }
  const startDrag = (event: PointerEvent<HTMLButtonElement>, token: number) => {
    if (busy) return
    const owner = ownerOf(token)
    if (owner !== undefined && practice.tasks[Number(owner)].locked) return
    event.currentTarget.setPointerCapture?.(event.pointerId)
    dragRef.current = {
      token,
      pointerId: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      startX: event.clientX,
      startY: event.clientY,
      moved: false,
    }
  }
  const moveDrag = (event: PointerEvent<HTMLButtonElement>) => {
    const current = dragRef.current
    if (!current || current.pointerId !== event.pointerId) return
    const moved =
      current.moved ||
      Math.hypot(event.clientX - current.startX, event.clientY - current.startY) > 7
    dragRef.current = { ...current, x: event.clientX, y: event.clientY, moved }
    if (moved) {
      setDrag(dragRef.current)
      const card = document
        .elementFromPoint(event.clientX, event.clientY)
        ?.closest('[data-match-card]')
      setHovered(card ? Number(card.getAttribute('data-match-card')) : null)
    }
  }
  const endDrag = (event: PointerEvent<HTMLButtonElement>) => {
    const current = dragRef.current
    if (!current || current.pointerId !== event.pointerId) return
    if (current.moved) {
      const target = document.elementFromPoint(event.clientX, event.clientY)
      const card = target?.closest('[data-match-card]')
      if (card) place(current.token, Number(card.getAttribute('data-match-card')))
      else if (target?.closest('[data-match-pool]')) returnToPool(current.token)
    } else {
      setSelected((old) => (old === current.token ? null : current.token))
    }
    dragRef.current = null
    setDrag(null)
    setHovered(null)
  }
  const cancelDrag = () => {
    dragRef.current = null
    setDrag(null)
    setHovered(null)
  }
  const tile = (token: number) => {
    const option = options.find((item) => item.token === token)
    if (!option) return null
    const owner = ownerOf(token)
    const locked = owner !== undefined && practice.tasks[Number(owner)].locked
    return (
      <button
        key={token}
        type="button"
        className={`big-match-tile ${selected === token ? 'is-selected' : ''} ${drag?.token === token ? 'is-dragging' : ''}`}
        aria-label={option.text}
        aria-pressed={selected === token}
        disabled={locked || busy}
        onPointerDown={(event) => startDrag(event, token)}
        onPointerMove={moveDrag}
        onPointerUp={endDrag}
        onPointerCancel={cancelDrag}
        onClick={(event) => {
          event.stopPropagation()
          if (event.detail === 0 && !locked) setSelected((old) => (old === token ? null : token))
        }}
      >
        {option.text}
      </button>
    )
  }

  return (
    <div className="big-match" aria-label="Big Match puzzle">
      <div className="big-match-heading">
        <button className="btn-soft" onClick={onHome}>
          <ArrowLeft size={20} /> Back
        </button>
        <div>
          <h1>Big Match!</h1>
          <p>Drag words to match!</p>
        </div>
        <strong>{placed} / 8 placed</strong>
      </div>
      {error && (
        <p role="alert" className="big-match-error">
          {error}
        </p>
      )}
      <div className="big-match-board">
        <div className="big-match-english" role="group" aria-label="English words">
          {practice.tasks.map((task, index) => {
            const token = placements[index]
            const showingLastCheck = checked && token === task.last_token
            const state = task.locked ? 'is-correct' : showingLastCheck ? 'is-incorrect' : ''
            return (
              <div
                key={index}
                data-match-card={index}
                className={`big-match-card ${state} ${hovered === index && !task.locked ? 'is-hovered' : ''}`}
                role="button"
                tabIndex={task.locked ? -1 : 0}
                aria-label={`${task.prompt}, ${token === undefined ? 'empty' : 'filled'}`}
                onClick={() => {
                  if (selected !== null) place(selected, index)
                }}
                onKeyDown={(event) => {
                  if ((event.key === 'Enter' || event.key === ' ') && selected !== null) {
                    event.preventDefault()
                    place(selected, index)
                  }
                }}
              >
                <span className="big-match-word">{task.prompt}</span>
                <span className="big-match-slot">
                  {token === undefined ? <span aria-hidden="true">Drop here</span> : tile(token)}
                </span>
              </div>
            )
          })}
        </div>
        <div
          className="big-match-pool"
          data-match-pool
          role="group"
          aria-label="Russian translations"
        >
          {options.map((option) => (
            <div key={option.token} className="big-match-pool-cell">
              {ownerOf(option.token) === undefined ? tile(option.token) : null}
            </div>
          ))}
        </div>
      </div>
      <div className="big-match-footer">
        <button
          className="btn-soft"
          disabled={busy || placed === lockedCount}
          onClick={() => {
            setPlacements(
              Object.fromEntries(
                practice.tasks.flatMap((task, index) =>
                  task.locked && task.last_token !== undefined ? [[index, task.last_token]] : [],
                ),
              ),
            )
            setSelected(null)
          }}
        >
          <RotateCcw size={18} /> Reset
        </button>
        <p role="status">
          {checked
            ? `${lockedCount} right! ${8 - lockedCount ? `Fix ${8 - lockedCount} more!` : 'You Rock!'}`
            : `${placed} / 8 placed`}
        </p>
        <button
          className="btn-primary"
          disabled={busy || placed !== 8 || (checked && !changed)}
          onClick={() => void check()}
        >
          Check
        </button>
      </div>
      {drag && (
        <div className="big-match-ghost" style={{ left: drag.x, top: drag.y }}>
          {options.find((option) => option.token === drag.token)?.text}
        </div>
      )}
    </div>
  )
}
