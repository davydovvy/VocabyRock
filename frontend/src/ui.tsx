import { BookOpen, LockKeyhole, Sparkles, Volume2 } from 'lucide-react'
import type { ReactNode } from 'react'

export const animal: Record<string, string> = {
  fox: '🦊',
  bear: '🐻',
  rabbit: '🐰',
  cat: '🐱',
  dog: '🐶',
  owl: '🦉',
  panda: '🐼',
  koala: '🐨',
}
export const packArt: Record<string, { emoji: string; bg: string }> = {
  Animals: { emoji: '🦁', bg: 'bg-[#ffe7ae]' },
  Food: { emoji: '🍎', bg: 'bg-[#ffd6d0]' },
  'Everyday Objects': { emoji: '🏠', bg: 'bg-[#d5f1ff]' },
}
export function Avatar({ name, size = 'normal' }: { name: string; size?: 'normal' | 'large' }) {
  return (
    <span
      aria-hidden="true"
      className={`${size === 'large' ? 'text-6xl md:text-7xl' : 'text-4xl'} inline-flex items-center justify-center`}
    >
      {animal[name] || '🦊'}
    </span>
  )
}
export function Logo() {
  return (
    <div className="inline-flex items-center gap-2 font-black text-2xl tracking-tight">
      <img src="/logo.svg" className="h-11 w-11" alt="" />
      <span>
        Vacaby<span className="text-violet">Rock</span>
      </span>
    </div>
  )
}
export function Shell({
  children,
  right,
  className = '',
}: {
  children: ReactNode
  right?: ReactNode
  className?: string
}) {
  return (
    <div className={`min-h-screen ${className}`}>
      <header className="mx-auto max-w-7xl px-4 md:px-8 py-5 flex items-center justify-between gap-3">
        <Logo />
        {right}
      </header>
      <main className="mx-auto max-w-7xl px-4 md:px-8 pb-16">{children}</main>
    </div>
  )
}
export function ProgressBar({ value }: { value: number }) {
  return (
    <div
      role="progressbar"
      aria-valuenow={Math.round(value)}
      aria-valuemin={0}
      aria-valuemax={100}
      className="h-3 rounded-full bg-[#e9e5f5] overflow-hidden"
    >
      <div
        className="h-full rounded-full bg-gradient-to-r from-mint via-sky to-violet transition-all"
        style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
      />
    </div>
  )
}
export function Empty({ title, text }: { title: string; text?: string }) {
  return (
    <div className="card p-8 text-center">
      <BookOpen className="mx-auto mb-3 text-violet" size={36} />
      <p className="text-xl font-black">{title}</p>
      {text && <p className="mt-2 text-[#68708e]">{text}</p>}
    </div>
  )
}
export function Speak({ word, accent }: { word: string; accent: string }) {
  const supported = typeof window !== 'undefined' && 'speechSynthesis' in window
  const play = () => {
    if (!supported) return
    window.speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance(word)
    utterance.lang = accent
    utterance.rate = 0.85
    const voice = window.speechSynthesis
      .getVoices()
      .find((v) => v.lang.toLowerCase() === accent.toLowerCase())
    if (voice) utterance.voice = voice
    window.speechSynthesis.speak(utterance)
  }
  return (
    <button
      disabled={!supported}
      onClick={play}
      className="btn-soft"
      aria-label={`Listen to ${word}`}
      title={supported ? 'Listen' : 'Voice is unavailable'}
    >
      <Volume2 size={24} />
      <span>Listen</span>
    </button>
  )
}
export function ParentLock() {
  return <LockKeyhole size={19} aria-hidden="true" />
}
export function Star() {
  return <Sparkles className="text-[#e5a414]" fill="#ffce60" aria-hidden="true" />
}
