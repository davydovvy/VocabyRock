import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  CircleHelp,
  Grid2X2,
  Headphones,
  Heart,
  Home,
  Keyboard,
  Layers3,
  RotateCcw,
  Settings2,
  Shuffle,
  Sparkles,
  Star as StarIcon,
  Volume2,
  X,
} from 'lucide-react'
import {
  api,
  json,
  type Config,
  type Kind,
  type Mode,
  type Pack,
  type Practice,
  type Profile,
  type Stats,
  type Word,
} from './api'
import { animal, Empty, packArt, ProgressBar, Shell, Speak, Star } from './ui'

const games: { kind: Kind; title: string; icon: typeof Layers3; color: string }[] = [
  { kind: 'choice', title: 'Pick the Word', icon: CircleHelp, color: 'bg-[#d8eaff]' },
  { kind: 'match', title: 'Find Pairs', icon: Shuffle, color: 'bg-[#ffe3e7]' },
  { kind: 'match_all', title: 'Find Pairs Challenge', icon: Grid2X2, color: 'bg-[#ffd9e0]' },
  { kind: 'flashcard', title: 'Flip Cards', icon: Layers3, color: 'bg-[#e6ddff]' },
  { kind: 'type', title: 'Type It', icon: Keyboard, color: 'bg-[#e1f7e7]' },
  { kind: 'listen', title: 'Listen', icon: Headphones, color: 'bg-[#fff0ca]' },
]
const modes: { mode: Mode; title: string; emoji: string; hint: string }[] = [
  { mode: 'new', title: 'New Words', emoji: '🌱', hint: 'Meet new words' },
  { mode: 'practice', title: 'Practice', emoji: '🎯', hint: 'Words ready now' },
  { mode: 'hard', title: 'Hard Words', emoji: '💪', hint: 'Give them a try' },
  { mode: 'all', title: 'All Words', emoji: '🌈', hint: 'Play them all' },
]

type View = 'home' | 'choose' | 'game' | 'words' | 'settings'

export default function Child({
  user,
  config,
  onLogout,
  onUserChange,
}: {
  user: Profile
  config: Config
  onLogout: () => void
  onUserChange: (user: Profile) => void
}) {
  const [view, setView] = useState<View>('home')
  const [packs, setPacks] = useState<Pack[]>([])
  const [stats, setStats] = useState<Stats | null>(null)
  const [words, setWords] = useState<Word[]>([])
  const [pack, setPack] = useState<Pack | null>(null)
  const [mode, setMode] = useState<Mode>('all')
  const [direction, setDirection] = useState(config.direction)
  const [practice, setPractice] = useState<Practice | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [avatar, setAvatar] = useState(user.avatar)
  const [sound, setSound] = useState(user.sound_enabled ?? true)

  const playSuccess = () => {
    if (!sound) return
    const AudioContextClass = window.AudioContext
    if (!AudioContextClass) return
    const context = new AudioContextClass()
    for (const [index, frequency] of [523, 659, 784].entries()) {
      const oscillator = context.createOscillator()
      const gain = context.createGain()
      oscillator.type = 'sine'
      oscillator.frequency.value = frequency
      gain.gain.setValueAtTime(0.0001, context.currentTime + index * 0.09)
      gain.gain.exponentialRampToValueAtTime(0.09, context.currentTime + index * 0.09 + 0.02)
      gain.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + index * 0.09 + 0.2)
      oscillator.connect(gain).connect(context.destination)
      oscillator.start(context.currentTime + index * 0.09)
      oscillator.stop(context.currentTime + index * 0.09 + 0.21)
    }
    window.setTimeout(() => void context.close(), 800)
  }

  const refresh = async () => {
    const [nextPacks, nextStats, nextUser] = await Promise.all([
      api<Pack[]>('/packs'),
      api<Stats>('/stats'),
      api<Profile>('/auth/me'),
    ])
    setPacks(nextPacks)
    setStats(nextStats)
    onUserChange(nextUser)
  }
  useEffect(() => {
    void refresh().catch((e) => setError(e.message))
  }, [])

  const start = async (kind: Kind, chosenMode = mode, chosenPack = pack, wordIds?: number[]) => {
    setBusy(true)
    setError('')
    try {
      const next = await api<Practice>(
        '/practice',
        json('POST', {
          pack_id: chosenPack?.id ?? null,
          mode: chosenMode,
          kind,
          direction,
          word_ids: wordIds,
        }),
      )
      setPractice(next)
      setView('game')
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  const goHome = () => {
    setPractice(null)
    setView('home')
    setError('')
    void refresh().catch(() => {})
  }
  const openPack = (next: Pack | null) => {
    setPack(next)
    setMode('all')
    setView('choose')
    setError('')
  }
  const showWords = async () => {
    setError('')
    try {
      setWords(await api<Word[]>('/words'))
      setView('words')
    } catch (e) {
      setError((e as Error).message)
    }
  }
  const saveSettings = async () => {
    setError('')
    try {
      const next = await api<Profile>(
        `/profiles/${user.id}`,
        json('PATCH', { avatar, sound_enabled: sound }),
      )
      onUserChange(next)
      setView('home')
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <Shell
      right={
        <div className="flex items-center gap-2 md:gap-4">
          <span className="hidden sm:inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 font-black">
            <Star /> {user.stars ?? 0}
          </span>
          <button className="btn-soft" onClick={() => setView('settings')} aria-label="Settings">
            <Settings2 size={22} />
          </button>
          <button className="btn-soft" onClick={onLogout}>
            Switch
          </button>
        </div>
      }
    >
      {error && (
        <div
          role="alert"
          className="mb-5 rounded-2xl bg-[#ffe5e3] px-5 py-4 font-bold text-[#a54141]"
        >
          {error}
        </div>
      )}
      {view === 'home' && (
        <>
          <section className="relative overflow-hidden rounded-[2.5rem] bg-gradient-to-br from-[#7460dd] via-[#6d62da] to-[#53b8d8] p-6 md:p-10 text-white shadow-card min-h-[290px] flex items-center">
            <div className="absolute right-4 top-1 text-[7rem] opacity-15" aria-hidden="true">
              ✦
            </div>
            <div className="relative z-10 max-w-xl">
              <span className="inline-block rounded-full bg-white/20 px-4 py-1 text-sm font-black">
                LEVEL {Math.floor((user.xp ?? 0) / 100) + 1} EXPLORER
              </span>
              <h1 className="mt-4 text-4xl md:text-5xl font-black leading-tight">
                Hi, {user.name}!<br />
                Ready to play?
              </h1>
              <p className="mt-2 text-lg font-bold text-white/90">
                {stats?.due
                  ? `${stats.due} words are ready for you`
                  : 'New words are waiting for you!'}
              </p>
              <button
                disabled={busy}
                className="btn-coral mt-6 text-xl px-9"
                onClick={() => void start('choice', 'quick', null)}
              >
                ▶ Play
              </button>
            </div>
            <div
              className="hidden md:block absolute right-[9%] bottom-4 floaty rounded-full bg-white/20 p-6 text-[7rem]"
              aria-hidden="true"
            >
              {animal[user.avatar] || '🦊'}
            </div>
          </section>
          <div className="mt-8 grid gap-4 sm:grid-cols-3">
            <div className="card p-5 flex items-center gap-4">
              <div className="rounded-2xl bg-[#fff0ca] p-3">
                <Star />
              </div>
              <div>
                <p className="font-black text-2xl">{user.stars ?? 0}</p>
                <p className="text-[#6b7190] font-bold">My Stars</p>
              </div>
            </div>
            <div className="card p-5 flex items-center gap-4">
              <div className="rounded-2xl bg-[#e2f8eb] p-3">
                <BookOpen className="text-mint" />
              </div>
              <div>
                <p className="font-black text-2xl">{stats?.learned ?? 0}</p>
                <p className="text-[#6b7190] font-bold">Words learned</p>
              </div>
            </div>
            <button
              className="card p-5 flex items-center gap-4 text-left hover:-translate-y-1 transition-transform"
              onClick={() => void showWords()}
            >
              <div className="rounded-2xl bg-[#e9e2ff] p-3">
                <BookOpen className="text-violet" />
              </div>
              <div>
                <p className="font-black text-xl">My Words</p>
                <p className="text-[#6b7190] font-bold">Take a look</p>
              </div>
              <ArrowRight className="ml-auto text-violet" />
            </button>
          </div>
          {stats && stats.achievements.length > 0 && (
            <div className="mt-6 flex flex-wrap items-center gap-2">
              <span className="font-black">My badges:</span>
              {stats.achievements.map((badge) => (
                <span key={badge} className="rounded-full bg-[#fff0ca] px-4 py-2 font-black">
                  🏅 {badge}
                </span>
              ))}
            </div>
          )}
          <div className="mt-12 flex items-end justify-between gap-4">
            <div>
              <p className="text-violet font-black uppercase tracking-widest text-sm">
                Pick an adventure
              </p>
              <h2 className="section-title mt-1">Word packs</h2>
            </div>
            <button
              className="font-black text-violet hover:underline"
              onClick={() => openPack(null)}
            >
              All words →
            </button>
          </div>
          <div className="mt-5 grid gap-5 md:grid-cols-2 xl:grid-cols-3">
            {packs.map((item) => {
              const art = packArt[item.name] || { emoji: '🎒', bg: 'bg-[#e8e1ff]' }
              return (
                <article className="card p-5" key={item.id}>
                  <div
                    className={`${art.bg} h-40 rounded-[1.5rem] flex items-center justify-center overflow-hidden`}
                  >
                    {item.cover ? (
                      <img className="w-full h-full object-cover" src={item.cover} alt="" />
                    ) : (
                      <span className="text-[5.5rem] floaty" aria-hidden="true">
                        {art.emoji}
                      </span>
                    )}
                  </div>
                  <div className="mt-5 flex items-start justify-between gap-2">
                    <div>
                      <h3 className="font-black text-2xl">{item.name}</h3>
                      <p className="text-[#6b7190] font-bold">{item.description}</p>
                    </div>
                    <span className="rounded-full bg-[#f4efff] px-3 py-1 text-sm font-black text-violet">
                      {item.word_count}
                    </span>
                  </div>
                  <div className="mt-4">
                    <div className="mb-2 flex justify-between text-sm font-black text-[#6b7190]">
                      <span>My progress</span>
                      <span>
                        {item.learned_count}/{item.word_count}
                      </span>
                    </div>
                    <ProgressBar
                      value={item.word_count ? (item.learned_count / item.word_count) * 100 : 0}
                    />
                  </div>
                  <button className="btn-primary mt-5 w-full" onClick={() => openPack(item)}>
                    Play <ArrowRight size={20} />
                  </button>
                </article>
              )
            })}
          </div>
        </>
      )}
      {view === 'choose' && (
        <>
          <button className="btn-soft mb-6" onClick={goHome}>
            <ArrowLeft /> Back
          </button>
          <div className="card p-6 md:p-9">
            <div className="flex items-center gap-5">
              <div className="rounded-3xl bg-[#fff0c7] p-5 text-5xl" aria-hidden="true">
                {pack ? packArt[pack.name]?.emoji || '🎒' : '🌈'}
              </div>
              <div>
                <p className="text-violet font-black uppercase tracking-widest text-sm">
                  Adventure
                </p>
                <h1 className="section-title">{pack?.name || 'All Words'}</h1>
                <p className="text-[#6b7190] font-bold">
                  {pack?.word_count ?? 'Lots of'} words to play
                </p>
              </div>
            </div>
            <h2 className="mt-9 text-xl font-black">Pick words</h2>
            <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-3">
              {modes.map((item) => (
                <button
                  key={item.mode}
                  onClick={() => setMode(item.mode)}
                  className={`rounded-2xl border-2 p-4 text-left min-h-28 transition-transform hover:-translate-y-1 ${mode === item.mode ? 'border-violet bg-[#f0eaff]' : 'border-[#e9e5f4] bg-white'}`}
                  aria-pressed={mode === item.mode}
                >
                  <span className="text-3xl" aria-hidden="true">
                    {item.emoji}
                  </span>
                  <span className="block font-black mt-1">{item.title}</span>
                  <span className="block text-xs font-bold text-[#7d829d]">{item.hint}</span>
                </button>
              ))}
            </div>
            <h2 className="mt-9 text-xl font-black">Pick a game</h2>
            <div className="mt-3 grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
              {games
                .filter((game) =>
                  config.allowed_exercises.includes(
                    game.kind === 'match_all' ? 'match' : game.kind,
                  ),
                )
                .map((game) => (
                  <button
                    disabled={busy}
                    key={game.kind}
                    onClick={() => void start(game.kind)}
                    className={`${game.color} min-h-32 rounded-2xl p-4 font-black text-center hover:-translate-y-1 transition-transform border-2 border-white shadow-sm`}
                  >
                    <game.icon className="mx-auto mb-2 text-violet" size={30} />
                    {game.title}
                  </button>
                ))}
            </div>
            {!('speechSynthesis' in window) && (
              <p className="mt-4 font-bold text-[#9b5b45]">
                Device voice is unavailable. Words with saved recordings can still play offline.
              </p>
            )}
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <span className="font-black">Words go:</span>
              <button
                aria-pressed={direction === 'en-ru'}
                className={direction === 'en-ru' ? 'btn-primary' : 'btn-soft'}
                onClick={() => setDirection('en-ru')}
              >
                English → Russian
              </button>
              <button
                aria-pressed={direction === 'ru-en'}
                className={direction === 'ru-en' ? 'btn-primary' : 'btn-soft'}
                onClick={() => setDirection('ru-en')}
              >
                Russian → English
              </button>
            </div>
          </div>
        </>
      )}
      {view === 'game' && practice && (
        <Game
          key={practice.id}
          practice={practice}
          config={config}
          onHome={goHome}
          onAgain={(mistakes) => {
            if (mistakes?.length)
              void start(
                practice.kind === 'match_all' ? 'choice' : practice.kind,
                'mistakes',
                pack,
                mistakes,
              )
            else
              void start(practice.kind, practice.kind === 'match_all' ? 'all' : practice.mode, pack)
          }}
          onUpdate={setPractice}
          onFinish={() => void refresh().catch(() => {})}
          onSuccess={playSuccess}
        />
      )}
      {view === 'words' && (
        <>
          <button className="btn-soft mb-6" onClick={goHome}>
            <ArrowLeft /> Back
          </button>
          <h1 className="section-title mb-6">My Words</h1>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {words.map((word) => (
              <article className="card p-5" key={word.id}>
                <div className="flex items-center gap-4">
                  {word.picture ? (
                    <img className="h-20 w-20 rounded-2xl object-cover" src={word.picture} alt="" />
                  ) : (
                    <div
                      className="h-20 w-20 rounded-2xl bg-[#eae3ff] flex items-center justify-center text-4xl"
                      aria-hidden="true"
                    >
                      ✦
                    </div>
                  )}
                  <div>
                    <h2 className="font-black text-xl">{word.english}</h2>
                    <p className="font-bold text-[#6b7190]">{word.translations.join(', ')}</p>
                    <p className="text-sm text-violet">{word.ipa}</p>
                  </div>
                </div>
                <div className="mt-4">
                  <Speak word={word.english} accent={config.accent} />
                </div>
              </article>
            ))}
          </div>
        </>
      )}
      {view === 'settings' && (
        <>
          <button className="btn-soft mb-6" onClick={goHome}>
            <ArrowLeft /> Back
          </button>
          <div className="card p-7 max-w-2xl">
            <h1 className="section-title">My Settings</h1>
            <p className="font-black mt-7 mb-3">My avatar</p>
            <div className="grid grid-cols-4 gap-3">
              {config.avatars.map((item) => (
                <button
                  key={item}
                  disabled={!config.child_avatar_change}
                  aria-label={item}
                  aria-pressed={avatar === item}
                  className={`rounded-2xl p-3 text-4xl ${avatar === item ? 'bg-[#e8e0ff] ring-4 ring-violet' : 'bg-[#f7f4fc]'}`}
                  onClick={() => setAvatar(item)}
                >
                  {animal[item]}
                </button>
              ))}
            </div>
            <label className="mt-7 flex items-center gap-3 font-black">
              <input
                type="checkbox"
                checked={sound}
                onChange={(e) => setSound(e.target.checked)}
                className="h-6 w-6 accent-violet"
              />
              Sound effects
            </label>
            <button className="btn-primary mt-8" onClick={() => void saveSettings()}>
              Save
            </button>
          </div>
        </>
      )}
    </Shell>
  )
}

function Game({
  practice,
  config,
  onHome,
  onAgain,
  onUpdate,
  onFinish,
  onSuccess,
}: {
  practice: Practice
  config: Config
  onHome: () => void
  onAgain: (mistakes?: number[]) => void
  onUpdate: (session: Practice) => void
  onFinish: () => void
  onSuccess: () => void
}) {
  const [index, setIndex] = useState(() =>
    practice.tasks.findIndex((_, i) => !practice.results.some((result) => result.index === i)),
  )
  const [selected, setSelected] = useState<number | null>(null)
  const [pairings, setPairings] = useState<Record<number, number>>({})
  const [typed, setTyped] = useState('')
  const [hintLevel, setHintLevel] = useState(0)
  const [hintText, setHintText] = useState('')
  const [revealed, setRevealed] = useState<string[] | null>(null)
  const [feedback, setFeedback] = useState<{
    correct: boolean
    answer: string | string[]
    retry?: boolean
    assisted?: boolean
  } | null>(null)
  const nextButton = useRef<HTMLButtonElement>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const done = practice.finished
  const nextIndex = practice.tasks.findIndex((_, i) => !practice.results.some((r) => r.index === i))
  const task = practice.tasks[index]
  const correctCount = practice.results.filter((r) => r.correct).length
  const mistakes = useMemo(
    () => practice.results.filter((r) => !r.correct).map((r) => r.word_id),
    [practice.results],
  )
  const title = games.find((g) => g.kind === practice.kind)?.title || 'Play'
  const pairCount = Object.keys(pairings).length
  const submit = async (
    indexToSend: number,
    value?: string,
    optionId?: number,
    rating?: string,
  ) => {
    setBusy(true)
    setError('')
    try {
      const response = await api<{
        correct: boolean
        retry: boolean
        answer: string | string[]
        finished: boolean
        assisted: boolean
      }>(
        `/practice/${practice.id}/answer`,
        json('POST', { index: indexToSend, answer: value, option_id: optionId, rating }),
      )
      setFeedback(response)
      if (response.correct) onSuccess()
      if (!response.retry) {
        const updated = await api<Practice>(`/practice/${practice.id}`)
        onUpdate(updated)
        if (updated.finished) onFinish()
      }
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  const next = () => {
    if (nextIndex >= 0) setIndex(nextIndex)
    setFeedback(null)
    setTyped('')
    setHintLevel(0)
    setHintText('')
    setRevealed(null)
    setSelected(null)
  }
  const showHint = async (level: 1 | 2) => {
    setBusy(true)
    setError('')
    try {
      const response = await api<{ hint: string }>(
        `/practice/${practice.id}/hint/${index}`,
        json('POST', { level }),
      )
      setHintText(response.hint)
      setHintLevel(level)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  useEffect(() => {
    if (feedback && !busy && practice.kind !== 'match') nextButton.current?.focus()
  }, [feedback, busy, practice.kind])
  const chooseMatch = (token: number) => {
    if (selected !== null) {
      void submit(selected, undefined, token)
      setSelected(null)
    }
  }
  const chooseChallengeOption = (token: number) => {
    if (selected === null) return
    setPairings((current) => {
      const nextPairings = { ...current }
      const previousToken = nextPairings[selected]
      const previousOwner = Object.keys(nextPairings).find(
        (key) => nextPairings[Number(key)] === token,
      )
      nextPairings[selected] = token
      if (previousOwner !== undefined && Number(previousOwner) !== selected) {
        if (previousToken === undefined) delete nextPairings[Number(previousOwner)]
        else nextPairings[Number(previousOwner)] = previousToken
      }
      return nextPairings
    })
    setSelected(null)
  }
  const checkAllPairs = async () => {
    setBusy(true)
    setError('')
    try {
      const updated = await api<Practice>(
        `/practice/${practice.id}/match-all`,
        json('POST', {
          pairs: practice.tasks.map((_, index) => ({ index, option_id: pairings[index] })),
        }),
      )
      onUpdate(updated)
      if (updated.results.some((result) => result.correct)) onSuccess()
      onFinish()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }
  const speech = task?.speech || ''
  const recording = task?.audio || ''
  const voiceSupported = 'speechSynthesis' in window
  const playWord = () => {
    if (recording) {
      void new Audio(recording).play().catch(() => {})
    } else if (voiceSupported) {
      window.speechSynthesis.cancel()
      const utterance = new SpeechSynthesisUtterance(speech)
      utterance.lang = config.accent
      utterance.rate = 0.85
      window.speechSynthesis.speak(utterance)
    }
  }
  useEffect(() => {
    if (practice.kind === 'listen' && speech && !feedback && !done) playWord()
  }, [index])

  if (done && (practice.kind === 'match' || practice.kind === 'match_all' || !feedback))
    return (
      <div className="mx-auto max-w-2xl text-center pt-6">
        <div className="text-8xl pop" aria-hidden="true">
          🏆
        </div>
        <h1 className="mt-5 text-4xl md:text-5xl font-black">Great job!</h1>
        <p className="mt-2 text-xl font-bold text-[#6b7190]">
          You got {correctCount} of {practice.tasks.length} right!
        </p>
        <div className="card mt-7 p-7">
          <ProgressBar value={(correctCount / practice.tasks.length) * 100} />
          <div className="mt-6 flex items-center justify-center gap-8">
            <div>
              <StarIcon className="mx-auto text-[#e9ad19]" size={30} fill="#ffce60" />
              <strong className="block mt-1">
                +{Math.max(1, Math.floor(correctCount / 3))} stars
              </strong>
            </div>
            <div>
              <Sparkles className="mx-auto text-violet" size={30} />
              <strong className="block mt-1">+{correctCount * 5 + mistakes.length} XP</strong>
            </div>
          </div>
          {practice.kind === 'match_all' && (
            <div className="mt-6 text-left">
              <h2 className="font-black mb-3">Your pairs</h2>
              <div className="grid gap-2">
                {practice.results.map((result) => (
                  <div
                    key={result.index}
                    className={`rounded-2xl p-3 font-bold ${result.correct ? 'bg-[#e1f8ed]' : 'bg-[#fff0e4]'}`}
                  >
                    <span className="font-black">{practice.tasks[result.index]?.prompt}</span>
                    <span className="mx-2">→</span>
                    <span>{result.chosen}</span>
                    {!result.correct && (
                      <span className="block text-sm mt-1">
                        Correct:{' '}
                        {Array.isArray(result.answer) ? result.answer.join(', ') : result.answer}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
          {practice.kind !== 'match_all' && mistakes.length > 0 && (
            <div className="mt-6 rounded-2xl bg-[#fff0ef] p-4 text-left">
              <p className="font-black mb-2">Words to try again</p>
              {practice.results
                .filter((r) => !r.correct)
                .map((r) => (
                  <span
                    key={r.index}
                    className="inline-block mr-2 mb-2 rounded-full bg-white px-3 py-1 font-bold"
                  >
                    {Array.isArray(r.answer) ? r.answer.join(', ') : r.answer}
                  </span>
                ))}
            </div>
          )}
        </div>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <button className="btn-primary text-lg" onClick={() => onAgain()}>
            <RotateCcw /> Play Again
          </button>
          {mistakes.length > 0 && (
            <button className="btn-coral text-lg" onClick={() => onAgain(mistakes)}>
              <Heart /> Practice Mistakes
            </button>
          )}
          <button className="btn-soft text-lg" onClick={onHome}>
            <Home /> Home
          </button>
        </div>
      </div>
    )
  if (!task) return <Empty title="Game is ready" text="Go home and try again" />
  const progressValue =
    ((practice.kind === 'match_all'
      ? pairCount
      : practice.kind === 'match'
        ? practice.results.length
        : index + (feedback && !feedback.retry ? 1 : 0)) /
      practice.tasks.length) *
    100
  return (
    <div className="mx-auto max-w-3xl">
      <div className="flex items-center justify-between gap-3 mb-6">
        <button className="btn-soft" onClick={onHome}>
          <ArrowLeft /> Back
        </button>
        <span className="font-black text-violet">{title}</span>
        <span className="font-black">
          {practice.kind === 'match_all'
            ? `${pairCount}/${practice.tasks.length} paired`
            : `${practice.kind === 'match' ? practice.results.length + 1 : index + 1}/${practice.tasks.length}`}
        </span>
      </div>
      <ProgressBar value={progressValue} />
      {error && (
        <p role="alert" className="mt-5 rounded-2xl bg-[#ffe5e3] p-4 font-bold">
          {error}
        </p>
      )}
      {practice.kind === 'match_all' ? (
        <div className="card mt-8 p-4 sm:p-6 md:p-8">
          <h1 className="text-center section-title">Match all 10 pairs</h1>
          <p className="mt-2 text-center font-bold text-[#6b7190]">
            Tap an English word, then its Russian translation. Change any pair before checking.
          </p>
          <p
            role="status"
            className="sticky top-2 z-10 mt-5 rounded-2xl bg-[#f0eaff] p-3 text-center font-black text-violet shadow-sm"
          >
            {selected === null
              ? `${pairCount} of 10 pairs chosen`
              : `Choose a Russian translation for ${practice.tasks[selected].prompt}`}
          </p>
          <div className="mt-7 grid grid-cols-2 gap-2 sm:gap-4">
            <div className="space-y-2" role="group" aria-label="English words">
              <h2 className="mb-3 text-center font-black text-violet">English</h2>
              {practice.tasks.map((item, i) => {
                const paired = practice.match_options?.find(
                  (option) => option.token === pairings[i],
                )
                return (
                  <button
                    key={i}
                    disabled={busy}
                    onClick={() => setSelected(selected === i ? null : i)}
                    aria-pressed={selected === i}
                    className={`w-full min-h-20 rounded-2xl border-2 p-2 sm:p-3 text-left font-black break-words ${selected === i ? 'border-violet bg-[#e8dfff]' : paired ? 'border-[#cfc2f6] bg-[#f5f1ff]' : 'border-[#e6dbff] bg-white'}`}
                  >
                    <span className="text-xs text-violet">{i + 1}.</span>{' '}
                    <span className="text-base sm:text-lg">{item.prompt}</span>
                    {paired && (
                      <span className="block mt-1 text-sm text-[#686d89]">→ {paired.text}</span>
                    )}
                  </button>
                )
              })}
            </div>
            <div className="space-y-2" role="group" aria-label="Russian translations">
              <h2 className="mb-3 text-center font-black text-violet">Russian</h2>
              {practice.match_options?.map((option) => {
                const owner = Object.keys(pairings).find(
                  (key) => pairings[Number(key)] === option.token,
                )
                return (
                  <button
                    key={option.token}
                    disabled={selected === null || busy}
                    onClick={() => chooseChallengeOption(option.token)}
                    className={`w-full min-h-20 rounded-2xl border-2 p-2 sm:p-3 text-left font-black break-words ${owner === undefined ? 'border-[#ffdfb8] bg-[#fff9ee]' : 'border-[#ffc4ce] bg-[#fff0f2]'} disabled:opacity-100`}
                  >
                    {owner !== undefined && (
                      <span className="mr-2 inline-flex h-6 min-w-6 items-center justify-center rounded-full bg-violet px-1 text-xs text-white">
                        {Number(owner) + 1}
                      </span>
                    )}
                    <span className="text-base sm:text-lg">{option.text}</span>
                  </button>
                )
              })}
            </div>
          </div>
          <div className="mt-5 flex flex-wrap justify-center gap-3">
            <button
              className="btn-soft"
              disabled={busy || pairCount === 0}
              onClick={() => {
                setPairings({})
                setSelected(null)
              }}
            >
              Clear pairs
            </button>
            <button
              className="btn-primary"
              disabled={busy || pairCount !== practice.tasks.length}
              onClick={() => void checkAllPairs()}
            >
              Check all pairs
            </button>
          </div>
        </div>
      ) : practice.kind === 'match' ? (
        <div className="card mt-8 p-5 md:p-8">
          <h1 className="text-center section-title">Find the pairs!</h1>
          <div className="mt-7 grid grid-cols-2 gap-4">
            <div className="space-y-3">
              {practice.tasks.map((item, i) => {
                const matched = practice.results.some((r) => r.index === i)
                return (
                  <button
                    key={i}
                    disabled={matched || busy}
                    onClick={() => {
                      setSelected(i)
                      setFeedback(null)
                    }}
                    aria-pressed={selected === i}
                    className={`w-full min-h-20 rounded-2xl border-2 p-3 text-lg font-black ${matched ? 'bg-[#e1f6eb] border-mint text-[#467765]' : selected === i ? 'bg-[#e8dfff] border-violet' : 'bg-[#f5f1ff] border-[#e6dbff]'}`}
                  >
                    {matched ? <Check className="mx-auto" /> : item.prompt}
                  </button>
                )
              })}
            </div>
            <div className="space-y-3">
              {practice.match_options?.map((option) => {
                const matched = practice.results.some(
                  (r) => practice.tasks[r.index]?.prompt && String(r.answer) === option.text,
                )
                return (
                  <button
                    key={option.token}
                    disabled={matched || busy}
                    onClick={() => chooseMatch(option.token)}
                    className={`w-full min-h-20 rounded-2xl border-2 p-3 text-lg font-black ${matched ? 'bg-[#e1f6eb] border-mint text-[#467765]' : 'bg-[#fff2e7] border-[#ffdfb8]'}`}
                  >
                    {matched ? <Check className="mx-auto" /> : option.text}
                  </button>
                )
              })}
            </div>
          </div>
          <p
            role="status"
            className={`mt-6 min-h-7 text-center text-xl font-black ${feedback?.correct ? 'text-[#32967e]' : 'text-coral'}`}
          >
            {feedback
              ? feedback.correct
                ? 'Nice pair!'
                : 'Try again!'
              : selected === null
                ? 'Tap a word on the left'
                : 'Now tap its pair →'}
          </p>
        </div>
      ) : (
        <div className="card mt-8 p-6 md:p-10 text-center min-h-[440px]">
          <p className="font-black text-violet uppercase tracking-widest">
            {practice.kind === 'flashcard'
              ? 'Flip the card!'
              : practice.kind === 'choice'
                ? 'Pick the right word!'
                : practice.kind === 'listen'
                  ? practice.direction === 'en-ru'
                    ? 'Listen and pick!'
                    : 'Listen and type!'
                  : 'Type the word!'}
          </p>
          {practice.kind === 'listen' ? (
            <div className="mt-8">
              <button
                disabled={!recording && !voiceSupported}
                aria-label="Play word"
                className="mx-auto flex h-28 w-28 items-center justify-center rounded-full bg-[#e9e2ff] text-violet shadow-[0_8px_0_#cfc2f6]"
                onClick={playWord}
              >
                <Volume2 size={54} />
              </button>
              <p className="mt-4 font-bold text-[#7e839e]">Tap to hear again</p>
            </div>
          ) : (
            <>
              <div className="mt-7 text-4xl md:text-5xl font-black">{task.prompt}</div>
              {task.picture && (
                <img
                  className="mx-auto mt-5 h-32 w-40 rounded-2xl object-cover"
                  src={task.picture}
                  alt="Word picture"
                />
              )}
              {practice.kind !== 'type' && task.ipa && (
                <p className="mt-2 text-violet font-bold">{task.ipa}</p>
              )}
              {task.hint && (
                <p className="mx-auto mt-3 max-w-lg rounded-2xl bg-[#fff4d8] p-3 text-lg font-bold">
                  {task.hint}
                </p>
              )}
              {practice.direction === 'en-ru' && task.prompt && (
                <div className="mt-5">
                  <Speak word={task.prompt} accent={config.accent} />
                </div>
              )}
            </>
          )}
          {!feedback && practice.kind === 'flashcard' && (
            <div className="mt-9">
              {!revealed ? (
                <button
                  className="btn-primary text-xl px-10"
                  onClick={async () => {
                    try {
                      const response = await api<{ answers: string[] }>(
                        `/practice/${practice.id}/reveal/${index}`,
                        json('POST'),
                      )
                      setRevealed(response.answers)
                    } catch (e) {
                      setError((e as Error).message)
                    }
                  }}
                >
                  Reveal
                </button>
              ) : (
                <>
                  <div className="rounded-2xl bg-[#f3eeff] p-5 text-3xl font-black">
                    {revealed.join(', ')}
                  </div>
                  <p className="mt-6 font-bold">Did you know it?</p>
                  <div className="mt-3 grid grid-cols-3 gap-2">
                    <button
                      disabled={busy}
                      className="btn-soft"
                      onClick={() => void submit(index, undefined, undefined, 'again')}
                    >
                      Didn't Know
                    </button>
                    <button
                      disabled={busy}
                      className="btn-soft"
                      onClick={() => void submit(index, undefined, undefined, 'hard')}
                    >
                      Hard
                    </button>
                    <button
                      disabled={busy}
                      className="btn-mint"
                      onClick={() => void submit(index, undefined, undefined, 'easy')}
                    >
                      Easy
                    </button>
                  </div>
                </>
              )}
            </div>
          )}
          {!feedback &&
            (practice.kind === 'choice' || (practice.kind === 'listen' && task.options)) && (
              <div className="mt-9 grid grid-cols-1 sm:grid-cols-2 gap-3">
                {task.options?.map((option) => (
                  <button
                    key={option.token}
                    disabled={busy}
                    className="min-h-20 rounded-2xl border-2 border-[#e5ddf5] bg-[#f9f7ff] p-4 text-xl font-black hover:border-violet hover:bg-[#efe9ff]"
                    onClick={() => void submit(index, undefined, option.token)}
                  >
                    {option.text}
                  </button>
                ))}
              </div>
            )}
          {!feedback &&
            (practice.kind === 'type' || (practice.kind === 'listen' && !task.options)) && (
              <>
                {practice.kind === 'type' && (
                  <div className="mt-7">
                    <div className="flex flex-wrap justify-center gap-3">
                      {hintLevel < 1 && (
                        <button
                          className="btn-soft"
                          disabled={busy}
                          onClick={() => void showHint(1)}
                        >
                          First and last letters
                        </button>
                      )}
                      {hintLevel < 2 && (
                        <button
                          className="btn-soft"
                          disabled={busy}
                          onClick={() => void showHint(2)}
                        >
                          Show whole word
                        </button>
                      )}
                    </div>
                    {hintLevel < 2 && (
                      <p className="mt-2 text-sm font-bold text-[#9c593a]">
                        Showing the whole word adds it to mistakes for later practice.
                      </p>
                    )}
                    {hintLevel > 0 && (
                      <p role="status" className="mt-4 text-2xl font-black text-violet">
                        {hintText}
                      </p>
                    )}
                    {hintLevel === 2 && (
                      <p className="mt-2 font-bold text-[#9c593a]">
                        This word is added to mistakes for later practice.
                      </p>
                    )}
                  </div>
                )}
                <form
                  className="mt-9 flex flex-col sm:flex-row gap-3"
                  onSubmit={(e) => {
                    e.preventDefault()
                    if (typed.trim()) void submit(index, typed)
                  }}
                >
                  <input
                    autoFocus
                    className="field text-xl flex-1"
                    value={typed}
                    onChange={(e) => setTyped(e.target.value)}
                    placeholder="Type here"
                    aria-label="Your answer"
                  />
                  <button
                    disabled={busy || !typed.trim()}
                    className="btn-primary text-xl"
                    type="submit"
                  >
                    Check
                  </button>
                </form>
              </>
            )}
          {feedback && (
            <div
              role="status"
              className={`mt-9 rounded-2xl p-5 font-black text-xl ${feedback.correct ? 'bg-[#e1f8ed] text-[#217b60]' : 'bg-[#fff0e4] text-[#9c593a]'}`}
            >
              <div className="flex justify-center items-center gap-2">
                {feedback.correct ? <Check /> : <X />}
                {feedback.correct
                  ? 'Great!'
                  : feedback.assisted
                    ? 'You got it! Practice this word again later.'
                    : 'Try again next time!'}
              </div>
              <p className="mt-2 text-base">
                Answer:{' '}
                {Array.isArray(feedback.answer) ? feedback.answer.join(', ') : feedback.answer}
              </p>
            </div>
          )}
          {feedback && (
            <button
              ref={nextButton}
              className="btn-primary mt-6 text-xl px-10"
              onClick={next}
              disabled={busy}
            >
              {done ? 'See Stars' : 'Next'} <ArrowRight />
            </button>
          )}
        </div>
      )}
    </div>
  )
}
