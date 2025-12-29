/**
 * Playwright E2E Test Configuration for Unstract
 * Configured for tiered test execution and CI integration
 */
const { defineConfig, devices } = require('@playwright/test');

/**
 * Read environment variables from file.
 * https://github.com/motdotla/dotenv
 */
require('dotenv').config({ path: '.env.e2e' });

/**
 * @see https://playwright.dev/docs/test-configuration
 */
module.exports = defineConfig({
  // Test directory
  testDir: './tests',

  // Test file pattern
  testMatch: '**/*.spec.js',

  // Maximum time one test can run
  timeout: 60 * 1000,

  // Expect timeout
  expect: {
    timeout: 10000,
  },

  // Run tests in files in parallel
  fullyParallel: true,

  // Fail the build on CI if you accidentally left test.only in the source code
  forbidOnly: !!process.env.CI,

  // Retry on CI only
  retries: process.env.CI ? 2 : 0,

  // Opt out of parallel tests on CI for stability
  workers: process.env.CI ? 1 : undefined,

  // Reporter configuration
  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-report' }],
    ['json', { outputFile: 'test-results/results.json' }],
    ...(process.env.CI ? [['github']] : []),
  ],

  // Shared settings for all projects
  use: {
    // Base URL for the application
    baseURL: process.env.BASE_URL || 'http://localhost:3000',

    // Collect trace when retrying the failed test
    trace: 'on-first-retry',

    // Take screenshot on failure
    screenshot: 'only-on-failure',

    // Record video on failure
    video: 'on-first-retry',

    // Browser context options
    contextOptions: {
      ignoreHTTPSErrors: true,
    },

    // Action timeout
    actionTimeout: 15000,

    // Navigation timeout
    navigationTimeout: 30000,
  },

  // Configure projects for major browsers
  projects: [
    // Authentication setup project
    {
      name: 'setup',
      testMatch: /.*\.setup\.js/,
    },

    // Critical path tests - must pass for release
    {
      name: 'critical',
      testMatch: /critical\/.*\.spec\.js/,
      use: {
        ...devices['Desktop Chrome'],
      },
      dependencies: ['setup'],
    },

    // Standard tests - Chrome only for speed
    {
      name: 'chrome',
      testMatch: /(?<!critical\/).*\.spec\.js/,
      testIgnore: /critical\/.*\.spec\.js/,
      use: {
        ...devices['Desktop Chrome'],
      },
      dependencies: ['setup'],
    },

    // Cross-browser tests - run on release branches
    {
      name: 'firefox',
      testMatch: /(?<!critical\/).*\.spec\.js/,
      testIgnore: /critical\/.*\.spec\.js/,
      use: {
        ...devices['Desktop Firefox'],
      },
      dependencies: ['setup'],
    },

    // Mobile viewport tests
    {
      name: 'mobile',
      testMatch: /(?<!critical\/).*\.spec\.js/,
      testIgnore: /critical\/.*\.spec\.js/,
      use: {
        ...devices['Pixel 5'],
      },
      dependencies: ['setup'],
    },
  ],

  // Folder for test artifacts such as screenshots, videos, traces
  outputDir: 'test-results/',

  // Run local dev server before starting tests
  webServer: process.env.CI
    ? undefined
    : {
        command: 'cd ../frontend && npm start',
        url: 'http://localhost:3000',
        reuseExistingServer: !process.env.CI,
        timeout: 120 * 1000,
      },
});
