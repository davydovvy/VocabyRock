import { useEffect, useState } from 'react'
import { ArrowRight, LockKeyhole, X } from 'lucide-react'
import { api, json, type Config, type Profile } from './api'
import Child from './Child'
import Parent from './Parent'
import { Avatar, Logo, Shell } from './ui'

export default function App() {
  const [profiles, setProfiles] = useState<Profile[]>([])
  const [user, setUser] = useState<Profile | null>(null)
  const [config, setConfig] = useState<Config | null>(null)
  const [parentOpen, setParentOpen] = useState(false)
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const loadConfig = async () => setConfig(await api<Config>('/config'))
  useEffect(() => {
    Promise.all([api<Profile[]>('/profiles'), api<Profile>('/auth/me').catch(() => null)])
      .then(async ([list, current]) => {
        setProfiles(list)
        if (current) {
          setUser(current)
          await loadConfig()
        }
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])
  const chooseChild = async (profile: Profile) => {
    setError('')
    try {
      const next = await api<Profile>('/auth/child', json('POST', { user_id: profile.id }))
      setUser(next)
      await loadConfig()
    } catch (e) {
      setError((e as Error).message)
    }
  }
  const parentLogin = async (event: React.FormEvent) => {
    event.preventDefault()
    setError('')
    try {
      const next = await api<Profile>('/auth/parent', json('POST', { password }))
      setUser(next)
      await loadConfig()
      setParentOpen(false)
      setPassword('')
    } catch (e) {
      setError((e as Error).message)
    }
  }
  const logout = async () => {
    try {
      await api('/auth/logout', json('POST'))
    } catch {
      /* local view still resets */
    }
    setUser(null)
    setConfig(null)
    setError('')
    setProfiles(await api<Profile[]>('/profiles'))
  }

  if (loading)
    return (
      <Shell>
        <div className="flex min-h-[60vh] items-center justify-center font-black text-2xl text-violet">
          Loading VacabyRock…
        </div>
      </Shell>
    )
  if (user && config)
    return user.role === 'parent' ? (
      <Parent config={config} onLogout={() => void logout()} />
    ) : (
      <Child user={user} config={config} onLogout={() => void logout()} onUserChange={setUser} />
    )
  return (
    <div className="profile-screen min-h-screen">
      <header className="mx-auto max-w-7xl px-4 md:px-8 py-6">
        <Logo />
      </header>
      <main className="mx-auto max-w-6xl px-4 pb-16">
        <section className="profile-welcome text-center pt-9 md:pt-14">
          <div className="text-6xl floaty" aria-hidden="true">
            ✨
          </div>
          <p className="mt-6 text-violet font-black uppercase tracking-[.2em] text-sm">
            Welcome to your word adventure
          </p>
          <h1 className="mt-2 text-4xl md:text-6xl font-black tracking-tight">
            Who is playing today?
          </h1>
          <p className="mt-4 text-lg font-bold text-[#707793]">Pick your explorer and let's go!</p>
        </section>
        {error && (
          <p
            role="alert"
            className="mx-auto mt-7 max-w-xl rounded-2xl bg-[#ffe4e1] p-4 text-center font-bold text-[#9b4242]"
          >
            {error}
          </p>
        )}
        <section
          aria-label="Choose a profile"
          className="profile-grid mt-10 grid gap-5 sm:grid-cols-3"
        >
          {profiles.map((profile, i) => (
            <button
              key={profile.id}
              onClick={() => {
                if (profile.role === 'parent') {
                  setError('')
                  setParentOpen(true)
                } else void chooseChild(profile)
              }}
              className="profile-card card group relative min-h-72 p-6 text-center transition-transform hover:-translate-y-2 focus-visible:-translate-y-2"
            >
              <div
                className={`mx-auto flex h-32 w-32 items-center justify-center rounded-full ${i === 0 ? 'bg-[#e8e1ff]' : i === 1 ? 'bg-[#ffe5ca]' : 'bg-[#d8f4e8]'} shadow-inner`}
              >
                <Avatar name={profile.avatar} size="large" />
              </div>
              <h2 className="mt-5 text-2xl font-black">{profile.name}</h2>
              <p className="mt-1 font-bold text-[#777d99]">
                {profile.role === 'parent' ? (
                  <span className="inline-flex items-center gap-1">
                    <LockKeyhole size={16} /> Parent area
                  </span>
                ) : (
                  'Ready to explore!'
                )}
              </p>
              <span className="mt-4 inline-flex items-center gap-1 font-black text-violet">
                {profile.role === 'parent' ? 'Sign in' : 'Study'} <ArrowRight size={19} />
              </span>
            </button>
          ))}
        </section>
        <p className="profile-footer mt-10 text-center font-bold text-[#8b90a7]">
          Learn a word. Earn a star. Rock on!
        </p>
      </main>
      {parentOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-[#29234b]/50 p-4"
          role="presentation"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setParentOpen(false)
          }}
        >
          <form
            onSubmit={(e) => void parentLogin(e)}
            role="dialog"
            aria-modal="true"
            aria-label="Parent password"
            className="card w-full max-w-md p-7"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="rounded-2xl bg-[#eee8ff] p-3 text-violet">
                  <LockKeyhole />
                </span>
                <h2 className="text-2xl font-black">Parent sign in</h2>
              </div>
              <button
                type="button"
                className="btn-soft !p-2"
                aria-label="Close"
                onClick={() => setParentOpen(false)}
              >
                <X />
              </button>
            </div>
            <label className="label mt-7" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              autoFocus
              type="password"
              className="field"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
            {error && (
              <p role="alert" className="mt-3 font-bold text-coral">
                {error}
              </p>
            )}
            <button className="btn-primary w-full mt-6" type="submit">
              Sign in
            </button>
          </form>
        </div>
      )}
    </div>
  )
}
