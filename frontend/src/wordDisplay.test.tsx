import { expect, it } from 'vitest'
import { displayEnglish } from './wordDisplay'

it.each([
  ['cat', '/kæt/', 'a cat'],
  ['dog', '/dɔɡ/', 'a dog'],
  ['book', '/bʊk/', 'a book'],
  ['house', '/haʊs/', 'a house'],
  ['university', '/ˌjuːnɪˈvɜːrsɪti/', 'a university'],
  ['European country', '/ˌjʊərəˈpiːən ˈkʌntri/', 'a European country'],
  ['apple', '/ˈæpəl/', 'an apple'],
  ['elephant', '/ˈɛlɪfənt/', 'an elephant'],
  ['orange', '/ˈɔːrɪndʒ/', 'an orange'],
  ['umbrella', '/ʌmˈbrɛlə/', 'an umbrella'],
  ['hour', '/ˈaʊər/', 'an hour'],
  ['honest person', '/ˈɒnɪst ˈpɜːrsən/', 'an honest person'],
  ['apple', '/kæpəl/', 'a apple'],
  ['apple', null, 'apple'],
  ['apple', '///', 'apple'],
])('uses the IPA sound for %s (%s)', (english, ipa, expected) => {
  expect(displayEnglish({ english, ipa, part_of_speech: 'singular countable' })).toBe(expected)
})
