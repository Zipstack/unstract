# Testing Guide

This document covers the testing infrastructure, quick start commands, and CI workflow for the Unstract monorepo.

## Table of Contents

- [Quick Start](#quick-start)
- [Test Infrastructure Overview](#test-infrastructure-overview)
- [Frontend Testing](#frontend-testing)
- [Backend Testing](#backend-testing)
- [E2E Testing](#e2e-testing)
- [CI Workflow](#ci-workflow)
- [Coverage Reporting](#coverage-reporting)

---

## Quick Start

### Frontend Tests

```bash
# Navigate to frontend directory
cd frontend

# Run tests in interactive watch mode
npm test

# Run tests with coverage report
npm run test:coverage

# Run only unit tests (stores, hooks, utils)
npm run test:unit

# Run only component tests
npm run test:components

# Run tests in CI mode (coverage + JUnit reports)
npm run test:ci
```

### Backend Tests

```bash
# Run all services with HTML coverage report
./scripts/run-coverage.sh all --html

# Run specific service
./scripts/run-coverage.sh backend
./scripts/run-coverage.sh sdk1
./scripts/run-coverage.sh connectors
./scripts/run-coverage.sh platform-service

# Run with multiple report formats
./scripts/run-coverage.sh all --html --xml --json

# Using pytest directly with markers
pytest -m "critical" backend/                 # Critical tests only
pytest -m "important" backend/                # Important tests only
pytest -m "not slow and not integration"      # Fast unit tests only
pytest -m "integration" backend/              # Integration tests only

# Run specific test file
pytest backend/connector_v2/tests/connector_tests.py -v

# Run with coverage for specific module
pytest --cov=backend --cov-report=html backend/
```

### E2E Tests

```bash
# Navigate to E2E directory and install dependencies
cd e2e
npm install
npx playwright install

# Run critical path tests only (fastest)
npm run test:critical

# Run all tests in Chrome
npm run test:chrome

# Run cross-browser tests (Chrome + Firefox)
npm run test:all-browsers

# Run mobile viewport tests
npm run test:mobile

# Run tests with UI (interactive mode)
npm run test:ui

# Run tests in debug mode
npm run test:debug

# Generate tests using codegen
npm run codegen

# View last test report
npm run report
```

### Using tox (Existing CI Pattern)

```bash
# Run all tox environments
tox

# Run specific environment
tox -e runner
tox -e sdk1
```

---

## Test Infrastructure Overview

### Directory Structure

```
├── frontend/
│   ├── jest.config.js              # Jest configuration
│   ├── src/
│   │   ├── __mocks__/              # Jest mocks
│   │   ├── __tests__/
│   │   │   ├── components/         # Component tests
│   │   │   ├── hooks/              # Hook tests
│   │   │   ├── store/              # Zustand store tests
│   │   │   └── utils/              # Test utilities
│   │   └── setupTests.js           # Jest setup
│   └── package.json
│
├── e2e/
│   ├── playwright.config.js        # Playwright configuration
│   ├── package.json
│   ├── tests/
│   │   ├── critical/               # Critical E2E tests
│   │   │   ├── authentication.spec.js
│   │   │   ├── workflow-execution.spec.js
│   │   │   └── connector-management.spec.js
│   │   └── auth.setup.js           # Auth state setup
│   ├── fixtures/                   # Test fixtures
│   └── utils/                      # Helper utilities
│
├── scripts/
│   └── run-coverage.sh             # Per-service coverage runner
│
├── .github/workflows/
│   ├── ci-test.yaml                # Legacy tox-based tests
│   └── ci-tiered-tests.yaml        # Priority-based test execution
│
└── pyproject.toml                  # pytest + coverage config
```

---

## Frontend Testing

### Configuration

Frontend tests use Jest with React Testing Library. Configuration is in `frontend/jest.config.js`.

**Coverage Thresholds (by Priority):**

| Path | Branches | Functions | Lines |
|------|----------|-----------|-------|
| Global | 20% | 20% | 20% |
| `src/store/` | 60% | 60% | 60% |
| `src/hooks/` | 50% | 50% | 50% |
| `src/components/helpers/auth/` | 70% | 70% | 70% |

### Writing Tests

```javascript
// Use custom render for router context
import { render, screen } from '../utils/test-utils';

// Test a component
describe('MyComponent', () => {
  it('should render correctly', () => {
    render(<MyComponent />);
    expect(screen.getByText('Hello')).toBeInTheDocument();
  });
});

// Test a Zustand store
import { renderHook, act } from '@testing-library/react';
import { useMyStore } from '../../store/my-store';

describe('useMyStore', () => {
  it('should update state', () => {
    const { result } = renderHook(() => useMyStore());
    act(() => {
      result.current.setSomeValue('test');
    });
    expect(result.current.someValue).toBe('test');
  });
});
```

---

## Backend Testing

### Test Markers

Tests are categorized using pytest markers defined in `pyproject.toml`:

| Marker | Description | When to Use |
|--------|-------------|-------------|
| `critical` | Critical path tests | Must pass for release |
| `important` | Important tests | Should pass for release |
| `standard` | Extended tests | Best effort |
| `slow` | Long-running tests | Skip for fast feedback |
| `integration` | Integration tests | Require external services |

### Writing Tests

```python
import pytest

@pytest.mark.critical
def test_critical_functionality():
    """This test must pass for any release."""
    assert critical_function() == expected_result

@pytest.mark.important
@pytest.mark.integration
def test_database_integration():
    """Integration test requiring database."""
    # Test code here

@pytest.mark.slow
def test_performance_benchmark():
    """Long-running performance test."""
    # Test code here
```

### Coverage Configuration

Coverage settings in `pyproject.toml`:

```toml
[tool.coverage.run]
branch = true
source = ["backend", "platform-service", "prompt-service", "workers", "unstract"]
omit = ["*/migrations/*", "*/tests/*", "*/__pycache__/*"]

[tool.coverage.report]
show_missing = true
fail_under = 0  # Adjust as coverage improves
```

---

## E2E Testing

### Configuration

E2E tests use Playwright with multiple browser projects defined in `e2e/playwright.config.js`:

| Project | Browser | Purpose |
|---------|---------|---------|
| `setup` | - | Authentication state setup |
| `critical` | Chrome | Critical path tests |
| `chrome` | Chrome | Standard tests |
| `firefox` | Firefox | Cross-browser verification |
| `mobile` | Pixel 5 | Mobile viewport tests |

### Environment Variables

Create `e2e/.env.e2e` from the example:

```bash
cp e2e/.env.e2e.example e2e/.env.e2e
```

Required variables:

| Variable | Description |
|----------|-------------|
| `BASE_URL` | Application URL (default: http://localhost:3000) |
| `TEST_USER_EMAIL` | Test user email for auth tests |
| `TEST_USER_PASSWORD` | Test user password |
| `TEST_ORG_NAME` | Test organization name |

### Writing E2E Tests

```javascript
const { test, expect } = require('@playwright/test');
const { waitForPageLoad, login } = require('../utils/test-helpers');

test.describe('Feature Name', () => {
  test('should do something important', async ({ page }) => {
    await page.goto('/some-page');
    await waitForPageLoad(page);

    await expect(page.getByRole('heading')).toBeVisible();
  });
});
```

---

## CI Workflow

The CI workflow is defined in `.github/workflows/ci-tiered-tests.yaml`.

### Workflow Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         PR / Push                                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    CRITICAL Tests (Must Pass)                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Backend    │  │     SDK      │  │   Frontend   │          │
│  │   Critical   │  │   Critical   │  │    Unit      │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                         MUST PASS                                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   IMPORTANT Tests (Should Pass)                  │
│  ┌──────────────────────┐  ┌──────────────────────┐            │
│  │     Integration      │  │     Connectors       │            │
│  │       Tests          │  │       Tests          │            │
│  └──────────────────────┘  └──────────────────────┘            │
│                        SHOULD PASS                               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  STANDARD Tests (Best Effort)                    │
│  ┌──────────────────────────────────────────────┐              │
│  │          Slow / Extended Tests                │              │
│  │          (main branch only)                   │              │
│  └──────────────────────────────────────────────┘              │
│                       BEST EFFORT                                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      E2E: Critical Paths                         │
│  ┌──────────────────────────────────────────────┐              │
│  │     Authentication, Workflows, Connectors     │              │
│  └──────────────────────────────────────────────┘              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Coverage & Quality Gate                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Codecov    │  │  PR Comment  │  │   Pass/Fail  │          │
│  │    Upload    │  │   Summary    │  │   Decision   │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

### Job Descriptions

| Job | Timeout | Trigger | Required Services |
|-----|---------|---------|-------------------|
| `critical-backend` | 15 min | Every PR | PostgreSQL, Redis |
| `critical-sdk` | 10 min | Every PR | None |
| `critical-frontend` | 10 min | Every PR | None |
| `important-integration` | 20 min | After Critical | PostgreSQL, Redis, RabbitMQ |
| `important-connectors` | 15 min | After Critical | None |
| `standard-extended` | 30 min | Main branch only | Varies |
| `e2e-critical` | 20 min | After Critical | None (uses deployed app) |
| `coverage-report` | 5 min | Always | None |
| `quality-gate` | 2 min | Always | None |

### Quality Gate Rules

The quality gate in `ci-tiered-tests.yaml` enforces:

1. **Critical tests MUST pass** - PR will be blocked if any Critical job fails
2. **Important tests SHOULD pass** - Warnings shown but not blocking
3. **Standard tests are best effort** - Only run on main branch
4. **E2E tests are informational** - Failures logged but not blocking

### Secrets Required

Configure these secrets in GitHub repository settings:

| Secret | Description |
|--------|-------------|
| `CODECOV_TOKEN` | Codecov upload token |
| `E2E_BASE_URL` | URL of test environment |
| `E2E_TEST_USER_EMAIL` | Test user credentials |
| `E2E_TEST_USER_PASSWORD` | Test user password |
| `E2E_TEST_ORG_NAME` | Test organization |

---

## Coverage Reporting

### Local Coverage Reports

```bash
# Backend - generates HTML in coverage_reports/
./scripts/run-coverage.sh all --html

# Frontend - generates HTML in frontend/coverage/
cd frontend && npm run test:coverage

# Open reports
open coverage_reports/combined/index.html    # Backend
open frontend/coverage/lcov-report/index.html  # Frontend
```

### CI Coverage Reports

Coverage is automatically:
1. Collected as artifacts from each job
2. Uploaded to Codecov for trend tracking
3. Summarized in PR comments
4. Added to GitHub job summary

### Coverage Targets by Priority

| Priority | Target | Description |
|----------|--------|-------------|
| Critical | ≥80% | Auth, core business logic, data persistence |
| Important | ≥60% | Integration points, secondary features |
| Standard | ≥40% | Utilities, admin features, edge cases |

---

## Troubleshooting

### Frontend Tests

```bash
# Clear Jest cache
cd frontend && npx jest --clearCache

# Run single test file
cd frontend && npm test -- --testPathPattern="session-store"

# Debug test
cd frontend && npm test -- --verbose --no-coverage
```

### Backend Tests

```bash
# Verbose output
pytest -v -s backend/

# Show locals on failure
pytest --tb=long backend/

# Run specific test
pytest backend/connector_v2/tests/connector_tests.py::test_specific -v
```

### E2E Tests

```bash
# Debug mode with browser visible
cd e2e && npm run test:debug

# Generate test from browser recording
cd e2e && npm run codegen

# View trace from failed test
cd e2e && npx playwright show-trace test-results/*/trace.zip
```
