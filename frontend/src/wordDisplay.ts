import type { Word } from './api'

export function englishPrefix(word: Pick<Word, 'part_of_speech' | 'ipa'>): string {
  if (word.part_of_speech === 'verb') return 'to '
  if (word.part_of_speech === 'singular countable' && word.ipa) {
    const firstSound = word.ipa
      .toLowerCase()
      .replace(/[ˈˌːˑ]/gu, '')
      .match(/\p{L}/u)?.[0]
    if (firstSound) {
      return 'aeiouæɑɐɒəɛɜɞɘɵøɶɪʊʌɨʉɯɤɔœɚɝ'.includes(firstSound) ? 'an ' : 'a '
    }
  }
  return ''
}

export function displayEnglish(word: Pick<Word, 'english' | 'part_of_speech' | 'ipa'>): string {
  const prefix = englishPrefix(word)
  if (word.part_of_speech === 'singular countable') {
    return prefix + word.english.trim().replace(/^(?:a|an)\s+/i, '')
  }
  if (word.part_of_speech === 'verb') {
    return prefix + word.english.trim().replace(/^to\s+/i, '')
  }
  return word.english
}
