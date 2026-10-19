import { defineConfig } from '@playwright/test'

// Expects the full stack to be running (see README). BASE_URL overrides the target.
export default defineConfig({
  testDir: './e2e',
  workers: 1, // tests share one seeded database; run them serially for deterministic state
  use: { baseURL: process.env.BASE_URL ?? 'http://127.0.0.1:5173' },
  reporter: [['list']],
})
