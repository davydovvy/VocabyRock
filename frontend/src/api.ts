export type Profile = {
  id: number
  role: 'child' | 'parent'
  name: string
  avatar: string
  sound_enabled?: boolean
  xp?: number
  stars?: number
}
export type Word = {
  id: number
  guid: string
  english: string
  translations: string[]
  ipa: string | null
  part_of_speech: string | null
  picture: string | null
  audio: string | null
  audio_status?: 'pending' | 'retrying' | 'ready' | 'failed' | null
  audio_error?: string | null
  example_en: string | null
  example_ru: string | null
  notes: string | null
}
export type WordInput = Omit<Word, 'id' | 'guid' | 'picture' | 'audio'> & {
  audio_url?: string | null
}
export type DictionaryResult = {
  word: string
  translations: { word: string; sense: string }[]
  ipa: string
  part_of_speech: string
  us_spelling: string
  audio: { url: string; label: string; tags: string[] }[]
}
export type Pack = {
  id: number
  guid: string
  name: string
  description: string
  category: string | null
  cover: string | null
  word_ids: number[]
  word_count: number
  learned_count: number
  learned: boolean
}
export type PixabayHit = {
  id: number
  preview_url: string
  page_url: string
  tags: string
  user: string
}
export type Config = {
  accent: string
  direction: 'en-ru' | 'ru-en'
  session_length: number
  allowed_exercises: Kind[]
  child_avatar_change: boolean
  avatars: string[]
}
export type Kind = 'match' | 'match_all' | 'flashcard' | 'choice' | 'type' | 'listen'
export type Mode = 'quick' | 'new' | 'practice' | 'hard' | 'all' | 'mistakes' | 'test'
export type Task = {
  prompt?: string | null
  picture?: string | null
  ipa?: string | null
  audio?: string | null
  hint?: string | null
  speech?: string
  options?: { token: number; text: string }[]
  big_match?: boolean
  locked?: boolean
  last_token?: number
}
export type Result = {
  index: number
  correct: boolean
  answer: string | string[]
  chosen?: string
  word_id: number
}
export type Practice = {
  id: number
  kind: Kind
  mode: Mode
  direction: 'en-ru' | 'ru-en'
  tasks: Task[]
  results: Result[]
  match_options?: { token: number; text: string }[]
  finished: boolean
}
export type Stats = {
  user: Profile
  learned: number
  studying: number
  difficult: number
  due: number
  success_rate: number
  attempts: number
  achievements: string[]
  recent_sessions: { id: number; kind: string; date: string; correct: number; total: number }[]
  upcoming_reviews: { word_id: number; direction: string; next_review_at: string }[]
}
export type ProgressRow = {
  id: number
  word_id: number
  direction: string
  attempts: number
  correct: number
  incorrect: number
  status: 'new' | 'learning' | 'review' | 'mastered'
  typed_streak: number
  learned: boolean
  next_review_at: string | null
}
export type Settings = {
  session_length: number
  accent: string
  direction: string
  fold_yo: boolean
  lenient_typos: boolean
  allowed_exercises: Kind[]
  child_avatar_change: boolean
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, {
    credentials: 'same-origin',
    ...options,
    headers: {
      ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...options.headers,
    },
  })
  if (!response.ok) {
    let message = `Something went wrong (${response.status})`
    try {
      const error = await response.json()
      if (typeof error.detail === 'string') message = error.detail
      else if (Array.isArray(error.detail))
        message = error.detail
          .map(
            (item: { loc?: (string | number)[]; msg?: string }) =>
              `${item.loc?.at(-1) || 'Field'}: ${item.msg || 'Invalid value'}`,
          )
          .join('; ')
    } catch {
      /* use fallback */
    }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}
export const json = (method: string, data?: unknown): RequestInit => ({
  method,
  body: data === undefined ? undefined : JSON.stringify(data),
})
export async function download(path: string, name: string) {
  const response = await fetch(`/api${path}`, { credentials: 'same-origin' })
  if (!response.ok) throw new Error('Download failed')
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = name
  document.body.append(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}
