import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 45_000,
  use: {
    baseURL: process.env.BASE_URL || 'http://127.0.0.1:8787',
    ...devices['Desktop Chrome'],
    launchOptions: { executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium' },
  },
  reporter: 'list',
})
