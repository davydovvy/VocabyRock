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
let practiceTasks = [
  {
    prompt: 'cat',
    options: [
      { token: 1, text: 'кошка' },
      { token: 2, text: 'собака' },
    ],
  },
]
let requests: string[] = []
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
function mockApi(taskCount = 1) {
  loggedIn = null
  answeredIndices = []
  practiceTasks = [
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
  ].slice(0, taskCount)
  requests = []
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
      if (path === '/practice' && options?.method === 'POST')
        return response(
          {
            id: 10,
            kind: 'choice',
            mode: 'all',
            direction: 'en-ru',
            tasks: practiceTasks,
            results: [],
            finished: false,
          },
          201,
        )
      if (path === '/practice/10/answer') {
        const index = JSON.parse(String(options?.body)).index as number
        answeredIndices.push(index)
        return response({
          correct: true,
          retry: false,
          answer: [index === 0 ? 'кошка' : 'собака'],
          finished: answeredIndices.length === practiceTasks.length,
        })
      }
      if (path === '/practice/10')
        return response({
          id: 10,
          kind: 'choice',
          mode: 'all',
          direction: 'en-ru',
          tasks: practiceTasks,
          results: answeredIndices.map((index) => ({
            index,
            correct: true,
            answer: [index === 0 ? 'кошка' : 'собака'],
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
      if (path === '/words' && options?.method === 'POST') {
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
      if (path === '/dictionary?word=tree')
        return response({
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
    await user.type(screen.getByLabelText('English'), 'tree')
    await user.type(screen.getByLabelText('Russian translations (separate with ;)'), 'дерево')
    await user.click(screen.getByRole('button', { name: 'Save Word' }))
    expect(await screen.findByText('tree')).toBeTruthy()
    expect(savedWords[0].translations).toEqual(['дерево'])
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
    await user.click(screen.getByRole('radio', { name: /US/ }))
    await user.click(screen.getByRole('button', { name: 'Save Word' }))
    await waitFor(() => expect(savedWords).toHaveLength(1))
    expect(savedWords[0].translations).toEqual(['де́рево'])
    expect(
      (savedWords[0] as (typeof savedWords)[number] & { audio_url: string }).audio_url,
    ).toContain('upload.wikimedia.org')
    expect(await screen.findByText('Audio queued for download')).toBeTruthy()
  })

  it('lets the parent choose a Pixabay picture for a word', async () => {
    mockApi()
    const user = userEvent.setup()
    render(<App />)
    await user.click(await screen.findByRole('button', { name: /Parent Parent area/ }))
    await user.type(screen.getByLabelText('Password'), 'test-parent-password')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    await user.click(await screen.findByRole('button', { name: 'Vocabulary' }))
    await user.click(screen.getByRole('button', { name: 'Add Word' }))
    await user.type(screen.getByLabelText('English'), 'tree')
    await user.type(screen.getByLabelText('Russian translations (separate with ;)'), 'дерево')
    await user.click(screen.getByRole('button', { name: 'Save Word' }))
    await user.click(
      await screen.findByRole('button', { name: 'Find picture for tree on Pixabay' }),
    )
    const dialog = await screen.findByRole('dialog', { name: 'Pixabay pictures for tree' })
    expect(await within(dialog).findByRole('img', { name: 'tree, nature' })).toBeTruthy()
    await user.click(within(dialog).getByRole('button', { name: 'Use picture' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(savedWords[0].picture).toBe('/media/tree.webp')
    expect(requests).toContain('POST /words/1/pixabay')
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
