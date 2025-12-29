/**
 * Jest configuration for Unstract frontend
 * Configured for React Testing Library with coverage thresholds
 */
module.exports = {
  // Use jsdom for DOM testing
  testEnvironment: 'jsdom',

  // Setup files run before each test
  setupFilesAfterEnv: ['<rootDir>/src/setupTests.js'],

  // Module name mapping for imports
  moduleNameMapper: {
    // Handle CSS imports (with CSS modules)
    '^.+\\.module\\.(css|sass|scss)$': 'identity-obj-proxy',
    // Handle CSS imports (without CSS modules)
    '^.+\\.(css|sass|scss)$': '<rootDir>/src/__mocks__/styleMock.js',
    // Handle image imports
    '^.+\\.(jpg|jpeg|png|gif|webp|svg)$': '<rootDir>/src/__mocks__/fileMock.js',
  },

  // Test file patterns
  testMatch: [
    '<rootDir>/src/**/__tests__/**/*.{js,jsx}',
    '<rootDir>/src/**/*.{spec,test}.{js,jsx}',
  ],

  // Files to ignore
  testPathIgnorePatterns: ['/node_modules/', '/build/'],

  // Transform files with babel
  transform: {
    '^.+\\.(js|jsx)$': 'babel-jest',
  },

  // Don't transform node_modules except these packages
  transformIgnorePatterns: [
    '/node_modules/(?!(axios|uuid|zustand)/)',
  ],

  // Coverage configuration
  collectCoverageFrom: [
    'src/**/*.{js,jsx}',
    '!src/index.js',
    '!src/reportWebVitals.js',
    '!src/setupProxy.js',
    '!src/setupTests.js',
    '!src/**/*.d.ts',
    '!src/__mocks__/**',
    '!src/__tests__/**',
  ],

  // Coverage thresholds by priority
  coverageThreshold: {
    // Global thresholds (relaxed for brownfield)
    global: {
      branches: 20,
      functions: 20,
      lines: 20,
      statements: 20,
    },
    // Critical: Core paths - higher thresholds
    './src/store/': {
      branches: 60,
      functions: 60,
      lines: 60,
      statements: 60,
    },
    './src/hooks/': {
      branches: 50,
      functions: 50,
      lines: 50,
      statements: 50,
    },
    './src/components/helpers/auth/': {
      branches: 70,
      functions: 70,
      lines: 70,
      statements: 70,
    },
  },

  // Coverage reporters
  coverageReporters: ['text', 'text-summary', 'lcov', 'html', 'json-summary'],

  // Coverage output directory
  coverageDirectory: '<rootDir>/coverage',

  // Verbose output
  verbose: true,

  // Clear mocks between tests
  clearMocks: true,

  // Restore mocks automatically
  restoreMocks: true,

  // Maximum workers for parallel execution
  maxWorkers: '50%',

  // Fail tests on console errors/warnings (helps catch issues early)
  // Disabled initially for brownfield - enable progressively
  // errorOnDeprecated: true,
};
