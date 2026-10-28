import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
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
let practiceKind: 'choice' | 'type' | 'match_all' = 'choice'
let practiceDirection: 'en-ru' | 'ru-en' = 'en-ru'
let fullHintUsed = false
let pictureUploadFailures = 0
let savedWords: {
  id: number
  english: string
  translations: string[]
  ipa: string | null
  part_of_speech: string | null
  picture: string | null
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
function mockApi(taskCount = 1, kind: 'choice' | 'type' | 'match_all' = 'choice') {
  loggedIn = null
  answeredIndices = []
  practiceKind = kind
  practiceDirection = 'en-ru'
  fullHintUsed = false
  practiceTasks = (
    kind === 'match_all'
      ? Array.from({ length: 10 }, (_, index) => ({ prompt: `word${index + 1}` }))
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
  pictureUploadFailures = 0
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
      if (path === '/packs') return response(packs)
      if (path === '/stats') return response(stats)
      if (path.startsWith('/stats?')) return response(stats)
      if (path.startsWith('/progress?')) return response([])
      if (path === '/practice' && options?.method === 'POST') {
        practiceDirection =
          kind === 'match_all' ? 'en-ru' : JSON.parse(String(options.body)).direction
        return response(
          {
            id: 10,
            kind: practiceKind,
            mode: 'all',
            direction: practiceDirection,
            tasks: practiceTasks,
            match_options:
              kind === 'match_all'
                ? Array.from({ length: 10 }, (_, index) => ({
                    token: 10 - index,
                    text: `слово${10 - index}`,
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
        return response({
          id: 10,
          kind: 'match_all',
          mode: 'all',
          direction: 'en-ru',
          tasks: practiceTasks,
          results: pairs.map((pair) => ({
            index: pair.index,
            correct: pair.option_id === pair.index + 1,
            answer: `слово${pair.index + 1}`,
            chosen: `слово${pair.option_id}`,
            word_id: pair.index + 1,
          })),
          finished: true,
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
              preview_url: 'https://cdn.pixabay.com/photo/tree_150.jpg',
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
  it('selects a child, opens a pack, completes a game, and sees stars', async () => {
    mockApi()
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: /Explorer One/ }))
    expect(await screen.findByRole('heading', { name: /Ready to play/ })).toBeTruthy()
    await user.click(screen.getAllByRole('button', { name: /Play/ })[1])
    await user.click(await screen.findByRole('button', { name: /Pick the Word/ }))
    expect(await screen.findByText('cat')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: 'кошка' }))
    expect(await screen.findByText('Great!')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: /See Stars/ }))
    expect(await screen.findByText('Great job!')).toBeTruthy()
    expect(requests.some((x) => x.includes('/practice/10/answer'))).toBe(true)
  })

  it('keeps the answered word and answer visible until Next is pressed', async () => {
    mockApi(2)
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: /Explorer One/ }))
    await screen.findByRole('heading', { name: /Ready to play/ })
    await user.click(screen.getAllByRole('button', { name: /Play/ })[1])
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
    await screen.findByRole('heading', { name: /Ready to play/ })
    await user.click(screen.getAllByRole('button', { name: /Play/ })[1])
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

  it('lets a child change ten pairs and checks them only after submission', async () => {
    mockApi(10, 'match_all')
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: /Explorer One/ }))
    await screen.findByRole('heading', { name: /Ready to play/ })
    await user.click(screen.getAllByRole('button', { name: /Play/ })[1])
    await user.click(screen.getByRole('button', { name: 'Find Pairs Challenge' }))
    expect(await screen.findByRole('heading', { name: 'Match all 10 pairs' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Check all pairs' }).hasAttribute('disabled')).toBe(
      true,
    )
    const english = within(screen.getByRole('group', { name: 'English words' }))
    const russian = within(screen.getByRole('group', { name: 'Russian translations' }))
    await user.click(english.getByRole('button', { name: /^1\. word1\b/ }))
    await user.click(russian.getByRole('button', { name: 'слово2' }))
    await user.click(english.getByRole('button', { name: /^2\. word2\b/ }))
    await user.click(russian.getByRole('button', { name: 'слово1' }))
    await user.click(english.getByRole('button', { name: /^1\. word1\b/ }))
    await user.click(russian.getByRole('button', { name: /слово1$/ }))
    for (let index = 3; index <= 10; index++) {
      await user.click(
        english.getByRole('button', { name: new RegExp(`^${index}\\. word${index}\\b`) }),
      )
      await user.click(russian.getByRole('button', { name: `слово${index}` }))
    }
    expect(screen.getByText('10 of 10 pairs chosen')).toBeTruthy()
    expect(requests.filter((request) => request === 'POST /practice/10/match-all')).toHaveLength(0)
    await user.click(screen.getByRole('button', { name: 'Check all pairs' }))
    expect(await screen.findByRole('heading', { name: 'Great job!' })).toBeTruthy()
    expect(screen.getByText('You got 10 of 10 right!')).toBeTruthy()
    expect(requests.filter((request) => request === 'POST /practice/10/match-all')).toHaveLength(1)
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
    await user.click(await screen.findByRole('button', { name: 'Choose picture' }))
    await user.click(screen.getByRole('button', { name: 'Save Word' }))
    await waitFor(() => expect(requests).toContain('POST /words/1/pixabay'))
    expect(savedWords[0].example_en).toBe('A tall tree.')
    expect(savedWords[0].example_ru).toBe('Высокое дерево.')
    expect(savedWords[0].notes).toBe('Imported note')
    expect(savedWords[0].part_of_speech).toBe('prefix')
    expect(savedWords[0].picture).toBe('/media/tree.webp')
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
