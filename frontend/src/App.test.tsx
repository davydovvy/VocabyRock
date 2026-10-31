import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from './App'

const profiles = [
  { id: 1, role: 'parent', name: 'Parent', avatar: 'owl' },
  { id: 2, role: 'child', name: 'Explorer One', avatar: 'fox', xp: 0, stars: 0 },
  { id: 3, role: 'child', name: 'Explorer Two', avatar: 'bear', xp: 0, stars: 0 },
]
const config = {
  accent: 'en-US',
  direction: 'en-ru',
  session_length: 10,
  allowed_exercises: ['choice', 'match', 'flashcard', 'type', 'listen'],
  child_avatar_change: true,
  avatars: ['fox', 'bear'],
}
const packs = [
  {
    id: 1,
    name: 'Animals',
    description: 'Animal friends',
    category: 'Animals',
    cover: null,
    word_ids: [1],
    word_count: 1,
    learned_count: 0,
    learned: false,
  },
]
const stats = {
  user: profiles[1],
  learned: 0,
  studying: 0,
  difficult: 0,
  due: 0,
  success_rate: 0,
  attempts: 0,
  achievements: [],
  recent_sessions: [],
  upcoming_reviews: [],
}
let loggedIn: (typeof profiles)[number] | null = null
let answeredIndices: number[] = []
let practiceTasks: {
  prompt: string
  ipa?: string
  options?: { token: number; text: string }[]
  big_match?: boolean
  locked?: boolean
  last_token?: number
}[] = [
  {
    prompt: 'cat',
    options: [
      { token: 1, text: 'кошка' },
      { token: 2, text: 'собака' },
    ],
  },
]
let requests: string[] = []
let startedPractices: { mode: string; kind: string; direction: string; pack_id: number | null }[] =
  []
let practiceKind: 'choice' | 'type' | 'match' = 'choice'
let practiceDirection: 'en-ru' | 'ru-en' = 'en-ru'
let fullHintUsed = false
let firstMatchResults:
  { index: number; correct: boolean; answer: string; chosen: string; word_id: number }[] | null =
  null
let pictureUploadFailures = 0
let learnedChildren = new Set<number>()
let savedWords: {
  id: number
  english: string
  translations: string[]
  ipa: string | null
  part_of_speech: string | null
  picture: string | null
  audio?: string | null
  audio_status?: string | null
  example_en: string | null
  example_ru: string | null
  notes: string | null
}[] = []

function response(value: unknown, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}
function mockApi(taskCount = 1, kind: 'choice' | 'type' | 'match' = 'choice') {
  loggedIn = null
  answeredIndices = []
  practiceKind = kind
  practiceDirection = 'en-ru'
  fullHintUsed = false
  firstMatchResults = null
  practiceTasks = (
    kind === 'match'
      ? Array.from({ length: 8 }, (_, index) => ({ prompt: `word${index + 1}`, big_match: true }))
      : kind === 'type'
        ? [
            { prompt: 'понедельник', ipa: '/ˈmʌndeɪ/' },
            { prompt: 'вторник', ipa: '/ˈtuːzdeɪ/' },
          ]
        : [
            {
              prompt: 'cat',
              options: [
                { token: 1, text: 'кошка' },
                { token: 2, text: 'собака' },
              ],
            },
            {
              prompt: 'dog',
              options: [
                { token: 3, text: 'собака' },
                { token: 4, text: 'кошка' },
              ],
            },
          ]
  ).slice(0, taskCount)
  requests = []
  startedPractices = []
  pictureUploadFailures = 0
  learnedChildren = new Set()
  savedWords = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, options?: RequestInit) => {
      const path = url.replace('/api', '')
      requests.push(`${options?.method || 'GET'} ${path}`)
      if (path === '/profiles') return response(profiles)
      if (path === '/auth/me')
        return loggedIn ? response(loggedIn) : response({ detail: 'Sign in' }, 401)
      if (path === '/auth/child') {
        loggedIn = profiles[1]
        return response(loggedIn)
      }
      if (path === '/auth/parent') {
        if (JSON.parse(String(options?.body)).password !== 'test-parent-password')
          return response({ detail: 'Wrong password' }, 401)
        loggedIn = profiles[0]
        return response(loggedIn)
      }
      if (path === '/config') return response(config)
      if (path === '/library/archive/inspect' && options?.method === 'POST')
        return response({ words: 31, packs: 4 })
      if (path === '/library/archive' && options?.method === 'POST')
        return response({ words: 31, packs: 4 })
      if (path === '/packs') return response(packs)
      if (path === '/stats') return response(stats)
      if (path.startsWith('/stats?')) return response(stats)
      if (path.startsWith('/progress?')) {
        const childId = Number(new URL(path, 'http://localhost').searchParams.get('child_id'))
        return response(
          learnedChildren.has(childId)
            ? [{ id: childId, word_id: 1, direction: 'ru-en', learned: true }]
            : [],
        )
      }
      if (path === '/progress/learned' && options?.method === 'PUT') {
        const { child_id, learned } = JSON.parse(String(options.body))
        if (learned) learnedChildren.add(child_id)
        else learnedChildren.delete(child_id)
        return response({ learned })
      }
      if (path === '/practice' && options?.method === 'POST') {
        const body = JSON.parse(String(options.body))
        startedPractices.push(body)
        practiceKind = body.mode === 'test' ? 'type' : kind
        if (body.mode === 'test') practiceTasks = [{ prompt: 'кошка' }]
        practiceDirection =
          body.mode === 'test' ? 'ru-en' : kind === 'match' ? 'en-ru' : body.direction
        return response(
          {
            id: 10,
            kind: practiceKind,
            mode: body.mode,
            direction: practiceDirection,
            tasks: practiceTasks,
            match_options:
              kind === 'match'
                ? Array.from({ length: 8 }, (_, index) => ({
                    token: 8 - index,
                    text: `слово${8 - index}`,
                  }))
                : undefined,
            results: [],
            finished: false,
          },
          201,
        )
      }
      if (path === '/practice/10/match-all' && options?.method === 'POST') {
        const pairs = JSON.parse(String(options.body)).pairs as {
          index: number
          option_id: number
        }[]
        const results = pairs.map((pair) => ({
          index: pair.index,
          correct: pair.option_id === pair.index + 1,
          answer: `слово${pair.index + 1}`,
          chosen: `слово${pair.option_id}`,
          word_id: pair.index + 1,
        }))
        practiceTasks = practiceTasks.map((task, index) => ({
          ...task,
          locked: results[index].correct,
          last_token: pairs[index].option_id,
        }))
        if (!firstMatchResults) firstMatchResults = results
        return response({
          id: 10,
          kind: 'match',
          mode: 'all',
          direction: 'en-ru',
          tasks: practiceTasks,
          match_options: Array.from({ length: 8 }, (_, index) => ({
            token: 8 - index,
            text: `слово${8 - index}`,
          })),
          results: firstMatchResults,
          finished: results.every((result) => result.correct),
        })
      }
      if (path === '/practice/10/hint/0' && options?.method === 'POST') {
        const level = JSON.parse(String(options.body)).level
        if (level === 2) fullHintUsed = true
        return response({ hint: level === 1 ? 'M----y' : 'Monday' })
      }
      if (path === '/practice/10/answer') {
        const index = JSON.parse(String(options?.body)).index as number
        answeredIndices.push(index)
        return response({
          correct: !fullHintUsed,
          assisted: fullHintUsed,
          retry: false,
          answer: practiceKind === 'type' ? ['Monday'] : [index === 0 ? 'кошка' : 'собака'],
          finished: answeredIndices.length === practiceTasks.length,
        })
      }
      if (path === '/practice/10')
        return response({
          id: 10,
          kind: practiceKind,
          mode: 'all',
          direction: practiceDirection,
          tasks: practiceTasks,
          results: answeredIndices.map((index) => ({
            index,
            correct: !fullHintUsed,
            answer: practiceKind === 'type' ? ['Monday'] : [index === 0 ? 'кошка' : 'собака'],
            word_id: index + 1,
          })),
          finished: answeredIndices.length === practiceTasks.length,
        })
      if (path === '/settings')
        return response({
          session_length: 10,
          accent: 'en-US',
          direction: 'en-ru',
          fold_yo: true,
          lenient_typos: false,
          allowed_exercises: config.allowed_exercises,
          child_avatar_change: true,
        })
      if ((path === '/words' || path.startsWith('/words?pack_id=')) && options?.method === 'POST') {
        const input = JSON.parse(String(options.body))
        const word = {
          ...input,
          id: 1,
          picture: null,
          audio: null,
          audio_status: input.audio_url ? 'pending' : null,
        }
        savedWords.push(word)
        return response(word, 201)
      }
      if (path === '/words/1' && options?.method === 'PUT') {
        savedWords[0] = { ...savedWords[0], ...JSON.parse(String(options.body)) }
        return response(savedWords[0])
      }
      if (path === '/dictionary?word=tree')
        return response({
          word: 'tree',
          translations: [
            { word: 'де́рево', sense: 'large woody plant' },
            { word: 'дре́во', sense: 'poetic' },
          ],
          ipa: '/tɹiː/',
          part_of_speech: 'noun',
          audio: [
            {
              url: 'https://upload.wikimedia.org/wikipedia/commons/a/ab/tree.mp3',
              label: 'tree.mp3',
              tags: ['US'],
            },
          ],
        })
      if (path === '/dictionary?word=january')
        return response({
          word: 'January',
          translations: [{ word: 'январь', sense: 'month' }],
          ipa: '/ˈdʒænjuˌɛɹi/',
          part_of_speech: 'name',
          us_spelling: '',
          audio: [],
        })
      if (path.startsWith('/pixabay/search?q='))
        return response({
          hits: [
            {
              id: 42,
              preview_url:
                '/api/pixabay/preview?url=https%3A%2F%2Fcdn.pixabay.com%2Fphoto%2Ftree_150.jpg',
              page_url: 'https://pixabay.com/photos/tree-42/',
              tags: 'tree, nature',
              user: 'Contributor',
            },
          ],
        })
      if (path === '/words/1/pixabay' && options?.method === 'POST') {
        savedWords[0].picture = '/media/tree.webp'
        return response({ picture: '/media/tree.webp' })
      }
      if (path === '/words/1/picture' && options?.method === 'POST') {
        if (pictureUploadFailures > 0) {
          pictureUploadFailures -= 1
          return response({ detail: 'Picture upload failed' }, 503)
        }
        savedWords[0].picture = '/media/upload.webp'
        return response({ picture: '/media/upload.webp' })
      }
      if (path === '/words/1/picture' && options?.method === 'DELETE') {
        savedWords[0].picture = null
        return response({ picture: null })
      }
      if (path === '/words') return response(savedWords)
      return response({ detail: `Unmocked: ${path}` }, 404)
    }),
  )
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('critical child and parent interactions', () => {
  it('checks a vocabulary archive before replacing the library', async () => {
    mockApi()
    vi.stubGlobal('confirm', () => true)
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: /Parent Parent area/ }))
    await user.type(screen.getByLabelText('Password'), 'test-parent-password')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    await user.click(await screen.findByRole('button', { name: 'Import / Export' }))
    expect(screen.getByRole('button', { name: 'Download archive' })).toBeTruthy()
    expect(screen.queryByText('Import CSV')).toBeNull()
    await user.upload(
      screen.getByLabelText('ZIP archive'),
      new File(['archive'], 'library.zip', { type: 'application/zip' }),
    )
    await user.click(screen.getByRole('button', { name: 'Check archive' }))
    expect(await screen.findByText('Archive contains 31 words and 4 packs.')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: 'Replace library' }))
    await waitFor(() => expect(requests).toContain('POST /library/archive'))
  })

  it('selects a child, opens a pack, completes a game, and sees stars', async () => {
    mockApi()
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: /Explorer One/ }))
    expect(await screen.findByRole('heading', { name: /Ready to study/ })).toBeTruthy()
    await user.click(screen.getAllByRole('button', { name: /Study/ })[1])
    await user.click(await screen.findByRole('button', { name: /Pick the Word/ }))
    expect(await screen.findByText('cat')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: 'кошка' }))
    expect(await screen.findByText('Great!')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: /See Stars/ }))
    expect(await screen.findByText('Great job!')).toBeTruthy()
    expect(requests.some((x) => x.includes('/practice/10/answer'))).toBe(true)
  })

  it('offers both printable pack sheets in the parent area', async () => {
    mockApi()
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: /Parent Parent area/ }))
    await user.type(screen.getByLabelText('Password'), 'test-parent-password')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    await user.click(await screen.findByRole('button', { name: 'Word Packs' }))
    expect(screen.getByRole('button', { name: 'Word sheet' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Writing test' })).toBeTruthy()
  })

  it('starts a separate pack test with English typing and no hints', async () => {
    mockApi()
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: /Explorer One/ }))
    await user.click(await screen.findByRole('button', { name: 'Test' }))
    expect(startedPractices.at(-1)).toMatchObject({
      mode: 'test',
      kind: 'type',
      direction: 'ru-en',
      pack_id: 1,
    })
    expect(await screen.findByText('кошка')).toBeTruthy()
    expect(screen.getByRole('textbox', { name: 'Your answer' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Show whole word' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'First and last letters' })).toBeNull()
  })

  it('keeps the answered word and answer visible until Next is pressed', async () => {
    mockApi(2)
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: /Explorer One/ }))
    await screen.findByRole('heading', { name: /Ready to study/ })
    await user.click(screen.getAllByRole('button', { name: /Study/ })[1])
    await user.click(await screen.findByRole('button', { name: /Pick the Word/ }))
    await user.click(await screen.findByRole('button', { name: 'кошка' }))
    const next = screen.getByRole('button', { name: /Next/ })
    await waitFor(() => expect(next.hasAttribute('disabled')).toBe(false))
    expect(screen.getByText('Answer: кошка')).toBeTruthy()
    expect(screen.getByText('cat')).toBeTruthy()
    expect(screen.queryByText('dog')).toBeNull()
    await user.click(next)
    expect(await screen.findByText('dog')).toBeTruthy()
  })

  it('shows typing hints without transcription and advances with Enter after an answer', async () => {
    mockApi(2, 'type')
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: /Explorer One/ }))
    await screen.findByRole('heading', { name: /Ready to study/ })
    await user.click(screen.getAllByRole('button', { name: /Study/ })[1])
    await user.click(screen.getByRole('button', { name: 'Russian → English' }))
    await user.click(screen.getByRole('button', { name: /Type It/ }))
    expect(await screen.findByText('понедельник')).toBeTruthy()
    expect(screen.queryByText('/ˈmʌndeɪ/')).toBeNull()

    await user.click(screen.getByRole('button', { name: 'First and last letters' }))
    expect(await screen.findByText('M----y')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: 'Show whole word' }))
    expect(await screen.findByText('Monday')).toBeTruthy()
    expect(screen.getByText('This word is added to mistakes for later practice.')).toBeTruthy()
    await user.type(screen.getByRole('textbox', { name: 'Your answer' }), 'Monday{enter}')
    expect(await screen.findByText('You got it! Practice this word again later.')).toBeTruthy()
    const next = screen.getByRole('button', { name: /Next/ })
    await waitFor(() => expect(next.hasAttribute('disabled')).toBe(false))
    expect(next).toBe(document.activeElement)
    await user.keyboard('{Enter}')
    expect(await screen.findByText('вторник')).toBeTruthy()
    expect(screen.queryByText('M----y')).toBeNull()
  })

  it('offers one Big Match and scores only after eight placements', async () => {
    mockApi(8, 'match')
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: /Explorer One/ }))
    await screen.findByRole('heading', { name: /Ready to study/ })
    await user.click(screen.getAllByRole('button', { name: /Study/ })[1])
    expect(screen.queryByRole('button', { name: 'Find Pairs' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Find Pairs Challenge' })).toBeNull()
    await user.click(screen.getByRole('button', { name: 'Big Match' }))
    expect(await screen.findByRole('heading', { name: 'Big Match!' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Check' }).hasAttribute('disabled')).toBe(true)
    const english = within(screen.getByRole('group', { name: 'English words' }))
    const russian = within(screen.getByRole('group', { name: 'Russian translations' }))
    await user.click(russian.getByRole('button', { name: 'слово2' }))
    await user.click(english.getByRole('button', { name: 'word1, empty' }))
    await user.click(russian.getByRole('button', { name: 'слово1' }))
    await user.click(english.getByRole('button', { name: 'word2, empty' }))
    expect(screen.queryByText(/right! Fix/)).toBeNull()
    expect(document.querySelector('.big-match-card.is-correct')).toBeNull()
    expect(document.querySelector('.big-match-card.is-incorrect')).toBeNull()
    for (let index = 3; index <= 8; index++) {
      await user.click(russian.getByRole('button', { name: `слово${index}` }))
      await user.click(english.getByRole('button', { name: `word${index}, empty` }))
    }
    expect(screen.getByRole('button', { name: 'Check' }).hasAttribute('disabled')).toBe(false)
    expect(requests.filter((request) => request === 'POST /practice/10/match-all')).toHaveLength(0)
    await user.click(screen.getByRole('button', { name: 'Check' }))
    expect(await screen.findByText('6 right! Fix 2 more!')).toBeTruthy()
    expect(document.querySelectorAll('.big-match-card.is-correct')).toHaveLength(6)
    expect(document.querySelectorAll('.big-match-card.is-incorrect')).toHaveLength(2)
    expect(screen.getByRole('button', { name: 'слово3' }).hasAttribute('disabled')).toBe(true)
    expect(screen.getByRole('button', { name: 'Check' }).hasAttribute('disabled')).toBe(true)
    await user.click(english.getByRole('button', { name: 'слово2' }))
    await user.click(english.getByRole('button', { name: 'word2, filled' }))
    await user.click(russian.getByRole('button', { name: 'слово1' }))
    await user.click(english.getByRole('button', { name: 'word1, empty' }))
    await user.click(screen.getByRole('button', { name: 'Check' }))
    expect(await screen.findByRole('heading', { name: 'You Rock!' })).toBeTruthy()
    expect(screen.getByText('First check: 6 of 8 right!')).toBeTruthy()
    expect(requests.filter((request) => request === 'POST /practice/10/match-all')).toHaveLength(2)
    expect(requests.filter((request) => request === 'POST /practice/10/answer')).toHaveLength(0)
  })

  it('opens the parent password dialog and signs in', async () => {
    mockApi()
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: /Parent Parent area/ }))
    await user.type(screen.getByLabelText('Password'), 'wrong')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await within(screen.getByRole('dialog')).findByText('Wrong password')).toBeTruthy()
    await user.clear(screen.getByLabelText('Password'))
    await user.type(screen.getByLabelText('Password'), 'test-parent-password')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    await waitFor(() => expect(screen.getByText('Welcome, Parent')).toBeTruthy())
    expect(requests).toContain('POST /auth/parent')
  })

  it('edits each child learned checkbox in vocabulary and pack word lists', async () => {
    mockApi()
    learnedChildren.add(2)
    savedWords.push({
      id: 1,
      english: 'cat',
      translations: ['кошка'],
      ipa: null,
      part_of_speech: null,
      picture: null,
      example_en: null,
      example_ru: null,
      notes: null,
    })
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: /Parent Parent area/ }))
    await user.type(screen.getByLabelText('Password'), 'test-parent-password')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    await user.click(await screen.findByRole('button', { name: 'Vocabulary' }))
    const first = (await screen.findByRole('checkbox', {
      name: 'Explorer One learned cat',
    })) as HTMLInputElement
    const second = screen.getByRole('checkbox', {
      name: 'Explorer Two learned cat',
    }) as HTMLInputElement
    await waitFor(() => expect(first.disabled).toBe(false))
    expect(first.checked).toBe(true)
    expect(second.checked).toBe(false)
    await user.click(first)
    await waitFor(() => expect(first.checked).toBe(false))
    expect(learnedChildren.has(2)).toBe(false)
    await user.click(second)
    await waitFor(() => expect(second.checked).toBe(true))
    expect(learnedChildren.has(3)).toBe(true)

    await user.click(screen.getByRole('button', { name: 'Word Packs' }))
    await user.click(screen.getByRole('button', { name: 'Manage Words' }))
    const packFirst = (await screen.findByRole('checkbox', {
      name: 'Explorer One learned cat',
    })) as HTMLInputElement
    const packSecond = screen.getByRole('checkbox', {
      name: 'Explorer Two learned cat',
    }) as HTMLInputElement
    expect(packFirst.checked).toBe(false)
    expect(packSecond.checked).toBe(true)
    await user.click(packFirst)
    await waitFor(() => expect(packFirst.checked).toBe(true))
    expect(requests.filter((request) => request === 'PUT /progress/learned')).toHaveLength(3)
  })

  it('plays downloaded word audio from vocabulary and pack lists', async () => {
    mockApi()
    savedWords.push(
      {
        id: 1,
        english: 'cat',
        translations: ['кошка'],
        ipa: null,
        part_of_speech: null,
        picture: null,
        audio: '/audio/cat.mp3',
        audio_status: 'ready',
        example_en: null,
        example_ru: null,
        notes: null,
      },
      {
        id: 2,
        english: 'dog',
        translations: ['собака'],
        ipa: null,
        part_of_speech: null,
        picture: null,
        audio: null,
        example_en: null,
        example_ru: null,
        notes: null,
      },
    )
    const recordings: string[] = []
    vi.stubGlobal(
      'Audio',
      class {
        constructor(url: string) {
          recordings.push(url)
        }
        play() {
          return Promise.resolve()
        }
      },
    )
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: /Parent Parent area/ }))
    await user.type(screen.getByLabelText('Password'), 'test-parent-password')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    await user.click(await screen.findByRole('button', { name: 'Vocabulary' }))
    await user.click(await screen.findByRole('button', { name: 'Listen to cat' }))
    expect(screen.queryByRole('button', { name: 'Listen to dog' })).toBeNull()
    await user.click(screen.getByRole('button', { name: 'Word Packs' }))
    await user.click(screen.getByRole('button', { name: 'Manage Words' }))
    await user.click(await screen.findByRole('button', { name: 'Listen to cat' }))
    expect(recordings).toEqual(['/audio/cat.mp3', '/audio/cat.mp3'])
  })

  it('lets the parent add a word with a Russian translation', async () => {
    mockApi()
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: /Parent Parent area/ }))
    await user.type(screen.getByLabelText('Password'), 'test-parent-password')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    await user.click(await screen.findByRole('button', { name: 'Vocabulary' }))
    await user.click(screen.getByRole('button', { name: 'Add Word' }))
    const partOfSpeech = screen.getByRole('combobox', {
      name: 'Part of speech',
    }) as HTMLSelectElement
    expect(partOfSpeech.value).toBe('')
    expect(screen.queryByLabelText('English example')).toBeNull()
    expect(screen.queryByLabelText('Russian example')).toBeNull()
    expect(screen.queryByLabelText('Notes')).toBeNull()
    await user.selectOptions(partOfSpeech, 'noun')
    await user.type(screen.getByLabelText('English'), 'tree')
    await user.type(screen.getByLabelText('Russian translations (separate with ;)'), 'дерево')
    await user.click(screen.getByRole('button', { name: 'Save Word' }))
    expect(await screen.findByText('tree')).toBeTruthy()
    expect(savedWords[0].translations).toEqual(['дерево'])
    expect(savedWords[0].part_of_speech).toBe('noun')
  })

  it('adds a new word from a pack and opens pack words for editing', async () => {
    mockApi()
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: /Parent Parent area/ }))
    await user.type(screen.getByLabelText('Password'), 'test-parent-password')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    await user.click(await screen.findByRole('button', { name: 'Word Packs' }))
    await user.click(screen.getByRole('button', { name: 'Manage Words' }))
    await user.click(screen.getByRole('button', { name: 'New Word' }))
    expect(screen.getByRole('dialog', { name: 'Add Word to Animals' })).toBeTruthy()
    await user.type(screen.getByLabelText('English'), 'mountain')
    await user.type(screen.getByLabelText('Russian translations (separate with ;)'), 'гора')
    await user.click(screen.getByRole('button', { name: 'Save Word' }))
    await waitFor(() => expect(requests).toContain('POST /words?pack_id=1'))
    await user.click(await screen.findByRole('button', { name: 'Edit mountain' }))
    expect(screen.getByRole('dialog', { name: 'Edit Word' })).toBeTruthy()
    const translations = screen.getByLabelText('Russian translations (separate with ;)')
    await user.clear(translations)
    await user.type(translations, 'вершина')
    await user.click(screen.getByRole('button', { name: 'Save Word' }))
    await waitFor(() => expect(requests).toContain('PUT /words/1'))
    expect(savedWords[0].translations).toEqual(['вершина'])
  })

  it('warns about a duplicate word while adding or editing', async () => {
    mockApi()
    savedWords.push({
      id: 1,
      english: 'tree',
      translations: ['дерево'],
      ipa: null,
      part_of_speech: null,
      picture: null,
      example_en: null,
      example_ru: null,
      notes: null,
    })
    savedWords.push({ ...savedWords[0], id: 2, english: 'river', translations: ['река'] })
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: /Parent Parent area/ }))
    await user.type(screen.getByLabelText('Password'), 'test-parent-password')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    await user.click(await screen.findByRole('button', { name: 'Vocabulary' }))
    await user.click(screen.getByRole('button', { name: 'Add Word' }))
    await user.type(screen.getByLabelText('English'), ' TREE ')
    expect(screen.getByRole('alert').textContent).toContain('already in the vocabulary library')
    expect((screen.getByRole('button', { name: 'Save Word' }) as HTMLButtonElement).disabled).toBe(
      true,
    )
    await user.click(screen.getByRole('button', { name: 'Close' }))
    await user.click(screen.getByRole('button', { name: 'Edit tree' }))
    await user.clear(screen.getByLabelText('English'))
    await user.type(screen.getByLabelText('English'), 'RIVER')
    expect(screen.getByRole('alert').textContent).toContain('“river”')
    expect((screen.getByRole('button', { name: 'Save Word' }) as HTMLButtonElement).disabled).toBe(
      true,
    )
    expect(requests.filter((request) => request === 'POST /words')).toHaveLength(0)
  })

  it('preserves hidden examples, notes, and an imported part of speech when editing', async () => {
    mockApi()
    savedWords.push({
      id: 1,
      english: 'tree',
      translations: ['дерево'],
      ipa: null,
      part_of_speech: 'prefix',
      picture: '/media/original.webp',
      example_en: 'A tall tree.',
      example_ru: 'Высокое дерево.',
      notes: 'Imported note',
    })
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: /Parent Parent area/ }))
    await user.type(screen.getByLabelText('Password'), 'test-parent-password')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    await user.click(await screen.findByRole('button', { name: 'Vocabulary' }))
    await user.click(await screen.findByRole('button', { name: 'Edit tree' }))
    const partOfSpeech = screen.getByRole('combobox', {
      name: 'Part of speech',
    }) as HTMLSelectElement
    expect(partOfSpeech.value).toBe('prefix')
    expect(screen.queryByLabelText('English example')).toBeNull()
    expect(screen.queryByLabelText('Russian example')).toBeNull()
    expect(screen.queryByLabelText('Notes')).toBeNull()
    expect((screen.getByRole('img', { name: 'Word picture' }) as HTMLImageElement).src).toContain(
      '/media/original.webp',
    )
    await user.click(screen.getByRole('button', { name: 'Search Pixabay' }))
    const searchPreview = await screen.findByRole('img', { name: 'tree, nature' })
    expect(searchPreview.getAttribute('src')).toContain('/api/pixabay/preview?url=')
    fireEvent.error(searchPreview)
    await user.click(screen.getByRole('button', { name: 'Preview unavailable. Tap to retry.' }))
    expect((screen.getByRole('img', { name: 'tree, nature' }) as HTMLImageElement).src).toContain(
      'retry=1',
    )
    await user.click(await screen.findByRole('button', { name: 'Choose picture' }))
    await user.click(screen.getByRole('button', { name: 'Save Word' }))
    await waitFor(() => expect(requests).toContain('POST /words/1/pixabay'))
    expect(savedWords[0].example_en).toBe('A tall tree.')
    expect(savedWords[0].example_ru).toBe('Высокое дерево.')
    expect(savedWords[0].notes).toBe('Imported note')
    expect(savedWords[0].part_of_speech).toBe('prefix')
    expect(savedWords[0].picture).toBe('/media/tree.webp')
  })

  it('removes a word picture on save without replacing the word', async () => {
    mockApi()
    savedWords.push({
      id: 1,
      english: 'tree',
      translations: ['дерево'],
      ipa: null,
      part_of_speech: null,
      picture: '/media/original.webp',
      example_en: null,
      example_ru: null,
      notes: null,
    })
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: /Parent Parent area/ }))
    await user.type(screen.getByLabelText('Password'), 'test-parent-password')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    await user.click(await screen.findByRole('button', { name: 'Vocabulary' }))
    await user.click(screen.getByRole('button', { name: 'Edit tree' }))
    await user.click(screen.getByRole('button', { name: 'Remove picture' }))
    expect(screen.queryByRole('img', { name: 'Word picture' })).toBeNull()
    expect(screen.getByText('Picture will be removed when you save this word.')).toBeTruthy()
    expect(savedWords[0].picture).toBe('/media/original.webp')
    await user.click(screen.getByRole('button', { name: 'Keep current picture' }))
    expect(screen.getByRole('img', { name: 'Word picture' })).toBeTruthy()
    await user.click(screen.getByRole('button', { name: 'Remove picture' }))
    await user.click(screen.getByRole('button', { name: 'Save Word' }))
    await waitFor(() => expect(requests).toContain('DELETE /words/1/picture'))
    expect(savedWords[0].picture).toBeNull()
    expect(savedWords).toHaveLength(1)
  })

  it('offers dictionary translations and saves the selected recording', async () => {
    mockApi()
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: /Parent Parent area/ }))
    await user.type(screen.getByLabelText('Password'), 'test-parent-password')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    await user.click(await screen.findByRole('button', { name: 'Vocabulary' }))
    await user.click(screen.getByRole('button', { name: 'Add Word' }))
    await user.type(screen.getByLabelText('English'), 'tree')
    await new Promise((resolve) => setTimeout(resolve, 700))
    expect(requests.filter((request) => request.startsWith('GET /dictionary'))).toEqual([])
    await user.click(screen.getByRole('button', { name: 'Fill from Wikimedia' }))
    expect(requests.filter((request) => request.startsWith('GET /dictionary'))).toEqual([
      'GET /dictionary?word=tree',
    ])
    await user.click(await screen.findByRole('button', { name: /де́рево/ }))
    expect((screen.getByLabelText('IPA') as HTMLInputElement).value).toBe('/tɹiː/')
    expect(
      (screen.getByRole('combobox', { name: 'Part of speech' }) as HTMLSelectElement).value,
    ).toBe('noun')
    await user.click(screen.getByRole('radio', { name: /US/ }))
    await user.click(screen.getByRole('button', { name: 'Save Word' }))
    await waitFor(() => expect(savedWords).toHaveLength(1))
    expect(savedWords[0].translations).toEqual(['де́рево'])
    expect(
      (savedWords[0] as (typeof savedWords)[number] & { audio_url: string }).audio_url,
    ).toContain('upload.wikimedia.org')
    expect(await screen.findByText('Audio queued for download')).toBeTruthy()
  })

  it('replaces the typed case with the Wikimedia headword when filling a word', async () => {
    mockApi()
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: /Parent Parent area/ }))
    await user.type(screen.getByLabelText('Password'), 'test-parent-password')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    await user.click(await screen.findByRole('button', { name: 'Vocabulary' }))
    await user.click(screen.getByRole('button', { name: 'Add Word' }))
    await user.type(screen.getByLabelText('English'), 'january')
    await user.click(screen.getByRole('button', { name: 'Fill from Wikimedia' }))
    await screen.findByRole('button', { name: /январь/ })
    expect((screen.getByLabelText('English') as HTMLInputElement).value).toBe('January')
    await user.click(screen.getByRole('button', { name: /январь/ }))
    await user.click(screen.getByRole('button', { name: 'Save Word' }))
    await waitFor(() => expect(savedWords).toHaveLength(1))
    expect(savedWords[0].english).toBe('January')
  })

  it('lets the parent choose a Pixabay picture while preserving the typed case', async () => {
    mockApi()
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: /Parent Parent area/ }))
    await user.type(screen.getByLabelText('Password'), 'test-parent-password')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    await user.click(await screen.findByRole('button', { name: 'Vocabulary' }))
    await user.click(screen.getByRole('button', { name: 'Add Word' }))
    const dialog = screen.getByRole('dialog', { name: 'Add Word' })
    await user.type(within(dialog).getByLabelText('English'), 'TrEe')
    expect((within(dialog).getByLabelText('English') as HTMLInputElement).value).toBe('TrEe')
    await user.type(
      within(dialog).getByLabelText('Russian translations (separate with ;)'),
      'ДЕРЕВО',
    )
    expect(
      (within(dialog).getByLabelText('Russian translations (separate with ;)') as HTMLInputElement)
        .value,
    ).toBe('дерево')
    await user.click(within(dialog).getByRole('button', { name: 'Search Pixabay' }))
    expect(await within(dialog).findByRole('img', { name: 'tree, nature' })).toBeTruthy()
    await user.click(within(dialog).getByRole('button', { name: 'Choose picture' }))
    expect(within(dialog).getByText('Selected Pixabay picture: tree, nature')).toBeTruthy()
    await user.click(within(dialog).getByRole('button', { name: 'Save Word' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(savedWords[0].picture).toBe('/media/tree.webp')
    expect(savedWords[0].english).toBe('TrEe')
    expect(savedWords[0].translations).toEqual(['дерево'])
    expect(requests.indexOf('POST /words/1/pixabay')).toBeGreaterThan(
      requests.indexOf('POST /words'),
    )
    expect(screen.queryByRole('button', { name: /Find picture for tree/ })).toBeNull()
  })

  it('keeps a newly saved word in the edit form if its picture upload fails', async () => {
    mockApi()
    pictureUploadFailures = 1
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: /Parent Parent area/ }))
    await user.type(screen.getByLabelText('Password'), 'test-parent-password')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    await user.click(await screen.findByRole('button', { name: 'Vocabulary' }))
    await user.click(screen.getByRole('button', { name: 'Add Word' }))
    await user.type(screen.getByLabelText('English'), 'TREE')
    await user.type(screen.getByLabelText('Russian translations (separate with ;)'), 'ДЕРЕВО')
    await user.upload(
      screen.getByLabelText('Upload picture'),
      new File(['picture bytes'], 'tree.png', { type: 'image/png' }),
    )
    expect(screen.getByText('Selected: tree.png')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: 'Save Word' }))
    expect(await screen.findByRole('alert')).toHaveProperty(
      'textContent',
      expect.stringContaining('Picture upload failed'),
    )
    expect(savedWords).toHaveLength(1)
    expect(screen.getByRole('dialog', { name: 'Edit Word' })).toBeTruthy()
    await user.click(screen.getByRole('button', { name: 'Save Word' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(savedWords).toHaveLength(1)
    expect(savedWords[0].picture).toBe('/media/upload.webp')
    expect(requests.filter((request) => request === 'POST /words')).toHaveLength(1)
    expect(requests).toContain('PUT /words/1')
  })

  it('shows the same sample pack artwork in the parent area', async () => {
    mockApi()
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: /Parent Parent area/ }))
    await user.type(screen.getByLabelText('Password'), 'test-parent-password')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    await user.click(await screen.findByRole('button', { name: 'Word Packs' }))
    expect(within(screen.getByRole('article')).getByText('🦁')).toBeTruthy()
  })
})
