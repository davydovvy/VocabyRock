import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  testMatch: 'keyboard-assistance.spec.ts',
  use: {
    baseURL: process.env.BASE_URL || 'http://127.0.0.1:8787',
    ...devices['iPad Pro 11'],
    browserName: 'webkit',
  },
  reporter: 'list',
})
