import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:4174',
    trace: 'retain-on-failure',
    // Most specs check technical details, so they start with Under the hood on.
    // customer-view.spec.ts covers the default customer view.
    storageState: {
      cookies: [],
      origins: [
        {
          origin: 'http://127.0.0.1:4174',
          localStorage: [{ name: 'ai-foundry-lab-under-the-hood', value: '1' }],
        },
      ],
    },
  },
  projects: [
    {
      name: 'desktop',
      use: { browserName: 'chromium', viewport: { width: 1440, height: 1000 } },
    },
  ],
  webServer: {
    command: 'npm run preview -- --host 127.0.0.1 --port 4174 --strictPort',
    url: 'http://127.0.0.1:4174',
    reuseExistingServer: false,
  },
})
