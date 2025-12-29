/**
 * Custom test utilities for Unstract frontend
 * Provides render helpers with common providers
 */
import React from 'react';
import { render } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';

/**
 * Custom render function that wraps components with necessary providers
 * @param {React.ReactElement} ui - Component to render
 * @param {Object} options - Render options
 * @param {string} options.route - Initial route for router
 * @param {Object} options.renderOptions - Additional render options
 * @returns {Object} Render result with custom utilities
 */
function customRender(ui, { route = '/', ...renderOptions } = {}) {
  // Set initial route
  window.history.pushState({}, 'Test page', route);

  function AllTheProviders({ children }) {
    return <BrowserRouter>{children}</BrowserRouter>;
  }

  return {
    ...render(ui, { wrapper: AllTheProviders, ...renderOptions }),
    // Add custom utilities here
  };
}

/**
 * Create a mock axios instance for testing
 * @returns {Object} Mock axios instance
 */
function createMockAxios() {
  return {
    get: jest.fn(() => Promise.resolve({ data: {} })),
    post: jest.fn(() => Promise.resolve({ data: {} })),
    put: jest.fn(() => Promise.resolve({ data: {} })),
    delete: jest.fn(() => Promise.resolve({ data: {} })),
    patch: jest.fn(() => Promise.resolve({ data: {} })),
    create: jest.fn(function () {
      return this;
    }),
    interceptors: {
      request: { use: jest.fn(), eject: jest.fn() },
      response: { use: jest.fn(), eject: jest.fn() },
    },
  };
}

/**
 * Create a mock session store state
 * @param {Object} overrides - State overrides
 * @returns {Object} Mock session state
 */
function createMockSessionState(overrides = {}) {
  return {
    sessionDetails: {
      isLoggedIn: true,
      orgName: 'test-org',
      role: 'admin',
      adapters: { llm: true, vectorDb: true },
      ...overrides.sessionDetails,
    },
    isLogoutLoading: false,
    setSessionDetails: jest.fn(),
    updateSessionDetails: jest.fn(),
    setLogoutLoading: jest.fn(),
    ...overrides,
  };
}

/**
 * Wait for async operations in tests
 * @param {number} ms - Milliseconds to wait
 * @returns {Promise} Promise that resolves after delay
 */
function waitFor(ms = 0) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Mock window.location for tests
 * @param {Object} locationOverrides - Location properties to override
 */
function mockWindowLocation(locationOverrides = {}) {
  const originalLocation = window.location;
  delete window.location;
  window.location = {
    ...originalLocation,
    pathname: '/',
    search: '',
    hash: '',
    href: 'http://localhost/',
    origin: 'http://localhost',
    assign: jest.fn(),
    replace: jest.fn(),
    reload: jest.fn(),
    ...locationOverrides,
  };
  return () => {
    window.location = originalLocation;
  };
}

// Re-export everything from @testing-library/react
export * from '@testing-library/react';

// Override render with custom render
export { customRender as render, createMockAxios, createMockSessionState, waitFor, mockWindowLocation };
