import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowDown,
  ArrowUp,
  BookOpen,
  Download,
  ImagePlus,
  LayoutDashboard,
  Pencil,
  Plus,
  Search,
  Settings2,
  Trash2,
  Upload,
  Users,
  X,
} from 'lucide-react'
import {
  api,
  download,
  json,
  type Config,
  type DictionaryResult,
  type Pack,
  type PixabayHit,
  type Profile,
  type ProgressRow,
  type Settings,
  type Stats,
  type Word,
  type WordInput,
} from './api'
import { animal, Avatar, Empty, packArt, ProgressBar, Shell } from './ui'

type Tab = 'overview' | 'words' | 'packs' | 'import' | 'progress' | 'settings'
const blankWord: WordInput = {
  english: '',
  translations: [],
  ipa: '',
  part_of_speech: '',
  example_en: '',
  example_ru: '',
  notes: '',
}
const partsOfSpeech = [
  'noun',
  'verb',
  'adjective',
  'adverb',
  'pronoun',
  'proper noun',
  'preposition',
  'conjunction',
  'interjection',
  'determiner',
  'article',
  'numeral',
  'particle',
  'phrase',
] as const
const blankPack = { name: '', description: '', category: '' }
type PictureChoice = { kind: 'upload'; file: File } | { kind: 'pixabay'; hit: PixabayHit }
const normalizeEnglish = (value: string) => value.trim().replace(/\s+/g, ' ').toLowerCase()

export default function Parent({ config, onLogout }: { config: Config; onLogout: () => void }) {
  const [tab, setTab] = useState<Tab>('overview')
  const [words, setWords] = useState<Word[]>([])
  const [packs, setPacks] = useState<Pack[]>([])
  const [profiles, setProfiles] = useState<Profile[]>([])
  const [settings, setSettings] = useState<Settings | null>(null)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [query, setQuery] = useState('')
  const [filterPack, setFilterPack] = useState<number | ''>('')
  const [editingWord, setEditingWord] = useState<Word | null>(null)
  const [wordPack, setWordPack] = useState<Pack | null>(null)
  const [wordForm, setWordForm] = useState<WordInput>(blankWord)
  const [translations, setTranslations] = useState('')
  const [dictionary, setDictionary] = useState<DictionaryResult | null>(null)
  const [dictionaryBusy, setDictionaryBusy] = useState(false)
  const [dictionaryError, setDictionaryError] = useState('')
  const [selectedAudio, setSelectedAudio] = useState('')
  const dictionaryRequest = useRef(0)
  const [showWordForm, setShowWordForm] = useState(false)
  const [savingWord, setSavingWord] = useState(false)
  const [pictureChoice, setPictureChoice] = useState<PictureChoice | null>(null)
  const [showPictureSearch, setShowPictureSearch] = useState(false)
  const [editingPack, setEditingPack] = useState<Pack | null>(null)
  const [packForm, setPackForm] = useState(blankPack)
  const [showPackForm, setShowPackForm] = useState(false)
  const [selectedPack, setSelectedPack] = useState<Pack | null>(null)
  const [chosenWord, setChosenWord] = useState<number | ''>('')
  const [csvFile, setCsvFile] = useState<File | null>(null)
  const [csvPack, setCsvPack] = useState<number | ''>('')
  const [preview, setPreview] = useState<{
    rows: { line: number; data: WordInput; duplicate_id: number | null }[]
    errors: string[]
  } | null>(null)
  const [stats, setStats] = useState<Record<number, Stats>>({})
  const [progressRows, setProgressRows] = useState<Record<number, ProgressRow[]>>({})
  const [pixabayQuery, setPixabayQuery] = useState('')
  const [pixabayHits, setPixabayHits] = useState<PixabayHit[] | null>(null)
  const [pixabayBusy, setPixabayBusy] = useState(false)
  const [pixabayError, setPixabayError] = useState('')
  const pixabaySearchId = useRef(0)

  const refresh = async () => {
    const [nextWords, nextPacks, nextProfiles] = await Promise.all([
      api<Word[]>('/words'),
      api<Pack[]>('/packs'),
      api<Profile[]>('/profiles'),
    ])
    setWords(nextWords)
    setPacks(nextPacks)
    setProfiles(nextProfiles)
    if (selectedPack) setSelectedPack(nextPacks.find((p) => p.id === selectedPack.id) || null)
  }
  const refreshStats = async () => {
    const children = (await api<Profile[]>('/profiles')).filter((p) => p.role === 'child')
    const [next, rows] = await Promise.all([
      Promise.all(children.map((p) => api<Stats>(`/stats?child_id=${p.id}`))),
      Promise.all(children.map((p) => api<ProgressRow[]>(`/progress?child_id=${p.id}`))),
    ])
    setStats(Object.fromEntries(children.map((p, i) => [p.id, next[i]])))
    setProgressRows(Object.fromEntries(children.map((p, i) => [p.id, rows[i]])))
  }
  useEffect(() => {
    void refresh().catch((e) => setError(e.message))
    void api<Settings>('/settings')
      .then(setSettings)
      .catch((e) => setError(e.message))
  }, [])
  useEffect(() => {
    if (tab === 'progress' || tab === 'overview')
      void refreshStats().catch((e) => setError(e.message))
  }, [tab])
  useEffect(() => {
    if (!words.some((word) => word.audio_status === 'pending' || word.audio_status === 'retrying'))
      return
    const timer = window.setInterval(() => {
      void api<Word[]>('/words')
        .then(setWords)
        .catch(() => {})
    }, 10000)
    return () => window.clearInterval(timer)
  }, [words])
  const run = async (action: () => Promise<unknown>, message: string) => {
    setError('')
    setNotice('')
    try {
      await action()
      await refresh()
      setNotice(message)
    } catch (e) {
      setError((e as Error).message)
    }
  }
  const filteredWords = useMemo(
    () =>
      words.filter(
        (w) =>
          (!filterPack || packs.find((p) => p.id === filterPack)?.word_ids.includes(w.id)) &&
          `${w.english} ${w.translations.join(' ')}`.toLowerCase().includes(query.toLowerCase()),
      ),
    [words, query, filterPack, packs],
  )
  const duplicateWord = useMemo(() => {
    const english = normalizeEnglish(wordForm.english)
    return english
      ? words.find(
          (word) => word.id !== editingWord?.id && normalizeEnglish(word.english) === english,
        )
      : undefined
  }, [words, wordForm.english, editingWord])

  const openWord = (word?: Word, pack?: Pack) => {
    dictionaryRequest.current += 1
    pixabaySearchId.current += 1
    setDictionary(null)
    setDictionaryError('')
    setDictionaryBusy(false)
    setSelectedAudio('')
    setPictureChoice(null)
    setShowPictureSearch(false)
    setPixabayQuery(word?.english || '')
    setPixabayHits(null)
    setPixabayError('')
    setPixabayBusy(false)
    setError('')
    setEditingWord(word || null)
    setWordPack(pack || null)
    setWordForm(
      word
        ? {
            english: word.english,
            translations: word.translations,
            ipa: word.ipa || '',
            part_of_speech: word.part_of_speech || '',
            example_en: word.example_en || '',
            example_ru: word.example_ru || '',
            notes: word.notes || '',
          }
        : blankWord,
    )
    setTranslations(word?.translations.join('; ').toLowerCase() || '')
    setShowWordForm(true)
  }
  const closeWord = () => {
    dictionaryRequest.current += 1
    pixabaySearchId.current += 1
    setShowWordForm(false)
    setWordPack(null)
  }
  const changeEnglish = (value: string) => {
    dictionaryRequest.current += 1
    setDictionary(null)
    setDictionaryError('')
    setDictionaryBusy(false)
    setSelectedAudio('')
    setError('')
    if (pixabayQuery === wordForm.english) setPixabayQuery(value)
    setWordForm((current) => ({ ...current, english: value }))
  }
  const lookupDictionary = async () => {
    const word = wordForm.english.trim()
    if (!word) return
    const requestId = ++dictionaryRequest.current
    setDictionary(null)
    setDictionaryError('')
    setDictionaryBusy(true)
    try {
      const result = await api<DictionaryResult>(`/dictionary?word=${encodeURIComponent(word)}`)
      if (dictionaryRequest.current !== requestId) return
      setDictionary(result)
      setWordForm((current) => ({
        ...current,
        english: result.word || current.english,
        ipa: current.ipa || result.ipa,
        part_of_speech: current.part_of_speech || result.part_of_speech,
      }))
    } catch (e) {
      if (dictionaryRequest.current === requestId) setDictionaryError((e as Error).message)
    } finally {
      if (dictionaryRequest.current === requestId) setDictionaryBusy(false)
    }
  }
  const saveWord = async () => {
    if (savingWord || duplicateWord) return
    const body = {
      ...wordForm,
      translations: translations
        .split(';')
        .map((s) => s.trim().toLowerCase())
        .filter(Boolean),
      audio_url: selectedAudio || null,
    }
    const wasEditing = Boolean(editingWord)
    const hasAudio = Boolean(selectedAudio)
    let savedWord: Word | null = null
    let saveStage: 'word' | 'picture' | 'refresh' = 'word'
    setSavingWord(true)
    setError('')
    setNotice('')
    try {
      savedWord = await api<Word>(
        editingWord
          ? `/words/${editingWord.id}`
          : wordPack
            ? `/words?pack_id=${wordPack.id}`
            : '/words',
        json(editingWord ? 'PUT' : 'POST', body),
      )
      setEditingWord(savedWord)
      setSelectedAudio('')
      saveStage = 'picture'
      if (pictureChoice?.kind === 'upload') {
        const form = new FormData()
        form.append('file', pictureChoice.file)
        const result = await api<{ picture: string }>(`/words/${savedWord.id}/picture`, {
          method: 'POST',
          body: form,
        })
        setEditingWord({ ...savedWord, picture: result.picture })
        setPictureChoice(null)
      } else if (pictureChoice?.kind === 'pixabay') {
        const result = await api<{ picture: string }>(
          `/words/${savedWord.id}/pixabay`,
          json('POST', { image_id: pictureChoice.hit.id }),
        )
        setEditingWord({ ...savedWord, picture: result.picture })
        setPictureChoice(null)
      }
      saveStage = 'refresh'
      await refresh()
      closeWord()
      setNotice(
        `${wasEditing ? 'Word saved' : wordPack ? `Word added to ${wordPack.name}` : 'Word added'}${hasAudio ? '; audio download queued' : ''}`,
      )
    } catch (e) {
      const prefix =
        saveStage === 'picture'
          ? 'Word saved, but the picture could not be saved: '
          : saveStage === 'refresh'
            ? 'Word saved, but the library could not refresh: '
            : ''
      setError(`${prefix}${(e as Error).message}`)
      if (savedWord) void refresh().catch(() => {})
    } finally {
      setSavingWord(false)
    }
  }
  const deleteWord = (word: Word) => {
    if (window.confirm(`Delete “${word.english}” from the library and all packs?`))
      void run(() => api(`/words/${word.id}`, json('DELETE')), 'Word deleted')
  }
  const retryAudio = async (word: Word) => {
    await run(() => api(`/words/${word.id}/audio/retry`, json('POST')), 'Audio download queued')
  }
  const openPack = (pack?: Pack) => {
    setError('')
    setEditingPack(pack || null)
    setPackForm(
      pack
        ? { name: pack.name, description: pack.description, category: pack.category || '' }
        : blankPack,
    )
    setShowPackForm(true)
  }
  const savePack = async () => {
    await run(
      async () => {
        await api(
          editingPack ? `/packs/${editingPack.id}` : '/packs',
          json(editingPack ? 'PUT' : 'POST', packForm),
        )
        setShowPackForm(false)
      },
      editingPack ? 'Pack saved' : 'Pack added',
    )
  }
  const setPackWords = async (pack: Pack, ids: number[]) => {
    await run(() => api(`/packs/${pack.id}/words`, json('PUT', { word_ids: ids })), 'Pack updated')
  }
  const uploadPackCover = async (id: number, file: File) => {
    const form = new FormData()
    form.append('file', file)
    await run(() => api(`/packs/${id}/cover`, { method: 'POST', body: form }), 'Picture saved')
  }
  const searchPixabay = async (query: string) => {
    const searchId = ++pixabaySearchId.current
    setPixabayError('')
    setPixabayHits(null)
    if (!query.trim()) {
      setPixabayError('Enter a word to search for pictures.')
      return
    }
    setPixabayBusy(true)
    try {
      const result = await api<{ hits: PixabayHit[] }>(
        `/pixabay/search?q=${encodeURIComponent(query.trim())}`,
      )
      if (pixabaySearchId.current === searchId) setPixabayHits(result.hits)
    } catch (e) {
      if (pixabaySearchId.current === searchId) setPixabayError((e as Error).message)
    } finally {
      if (pixabaySearchId.current === searchId) setPixabayBusy(false)
    }
  }
  const previewFile = async () => {
    if (!csvFile) return
    const form = new FormData()
    form.append('file', csvFile)
    setError('')
    try {
      setPreview(await api('/import/preview', { method: 'POST', body: form }))
    } catch (e) {
      setError((e as Error).message)
    }
  }
  const importFile = async () => {
    if (!csvFile) return
    const form = new FormData()
    form.append('file', csvFile)
    await run(async () => {
      const result = await api<{ imported: number }>(
        `/import${csvPack ? `?pack_id=${csvPack}` : ''}`,
        { method: 'POST', body: form },
      )
      setPreview(null)
      setCsvFile(null)
      setNotice(`${result.imported} new words imported`)
    }, 'Import complete')
  }
  const saveSettings = async () => {
    if (!settings) return
    await run(async () => {
      setSettings(await api('/settings', json('PUT', settings)))
    }, 'Settings saved')
  }
  const saveProfile = async (profile: Profile, changes: Partial<Profile>) => {
    await run(() => api(`/profiles/${profile.id}`, json('PATCH', changes)), 'Profile saved')
  }
  const reset = async (childId: number, wordId?: number, packId?: number) => {
    if (!window.confirm('Reset this learning progress? This cannot be undone.')) return
    await run(async () => {
      await api(
        '/progress/reset',
        json('POST', { child_id: childId, word_id: wordId, pack_id: packId, confirm: true }),
      )
      await refreshStats()
    }, 'Progress reset')
  }

  const tabs: { key: Tab; label: string; icon: typeof BookOpen }[] = [
    { key: 'overview', label: 'Overview', icon: LayoutDashboard },
    { key: 'words', label: 'Vocabulary', icon: BookOpen },
    { key: 'packs', label: 'Word Packs', icon: BookOpen },
    { key: 'import', label: 'Import / Export', icon: Upload },
    { key: 'progress', label: 'Progress', icon: Users },
    { key: 'settings', label: 'Settings', icon: Settings2 },
  ]
  return (
    <Shell
      right={
        <button className="btn-soft" onClick={onLogout}>
          Switch profile
        </button>
      }
    >
      <div className="mb-7">
        <p className="text-violet font-black uppercase tracking-widest text-sm">Parent area</p>
        <h1 className="section-title">Welcome, Parent</h1>
        <p className="font-bold text-[#747995]">
          Manage words and see how your explorers are doing.
        </p>
      </div>
      <nav aria-label="Parent sections" className="flex gap-2 overflow-x-auto pb-4 mb-6">
        {tabs.map((item) => (
          <button
            key={item.key}
            onClick={() => {
              setTab(item.key)
              setError('')
              setNotice('')
            }}
            className={`btn whitespace-nowrap ${tab === item.key ? 'bg-violet text-white' : 'bg-white text-ink'}`}
          >
            <item.icon size={19} />
            {item.label}
          </button>
        ))}
      </nav>
      {error && !showWordForm && (
        <p role="alert" className="rounded-2xl bg-[#ffe5e3] p-4 mb-5 font-bold text-[#9a4141]">
          {error}
        </p>
      )}
      {notice && (
        <p role="status" className="rounded-2xl bg-[#e1f8ed] p-4 mb-5 font-bold text-[#217b60]">
          {notice}
        </p>
      )}
      {tab === 'overview' && (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <StatCard label="Words" value={words.length} emoji="📚" />
            <StatCard label="Packs" value={packs.length} emoji="🎒" />
            <StatCard
              label="Explorers"
              value={profiles.filter((p) => p.role === 'child').length}
              emoji="🦊"
            />
          </div>
          <h2 className="section-title mt-10 mb-5">Your explorers</h2>
          <div className="grid gap-5 md:grid-cols-2">
            {profiles
              .filter((p) => p.role === 'child')
              .map((child) => (
                <div key={child.id} className="card p-6 flex items-center gap-5">
                  <div className="rounded-3xl bg-[#f1eaff] p-4">
                    <Avatar name={child.avatar} />
                  </div>
                  <div className="flex-1">
                    <h3 className="text-xl font-black">{child.name}</h3>
                    <p className="font-bold text-[#747995]">
                      {stats[child.id]?.learned ?? 0} learned · {stats[child.id]?.due ?? 0} ready to
                      review
                    </p>
                    <ProgressBar
                      value={Math.min(
                        100,
                        ((stats[child.id]?.learned ?? 0) / Math.max(1, words.length)) * 100,
                      )}
                    />
                  </div>
                </div>
              ))}
          </div>
          <div className="mt-10 card p-7">
            <h2 className="text-xl font-black">Start adding words</h2>
            <p className="mt-1 text-[#747995] font-bold">
              Make a pack, add words, then let the kids play.
            </p>
            <div className="mt-4 flex flex-wrap gap-3">
              <button
                className="btn-primary"
                onClick={() => {
                  setTab('words')
                  openWord()
                }}
              >
                <Plus /> Add word
              </button>
              <button
                className="btn-soft"
                onClick={() => {
                  setTab('packs')
                  openPack()
                }}
              >
                <Plus /> Add pack
              </button>
            </div>
          </div>
        </>
      )}
      {tab === 'words' && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
            <div>
              <h2 className="section-title">Vocabulary Library</h2>
              <p className="font-bold text-[#747995]">{filteredWords.length} words</p>
            </div>
            <button className="btn-primary" onClick={() => openWord()}>
              <Plus /> Add Word
            </button>
          </div>
          <div className="card p-4 mb-5 flex flex-wrap gap-3">
            <label className="relative flex-1 min-w-48">
              <Search className="absolute left-4 top-3.5 text-[#888ca7]" size={20} />
              <input
                className="field pl-11"
                placeholder="Search English or Russian"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </label>
            <select
              className="field max-w-xs"
              value={filterPack}
              onChange={(e) => setFilterPack(e.target.value ? Number(e.target.value) : '')}
            >
              <option value="">All packs</option>
              {packs.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
          <div className="vocabulary-grid">
            {filteredWords.map((word) => (
              <article key={word.id} className="card vocabulary-card min-w-0 rounded-3xl p-3">
                <div className="min-w-0 flex flex-col">
                  <div className="flex items-start gap-3">
                    <div className="h-12 w-12 shrink-0 rounded-xl bg-[#eee8ff] flex items-center justify-center overflow-hidden text-2xl">
                      {word.picture ? (
                        <img className="h-full w-full object-cover" src={word.picture} alt="" />
                      ) : (
                        '✦'
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <h3 className="font-black leading-tight break-words">{word.english}</h3>
                      {word.ipa && (
                        <p className="text-xs font-bold text-violet break-words">{word.ipa}</p>
                      )}
                    </div>
                  </div>
                  <p className="mt-2 text-sm leading-snug text-[#747995] font-bold break-words">
                    {word.translations.join(' · ')}
                  </p>
                  {word.audio_status === 'pending' && (
                    <p className="mt-2 text-xs font-bold text-violet">Audio queued for download</p>
                  )}
                  {word.audio_status === 'retrying' && (
                    <p className="mt-2 text-xs font-bold text-violet">Audio retry scheduled</p>
                  )}
                  {word.audio_status === 'ready' && (
                    <p className="mt-2 text-xs font-bold text-violet">Audio available offline</p>
                  )}
                  {word.audio_status === 'failed' && (
                    <p className="mt-2 text-xs font-bold text-coral break-words">
                      Audio download failed{word.audio_error ? `: ${word.audio_error}` : ''}
                    </p>
                  )}
                  {word.audio_status === 'failed' && (
                    <button
                      className="btn-soft !min-h-10 !px-3 !py-1 text-sm mt-auto self-start"
                      onClick={() => void retryAudio(word)}
                    >
                      Retry audio
                    </button>
                  )}
                </div>
                <div className="flex flex-col justify-between gap-2">
                  <button
                    className="btn-soft !min-h-10 !w-10 !p-0"
                    aria-label={`Edit ${word.english}`}
                    title={`Edit ${word.english}`}
                    onClick={() => openWord(word)}
                  >
                    <Pencil size={17} />
                  </button>
                  <button
                    className="btn-soft !min-h-10 !w-10 !p-0 text-coral"
                    aria-label={`Delete ${word.english}`}
                    title={`Delete ${word.english}`}
                    onClick={() => deleteWord(word)}
                  >
                    <Trash2 size={17} />
                  </button>
                </div>
              </article>
            ))}
          </div>
          {filteredWords.length === 0 && (
            <Empty title="No words found" text="Add a word or try another search." />
          )}
        </>
      )}
      {tab === 'packs' && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
            <h2 className="section-title">Word Packs</h2>
            <button className="btn-primary" onClick={() => openPack()}>
              <Plus /> Add Pack
            </button>
          </div>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {packs.map((pack) => {
              const art = packArt[pack.name] || { emoji: '🎒', bg: 'bg-[#e8e1ff]' }
              return (
                <article key={pack.id} className="card p-5">
                  <div
                    className={`${art.bg} h-32 rounded-2xl flex items-center justify-center text-6xl overflow-hidden`}
                  >
                    {pack.cover ? (
                      <img className="h-full w-full object-cover" src={pack.cover} alt="" />
                    ) : (
                      art.emoji
                    )}
                  </div>
                  <h3 className="font-black text-xl mt-4">{pack.name}</h3>
                  <p className="font-bold text-[#747995]">{pack.description}</p>
                  <p className="mt-2 text-sm font-black text-violet">{pack.word_count} words</p>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <button className="btn-primary" onClick={() => setSelectedPack(pack)}>
                      Manage Words
                    </button>
                    <button className="btn-soft" onClick={() => openPack(pack)}>
                      Edit
                    </button>
                    <label className="btn-soft" aria-label={`Upload cover for ${pack.name}`}>
                      <ImagePlus size={19} />
                      <input
                        type="file"
                        className="sr-only"
                        accept="image/jpeg,image/png,image/webp"
                        onChange={(e) => {
                          if (e.target.files?.[0]) void uploadPackCover(pack.id, e.target.files[0])
                        }}
                      />
                    </label>
                    <button
                      className="btn-soft text-coral"
                      aria-label={`Delete ${pack.name}`}
                      onClick={() => {
                        if (
                          window.confirm(
                            `Delete pack “${pack.name}”? Its words will stay in the library.`,
                          )
                        )
                          void run(() => api(`/packs/${pack.id}`, json('DELETE')), 'Pack deleted')
                      }}
                    >
                      <Trash2 size={19} />
                    </button>
                  </div>
                </article>
              )
            })}
          </div>
          {selectedPack && (
            <div className="card mt-7 p-6">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h3 className="text-xl font-black">{selectedPack.name} words</h3>
                <div className="flex items-center gap-2">
                  <button className="btn-primary" onClick={() => openWord(undefined, selectedPack)}>
                    <Plus size={18} /> New Word
                  </button>
                  <button
                    className="btn-soft"
                    aria-label="Close pack words"
                    onClick={() => setSelectedPack(null)}
                  >
                    <X size={18} />
                  </button>
                </div>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <select
                  className="field flex-1 min-w-52"
                  value={chosenWord}
                  onChange={(e) => setChosenWord(e.target.value ? Number(e.target.value) : '')}
                >
                  <option value="">Choose a word to add</option>
                  {words
                    .filter((w) => !selectedPack.word_ids.includes(w.id))
                    .map((w) => (
                      <option key={w.id} value={w.id}>
                        {w.english} — {w.translations.join(', ')}
                      </option>
                    ))}
                </select>
                <button
                  className="btn-primary"
                  disabled={!chosenWord}
                  onClick={() => {
                    if (chosenWord) {
                      void setPackWords(selectedPack, [...selectedPack.word_ids, chosenWord])
                      setChosenWord('')
                    }
                  }}
                >
                  <Plus /> Add
                </button>
              </div>
              <div className="mt-5 space-y-2">
                {selectedPack.word_ids.map((id, index) => {
                  const word = words.find((w) => w.id === id)
                  if (!word) return null
                  return (
                    <div
                      className="rounded-2xl bg-[#f8f6ff] p-3 flex flex-wrap items-center gap-3"
                      key={id}
                    >
                      <span className="w-6 shrink-0 font-black text-violet">{index + 1}</span>
                      <div className="h-12 w-12 shrink-0 rounded-xl bg-[#eee8ff] flex items-center justify-center overflow-hidden text-2xl">
                        {word.picture ? (
                          <img className="h-full w-full object-cover" src={word.picture} alt="" />
                        ) : (
                          '✦'
                        )}
                      </div>
                      <div className="min-w-32 flex-1">
                        <p className="font-black leading-tight break-words">
                          {word.english}
                          {word.ipa && (
                            <span className="ml-2 text-sm font-bold text-violet">{word.ipa}</span>
                          )}
                        </p>
                        <p className="text-sm font-bold text-[#7a80a0] break-words">
                          {word.translations.join(', ')}
                        </p>
                      </div>
                      <div className="ml-auto flex shrink-0 gap-1 sm:gap-2">
                        <button
                          className="btn-soft !min-h-10 !w-10 !p-0"
                          aria-label={`Edit ${word.english}`}
                          onClick={() => openWord(word, selectedPack)}
                        >
                          <Pencil size={18} />
                        </button>
                        <button
                          disabled={index === 0}
                          className="btn-soft !min-h-10 !w-10 !p-0"
                          aria-label={`Move ${word.english} up`}
                          onClick={() => {
                            const ids = [...selectedPack.word_ids]
                            ;[ids[index - 1], ids[index]] = [ids[index], ids[index - 1]]
                            void setPackWords(selectedPack, ids)
                          }}
                        >
                          <ArrowUp size={18} />
                        </button>
                        <button
                          disabled={index === selectedPack.word_ids.length - 1}
                          className="btn-soft !min-h-10 !w-10 !p-0"
                          aria-label={`Move ${word.english} down`}
                          onClick={() => {
                            const ids = [...selectedPack.word_ids]
                            ;[ids[index + 1], ids[index]] = [ids[index], ids[index + 1]]
                            void setPackWords(selectedPack, ids)
                          }}
                        >
                          <ArrowDown size={18} />
                        </button>
                        <button
                          className="btn-soft !min-h-10 !w-10 !p-0 text-coral"
                          aria-label={`Remove ${word.english}`}
                          onClick={() =>
                            void setPackWords(
                              selectedPack,
                              selectedPack.word_ids.filter((x) => x !== id),
                            )
                          }
                        >
                          <X size={18} />
                        </button>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </>
      )}
      {tab === 'import' && (
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="card p-6">
            <h2 className="text-2xl font-black">Import CSV</h2>
            <p className="mt-2 font-bold text-[#747995]">
              Use UTF-8. Separate translations with a semicolon.
            </p>
            <button
              className="btn-soft mt-4"
              onClick={() => void download('/import/template', 'vacabyrock-template.csv')}
            >
              <Download /> Get template
            </button>
            <label className="label mt-7">CSV file</label>
            <input
              type="file"
              accept=".csv,text/csv"
              className="field"
              onChange={(e) => {
                setCsvFile(e.target.files?.[0] || null)
                setPreview(null)
              }}
            />
            <label className="label mt-4">Add imported words to a pack</label>
            <select
              className="field"
              value={csvPack}
              onChange={(e) => setCsvPack(e.target.value ? Number(e.target.value) : '')}
            >
              <option value="">Library only</option>
              {packs.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
            <button
              disabled={!csvFile}
              className="btn-primary mt-5"
              onClick={() => void previewFile()}
            >
              Preview Import
            </button>
            {preview && (
              <div className="mt-6">
                <h3 className="font-black text-lg">Preview: {preview.rows.length} rows</h3>
                {preview.errors.map((error, i) => (
                  <p className="text-coral font-bold" key={i}>
                    {error}
                  </p>
                ))}
                <div className="max-h-56 overflow-auto mt-2">
                  {preview.rows.map((row) => (
                    <p className="border-b py-2" key={row.line}>
                      {row.data.english} — {row.data.translations.join(', ')}{' '}
                      {row.duplicate_id && (
                        <span className="text-[#ad7b20] font-black">Already in library</span>
                      )}
                    </p>
                  ))}
                </div>
                <button
                  disabled={preview.errors.length > 0 || preview.rows.length === 0}
                  className="btn-mint mt-5"
                  onClick={() => void importFile()}
                >
                  Import Words
                </button>
              </div>
            )}
          </div>
          <div className="card p-6">
            <h2 className="text-2xl font-black">Export CSV</h2>
            <p className="mt-2 font-bold text-[#747995]">Save a copy of your vocabulary.</p>
            <button
              className="btn-primary mt-5"
              onClick={() => void download('/export', 'vacabyrock-library.csv')}
            >
              <Download /> Full Library
            </button>
            <h3 className="mt-8 font-black">One pack</h3>
            <div className="mt-3 flex flex-wrap gap-2">
              {packs.map((pack) => (
                <button
                  className="btn-soft"
                  key={pack.id}
                  onClick={() =>
                    void download(
                      `/export?pack_id=${pack.id}`,
                      `vacabyrock-${pack.name.toLowerCase().replaceAll(' ', '-')}.csv`,
                    )
                  }
                >
                  <Download size={18} />
                  {pack.name}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
      {tab === 'progress' && (
        <div className="space-y-6">
          {profiles
            .filter((p) => p.role === 'child')
            .map((child) => {
              const data = stats[child.id]
              return (
                <section className="card p-6" key={child.id}>
                  <div className="flex items-center gap-4 mb-6">
                    <Avatar name={child.avatar} />
                    <h2 className="text-2xl font-black">{child.name}</h2>
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                    {[
                      ['Learned', data?.learned],
                      ['Studying', data?.studying],
                      ['Hard words', data?.difficult],
                      ['Ready now', data?.due],
                      ['Success', `${data?.success_rate ?? 0}%`],
                    ].map(([label, value]) => (
                      <div key={label} className="rounded-2xl bg-[#f3efff] p-4">
                        <strong className="block text-2xl">{value ?? 0}</strong>
                        <span className="text-sm font-bold text-[#6d7392]">{label}</span>
                      </div>
                    ))}
                  </div>
                  <div className="mt-5 grid gap-3 md:grid-cols-3">
                    <WordStatusList
                      title="Learned words"
                      rows={(progressRows[child.id] || []).filter(
                        (r) => r.status === 'review' || r.status === 'mastered',
                      )}
                      words={words}
                    />
                    <WordStatusList
                      title="Studying words"
                      rows={(progressRows[child.id] || []).filter((r) => r.status === 'learning')}
                      words={words}
                    />
                    <WordStatusList
                      title="Hard words"
                      rows={(progressRows[child.id] || []).filter((r) => r.incorrect > r.correct)}
                      words={words}
                    />
                  </div>
                  <h3 className="font-black mt-7">Achievements</h3>
                  <p className="font-bold text-[#747995]">
                    {data?.achievements.length
                      ? data.achievements.join(' · ')
                      : 'No achievements yet'}
                  </p>
                  <h3 className="font-black mt-6">Recent games</h3>
                  <div className="mt-2 space-y-1">
                    {data?.recent_sessions.length ? (
                      data.recent_sessions.map((s) => (
                        <p key={s.id} className="flex justify-between border-b py-2 font-bold">
                          <span>
                            {new Date(s.date).toLocaleDateString()} · {s.kind}
                          </span>
                          <span>
                            {s.correct}/{s.total}
                          </span>
                        </p>
                      ))
                    ) : (
                      <p className="text-[#747995]">No games yet</p>
                    )}
                  </div>
                  <h3 className="font-black mt-6">Upcoming reviews</h3>
                  <p className="font-bold text-[#747995]">
                    {data?.upcoming_reviews.length
                      ? data.upcoming_reviews
                          .slice(0, 5)
                          .map(
                            (r) =>
                              `${words.find((w) => w.id === r.word_id)?.english || 'Word'} (${new Date(r.next_review_at).toLocaleDateString()})`,
                          )
                          .join(' · ')
                      : 'None yet'}
                  </p>
                  <div className="mt-6 flex flex-wrap gap-2">
                    <button className="btn-soft text-coral" onClick={() => void reset(child.id)}>
                      Reset all progress
                    </button>
                    <select
                      className="field max-w-xs"
                      defaultValue=""
                      onChange={(e) => {
                        if (e.target.value) {
                          void reset(child.id, undefined, Number(e.target.value))
                          e.target.value = ''
                        }
                      }}
                    >
                      <option value="">Reset a pack…</option>
                      {packs.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name}
                        </option>
                      ))}
                    </select>
                    <select
                      className="field max-w-xs"
                      defaultValue=""
                      onChange={(e) => {
                        if (e.target.value) {
                          void reset(child.id, Number(e.target.value))
                          e.target.value = ''
                        }
                      }}
                    >
                      <option value="">Reset a word…</option>
                      {words.map((w) => (
                        <option key={w.id} value={w.id}>
                          {w.english} — {w.translations[0]}
                        </option>
                      ))}
                    </select>
                  </div>
                </section>
              )
            })}
        </div>
      )}
      {tab === 'settings' && settings && (
        <div className="grid gap-6 lg:grid-cols-2">
          <section className="card p-6">
            <h2 className="text-2xl font-black">Learning Settings</h2>
            <label className="label mt-5">Questions per game</label>
            <input
              className="field"
              type="number"
              min="1"
              max="30"
              value={settings.session_length}
              onChange={(e) => setSettings({ ...settings, session_length: Number(e.target.value) })}
            />
            <label className="label mt-4">English accent</label>
            <select
              className="field"
              value={settings.accent}
              onChange={(e) => setSettings({ ...settings, accent: e.target.value })}
            >
              <option value="en-US">American English</option>
              <option value="en-GB">British English</option>
            </select>
            <label className="label mt-4">Default word direction</label>
            <select
              className="field"
              value={settings.direction}
              onChange={(e) => setSettings({ ...settings, direction: e.target.value })}
            >
              <option value="en-ru">English → Russian</option>
              <option value="ru-en">Russian → English</option>
            </select>
            <label className="mt-5 flex items-center gap-3 font-bold">
              <input
                type="checkbox"
                checked={settings.fold_yo}
                onChange={(e) => setSettings({ ...settings, fold_yo: e.target.checked })}
              />
              Treat е and ё as the same
            </label>
            <label className="mt-3 flex items-center gap-3 font-bold">
              <input
                type="checkbox"
                checked={settings.lenient_typos}
                onChange={(e) => setSettings({ ...settings, lenient_typos: e.target.checked })}
              />
              Allow one letter typo
            </label>
            <label className="mt-3 flex items-center gap-3 font-bold">
              <input
                type="checkbox"
                checked={settings.child_avatar_change}
                onChange={(e) =>
                  setSettings({ ...settings, child_avatar_change: e.target.checked })
                }
              />
              Children can change avatars
            </label>
            <h3 className="font-black mt-7">Available games</h3>
            <div className="mt-2 grid grid-cols-2 gap-2">
              {config.allowed_exercises
                .concat(['match', 'flashcard', 'choice', 'type', 'listen'] as const)
                .filter((x, i, arr) => arr.indexOf(x) === i)
                .map((kind) => (
                  <label
                    key={kind}
                    className="flex items-center gap-2 rounded-xl bg-[#f6f2ff] p-3 font-bold"
                  >
                    <input
                      type="checkbox"
                      checked={settings.allowed_exercises.includes(kind)}
                      onChange={(e) =>
                        setSettings({
                          ...settings,
                          allowed_exercises: e.target.checked
                            ? [...settings.allowed_exercises, kind]
                            : settings.allowed_exercises.filter((x) => x !== kind),
                        })
                      }
                    />
                    {kind}
                  </label>
                ))}
            </div>
            <button className="btn-primary mt-7" onClick={() => void saveSettings()}>
              Save Settings
            </button>
          </section>
          <section className="card p-6">
            <h2 className="text-2xl font-black">Children</h2>
            <div className="space-y-6 mt-5">
              {profiles
                .filter((p) => p.role === 'child')
                .map((child) => (
                  <ProfileEditor
                    key={child.id}
                    profile={child}
                    avatars={config.avatars}
                    onSave={(changes) => void saveProfile(child, changes)}
                  />
                ))}
            </div>
          </section>
        </div>
      )}
      {showWordForm && (
        <Dialog
          title={editingWord ? 'Edit Word' : wordPack ? `Add Word to ${wordPack.name}` : 'Add Word'}
          onClose={closeWord}
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="English" value={wordForm.english} onChange={changeEnglish} />
            <div className="flex items-end">
              <button
                type="button"
                className="btn-soft"
                disabled={!wordForm.english.trim() || dictionaryBusy}
                onClick={() => void lookupDictionary()}
              >
                {dictionaryBusy ? 'Looking up…' : 'Fill from Wikimedia'}
              </button>
            </div>
            {duplicateWord && (
              <p role="alert" className="sm:col-span-2 font-bold text-coral">
                “{duplicateWord.english}” is already in the vocabulary library.
                {wordPack && !wordPack.word_ids.includes(duplicateWord.id)
                  ? ' Choose it from the existing-word list in this pack.'
                  : ''}
              </p>
            )}
            <Field
              label="Russian translations (separate with ;)"
              value={translations}
              onChange={(value) => setTranslations(value.toLowerCase())}
            />
            <div className="sm:col-span-2">
              {dictionaryBusy && <p role="status">Looking up dictionary entry…</p>}
              {dictionaryError && <p role="status">{dictionaryError}</p>}
              {dictionary && (
                <>
                  {dictionary.us_spelling && (
                    <button
                      type="button"
                      className="btn-soft mb-3"
                      onClick={() => changeEnglish(dictionary.us_spelling)}
                    >
                      Use US spelling: {dictionary.us_spelling}
                    </button>
                  )}
                  <p className="label">Russian translation suggestions</p>
                  {dictionary.translations.length ? (
                    <div className="flex flex-wrap gap-2">
                      {dictionary.translations.map((item, index) => {
                        const suggestion = item.word.toLowerCase()
                        const selected = translations
                          .split(';')
                          .map((s) => s.trim())
                          .includes(suggestion)
                        return (
                          <button
                            key={`${item.word}-${item.sense}-${index}`}
                            type="button"
                            aria-pressed={selected}
                            title={item.sense || undefined}
                            className="btn-soft"
                            onClick={() =>
                              setTranslations((current) => {
                                const values = current
                                  .split(';')
                                  .map((s) => s.trim())
                                  .filter(Boolean)
                                return (
                                  selected
                                    ? values.filter((value) => value !== suggestion)
                                    : [...values, suggestion]
                                ).join('; ')
                              })
                            }
                          >
                            {item.word}
                            {item.sense ? ` · ${item.sense}` : ''}
                          </button>
                        )
                      })}
                    </div>
                  ) : (
                    <p>No Russian translations found. Enter one manually.</p>
                  )}
                  <p className="label mt-4">Pronunciation recordings</p>
                  {dictionary.audio.length ? (
                    <>
                      <label className="flex items-center gap-3 py-1">
                        <input
                          type="radio"
                          name="dictionary-audio"
                          checked={!selectedAudio}
                          onChange={() => setSelectedAudio('')}
                        />
                        <span>No recording</span>
                      </label>
                      {dictionary.audio.map((item) => (
                        <label key={item.url} className="flex items-center gap-3 py-1">
                          <input
                            type="radio"
                            name="dictionary-audio"
                            checked={selectedAudio === item.url}
                            onChange={() => setSelectedAudio(item.url)}
                          />
                          <span>{item.tags.join(', ') || 'Accent unspecified'}</span>
                          <audio
                            controls
                            preload="none"
                            src={item.url}
                            aria-label={`Preview ${item.label}`}
                          />
                        </label>
                      ))}
                    </>
                  ) : (
                    <p>No recording found.</p>
                  )}
                </>
              )}
            </div>
            <Field
              label="IPA"
              value={wordForm.ipa || ''}
              onChange={(value) => setWordForm({ ...wordForm, ipa: value })}
            />
            <label>
              <span className="label">Part of speech</span>
              <select
                className="field"
                value={wordForm.part_of_speech || ''}
                onChange={(event) =>
                  setWordForm({ ...wordForm, part_of_speech: event.target.value })
                }
              >
                <option value="">Select part of speech</option>
                {wordForm.part_of_speech &&
                  !partsOfSpeech.some((part) => part === wordForm.part_of_speech) && (
                    <option value={wordForm.part_of_speech}>{wordForm.part_of_speech}</option>
                  )}
                {partsOfSpeech.map((part) => (
                  <option key={part} value={part}>
                    {part}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <section className="mt-6 rounded-2xl border-2 border-[#e5ddf5] p-4">
            <h3 className="font-black text-lg">Picture</h3>
            <div className="mt-3 flex flex-wrap items-center gap-4">
              {pictureChoice?.kind === 'pixabay' || (!pictureChoice && editingWord?.picture) ? (
                <img
                  className="h-24 w-24 rounded-2xl object-cover"
                  src={
                    pictureChoice?.kind === 'pixabay'
                      ? pictureChoice.hit.preview_url
                      : editingWord?.picture || ''
                  }
                  alt="Word picture"
                />
              ) : (
                <div
                  className="h-24 w-24 rounded-2xl bg-[#eee8ff] flex items-center justify-center text-3xl"
                  aria-hidden="true"
                >
                  ✦
                </div>
              )}
              <div className="flex flex-wrap gap-2">
                <label className="btn-soft">
                  <ImagePlus size={19} /> Upload picture
                  <input
                    type="file"
                    className="sr-only"
                    aria-label="Upload picture"
                    accept="image/jpeg,image/png,image/webp"
                    onChange={(event) => {
                      if (event.target.files?.[0])
                        setPictureChoice({ kind: 'upload', file: event.target.files[0] })
                    }}
                  />
                </label>
                <button
                  type="button"
                  className="btn-soft"
                  disabled={!pixabayQuery.trim() && !wordForm.english.trim()}
                  onClick={() => {
                    const searchTerm = pixabayQuery.trim() || wordForm.english.trim()
                    setPixabayQuery(searchTerm)
                    setShowPictureSearch(true)
                    void searchPixabay(searchTerm)
                  }}
                >
                  <Search size={19} /> Search Pixabay
                </button>
                {pictureChoice && (
                  <button type="button" className="btn-soft" onClick={() => setPictureChoice(null)}>
                    {editingWord?.picture ? 'Keep current picture' : 'Clear picture'}
                  </button>
                )}
              </div>
            </div>
            {pictureChoice?.kind === 'upload' && (
              <p className="mt-2 font-bold">Selected: {pictureChoice.file.name}</p>
            )}
            {pictureChoice?.kind === 'pixabay' && (
              <p className="mt-2 font-bold">Selected Pixabay picture: {pictureChoice.hit.tags}</p>
            )}
            {showPictureSearch && (
              <div className="mt-5">
                <form
                  className="flex flex-col sm:flex-row gap-3"
                  onSubmit={(event) => {
                    event.preventDefault()
                    void searchPixabay(pixabayQuery)
                  }}
                >
                  <input
                    className="field flex-1"
                    aria-label="Pixabay search"
                    value={pixabayQuery}
                    onChange={(event) => setPixabayQuery(event.target.value)}
                    maxLength={100}
                  />
                  <button className="btn-primary" type="submit" disabled={pixabayBusy}>
                    <Search size={19} /> Search
                  </button>
                </form>
                <p className="mt-3 text-sm font-bold text-[#747995]">
                  Search results from{' '}
                  <a
                    href="https://pixabay.com/"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-violet underline"
                  >
                    Pixabay
                  </a>
                  . Choose a picture to add when you save this word.
                </p>
                {pixabayError && (
                  <p
                    role="alert"
                    className="mt-4 rounded-2xl bg-[#ffe5e3] p-4 font-bold text-coral"
                  >
                    {pixabayError}
                  </p>
                )}
                {pixabayBusy && <p className="mt-5 font-bold">Loading pictures…</p>}
                {pixabayHits && pixabayHits.length === 0 && (
                  <p className="mt-5 font-bold">No pictures found. Try another search.</p>
                )}
                {pixabayHits && pixabayHits.length > 0 && (
                  <div className="mt-5 grid max-h-72 grid-cols-2 gap-4 overflow-y-auto sm:grid-cols-3">
                    {pixabayHits.map((hit) => (
                      <article key={hit.id} className="rounded-2xl border-2 border-[#e5ddf5] p-2">
                        <img
                          className="h-28 w-full rounded-xl object-cover"
                          src={hit.preview_url}
                          alt={hit.tags || 'Pixabay picture'}
                          loading="lazy"
                        />
                        <button
                          type="button"
                          className="btn-mint mt-2 w-full text-sm"
                          onClick={() => {
                            setPictureChoice({ kind: 'pixabay', hit })
                            setShowPictureSearch(false)
                          }}
                        >
                          Choose picture
                        </button>
                        <a
                          className="mt-2 block truncate text-xs font-bold text-violet underline"
                          href={hit.page_url}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          Image by {hit.user || 'Pixabay contributor'}
                        </a>
                      </article>
                    ))}
                  </div>
                )}
              </div>
            )}
          </section>
          {error && (
            <p role="alert" className="mt-4 font-bold text-coral">
              {error}
            </p>
          )}
          <button
            disabled={
              !wordForm.english.trim() || !translations.trim() || savingWord || !!duplicateWord
            }
            className="btn-primary mt-6"
            onClick={() => void saveWord()}
          >
            {savingWord ? 'Saving…' : 'Save Word'}
          </button>
        </Dialog>
      )}
      {showPackForm && (
        <Dialog
          title={editingPack ? 'Edit Pack' : 'Add Pack'}
          onClose={() => setShowPackForm(false)}
        >
          <Field
            label="Pack name"
            value={packForm.name}
            onChange={(value) => setPackForm({ ...packForm, name: value })}
          />
          <div className="mt-4">
            <Field
              label="Description"
              value={packForm.description}
              onChange={(value) => setPackForm({ ...packForm, description: value })}
            />
          </div>
          <div className="mt-4">
            <Field
              label="Category (optional)"
              value={packForm.category}
              onChange={(value) => setPackForm({ ...packForm, category: value })}
            />
          </div>
          {error && (
            <p role="alert" className="mt-4 font-bold text-coral">
              {error}
            </p>
          )}
          <button
            disabled={!packForm.name.trim()}
            className="btn-primary mt-6"
            onClick={() => void savePack()}
          >
            Save Pack
          </button>
        </Dialog>
      )}
    </Shell>
  )
}

function Field({
  label,
  value,
  onChange,
}: {
  label: string
  value: string
  onChange: (value: string) => void
}) {
  return (
    <label>
      <span className="label">{label}</span>
      <input className="field" value={value} onChange={(e) => onChange(e.target.value)} />
    </label>
  )
}
function StatCard({ label, value, emoji }: { label: string; value: number; emoji: string }) {
  return (
    <div className="card p-6 flex items-center gap-5">
      <span className="text-5xl" aria-hidden="true">
        {emoji}
      </span>
      <div>
        <strong className="block text-3xl font-black">{value}</strong>
        <span className="font-bold text-[#747995]">{label}</span>
      </div>
    </div>
  )
}
function Dialog({
  title,
  children,
  onClose,
}: {
  title: string
  children: React.ReactNode
  onClose: () => void
}) {
  return (
    <div
      className="fixed inset-0 z-50 bg-[#29234b]/50 p-4 flex items-center justify-center"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="card w-full max-w-2xl max-h-[90vh] overflow-auto p-6 md:p-8"
      >
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-2xl font-black">{title}</h2>
          <button className="btn-soft" aria-label="Close" onClick={onClose}>
            <X />
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}
function ProfileEditor({
  profile,
  avatars,
  onSave,
}: {
  profile: Profile
  avatars: string[]
  onSave: (changes: Partial<Profile>) => void
}) {
  const [name, setName] = useState(profile.name)
  const [avatar, setAvatar] = useState(profile.avatar)
  useEffect(() => {
    setName(profile.name)
    setAvatar(profile.avatar)
  }, [profile])
  return (
    <div className="rounded-2xl bg-[#f7f3ff] p-4">
      <div className="flex items-center gap-3">
        <Avatar name={avatar} />
        <input
          className="field"
          aria-label={`Name for ${profile.name}`}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {avatars.map((item) => (
          <button
            aria-label={`${item} for ${profile.name}`}
            aria-pressed={avatar === item}
            key={item}
            className={`rounded-xl p-2 text-2xl ${avatar === item ? 'ring-2 ring-violet bg-white' : ''}`}
            onClick={() => setAvatar(item)}
          >
            {animal[item]}
          </button>
        ))}
      </div>
      <button className="btn-primary mt-3" onClick={() => onSave({ name, avatar })}>
        Save
      </button>
    </div>
  )
}

function WordStatusList({
  title,
  rows,
  words,
}: {
  title: string
  rows: ProgressRow[]
  words: Word[]
}) {
  return (
    <div className="rounded-2xl bg-[#f7f3ff] p-4">
      <h3 className="font-black">{title}</h3>
      <div className="mt-2 max-h-36 overflow-auto space-y-1">
        {rows.length ? (
          rows.map((row) => (
            <p key={row.id} className="text-sm font-bold text-[#646b89]">
              {words.find((word) => word.id === row.word_id)?.english || 'Removed word'}{' '}
              <span className="text-violet">
                {row.direction === 'en-ru' ? 'EN → RU' : 'RU → EN'}
              </span>
            </p>
          ))
        ) : (
          <p className="text-sm text-[#8a8fa8]">No words yet</p>
        )}
      </div>
    </div>
  )
}
