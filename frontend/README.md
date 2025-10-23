# Unstract Frontend

The Unstract frontend is built with React 18 and uses [Vite](https://vite.dev) as the build tool for fast development and optimized production builds.

**Migration Note:** This project was migrated from Create React App to Vite on 2025-10-19. See [VITE_MIGRATION.md](docs/VITE_MIGRATION.md) for details.

## Prerequisites

- **Node.js**: Version 16.x to 19.x (Node 20+ not yet supported)
- **npm**: Version 8.19.4 or higher

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/Zipstack/unstract.git
cd unstract/frontend
```

### 2. Install Dependencies

```bash
npm install
```

### 3. Configure Environment Variables

Copy the sample environment file and configure it:

```bash
cp sample.env .env
```

**Important:** All environment variables must use the `VITE_` prefix (not `REACT_APP_`):

```env
VITE_BACKEND_URL=http://frontend.unstract.localhost:8081
VITE_ENABLE_POSTHOG=false
VITE_FAVICON_PATH=/path/to/custom/favicon.ico
VITE_CUSTOM_LOGO_URL=/path/to/custom/logo.svg
```

### 4. Start Development Server

```bash
npm start
```

Or use the Vite-specific command:

```bash
npm run dev
```

The application will be available at [http://localhost:3000](http://localhost:3000).

**Hot Module Replacement (HMR)** is enabled by default - the page will automatically update when you make changes without losing component state.

## Editor Setup

### Recommended VSCode Extensions

1. **Prettier** - Code formatter: <https://marketplace.visualstudio.com/items?itemName=esbenp.prettier-vscode>
2. **ESLint** - JavaScript linter: <https://marketplace.visualstudio.com/items?itemName=dbaeumer.vscode-eslint>

## Available Scripts

### Development

#### `npm start` or `npm run dev`

Starts the Vite development server with Hot Module Replacement (HMR).

- **URL**: [http://localhost:3000](http://localhost:3000)
- **Features**:
  - Near-instant server start
  - Lightning-fast HMR (updates without full page reload)
  - On-demand compilation
  - Error overlay for build errors

#### `npm run preview`

Locally preview the production build before deployment.

- **URL**: [http://localhost:4173](http://localhost:4173)
- **Use case**: Test production build locally

### Building

#### `npm run build`

Builds the application for production to the `build/` folder.

**Build Features**:
- Optimized production bundle with tree-shaking
- Code splitting for better caching
- Minified output with hashed filenames
- Vendor chunk splitting for React, Ant Design, and PDF libraries
- Source maps generation (configurable)

**Output**: Production-ready static files in `build/` directory

### Testing

#### `npm test`

Runs tests using Vitest in watch mode.

**Features**:
- Fast test execution
- Component testing support
- Compatible with existing Jest tests
- Watch mode for development

### Linting and Formatting

The project includes ESLint and Prettier for code quality and formatting.

**Available commands:**

- `npm run lint` - Check for linting errors
- `npm run lint:fix` - Auto-fix linting errors
- `npm run prettier` - Check formatting issues
- `npm run prettier:fix` - Auto-fix formatting issues
- `npm run lint:all` - Run both ESLint and Prettier fixes on all files
- `npm run lint:changed` - Run ESLint and Prettier only on changed files

**Note:** Make sure to run `npm install` first to install the required dependencies.

## Environment Variables

Vite uses a different approach to environment variables compared to Create React App:

### Variable Naming

All custom environment variables must use the `VITE_` prefix:

```javascript
// ✅ Correct
console.log(import.meta.env.VITE_BACKEND_URL);

// ❌ Wrong (CRA style - no longer works)
console.log(process.env.REACT_APP_BACKEND_URL);
```

### Built-in Variables

Vite provides these built-in variables:

- `import.meta.env.MODE`: `'development'` or `'production'`
- `import.meta.env.DEV`: `true` in development
- `import.meta.env.PROD`: `true` in production
- `import.meta.env.BASE_URL`: Base URL of the app

### Loading Environment Files

Vite automatically loads environment files:

- `.env`: Loaded in all cases
- `.env.local`: Loaded in all cases (gitignored)
- `.env.[mode]`: Only loaded in specified mode
- `.env.[mode].local`: Only loaded in specified mode (gitignored)

**Note:** Restart the dev server after changing `.env` files.

## Configuration

### Vite Configuration

The project is configured via `vite.config.js` in the root directory:

**Key features**:
- **Proxy**: API calls to `/api` are proxied to the backend
- **HMR**: Hot Module Replacement with polling for Docker compatibility
- **Build optimization**: Manual chunk splitting for better caching
- **JSX in .js files**: esbuild configured to handle JSX syntax in `.js` files

### Proxy Configuration

Backend API calls are automatically proxied in development:

```javascript
// vite.config.js
server: {
  proxy: {
    '/api': {
      target: env.VITE_BACKEND_URL,
      changeOrigin: true,
      secure: false,
    },
  },
}
```

**Usage in code**:
```javascript
// These calls will be proxied to the backend
axios.get('/api/v1/users');
fetch('/api/v1/workflows');
```

## React Strict Mode

React Strict Mode is enabled by default in development, which:

- **Mounts components twice** to detect side effects
- Helps identify unsafe lifecycles and deprecated APIs
- Ensures components are resilient to remounting

This behavior only occurs in development and helps maintain component quality.

## Code Organization

### Static Assets

Reference static assets from the `public/` directory:

```javascript
// ✅ Correct
<img src="/images/logo.png" alt="Logo" />

// ❌ Wrong (CRA style)
<img src={`${process.env.PUBLIC_URL}/images/logo.png`} alt="Logo" />
```

### Dynamic Imports

Use dynamic imports for code splitting:

```javascript
const Dashboard = lazy(() => import('./pages/Dashboard'));
```

Vite automatically creates separate chunks for dynamically imported modules.

## Docker Development

The frontend is fully containerized for both development and production environments.

### Quick Start with Docker Compose

From the project root:

```bash
# Start all services (from repository root)
./run-platform.sh

# Or manually with docker compose
docker compose up
```

The frontend will be available at [http://frontend.unstract.localhost](http://frontend.unstract.localhost).

### Development Container

The development Dockerfile is located at `docker/dockerfiles/frontend.Dockerfile`.

**Key features**:
- Vite dev server with HMR enabled
- File watching with polling for Docker volume compatibility
- Hot reload when source files change
- Proxy configuration for backend API calls

**Environment variables for Docker**:
```bash
# Development
VITE_BACKEND_URL=http://frontend.unstract.localhost:8081
WDS_SOCKET_PORT=3000
CHOKIDAR_USEPOLLING=true
```

### Production Build

Production builds use NGINX to serve the optimized static files:

```bash
# Build production image
docker compose -f docker-compose.build.yaml build frontend

# The build process:
# 1. npm install dependencies
# 2. vite build (outputs to build/ directory)
# 3. Copy build/ to NGINX html directory
# 4. Inject runtime config script for dynamic environment variables
```

**Production build features**:
- Optimized bundle with tree-shaking
- Vendor chunk splitting (React, Ant Design, PDF libraries)
- Minified assets with content hashing
- Runtime configuration injection for dynamic environment variables

### Runtime Configuration

The frontend supports runtime environment variable injection (without rebuilding):

1. Environment variables are read from Docker environment
2. `generate-runtime-config.sh` creates `/config/runtime-config.js`
3. Script is injected into `index.html` after build
4. JavaScript reads from `window.RUNTIME_CONFIG`

**Supported runtime variables**:
- `VITE_FAVICON_PATH` / `REACT_APP_FAVICON_PATH` (backward compatibility)
- `VITE_CUSTOM_LOGO_URL` / `REACT_APP_CUSTOM_LOGO_URL` (backward compatibility)

### HMR in Docker

Hot Module Replacement works in Docker through:

1. **Polling**: File watching uses polling instead of native filesystem events
2. **Port configuration**: HMR WebSocket port matches the exposed container port
3. **Host binding**: Vite server binds to `0.0.0.0` for external access

Configuration in `vite.config.js`:
```javascript
server: {
  host: '0.0.0.0',
  port: 3000,
  watch: {
    usePolling: true,
    interval: 100,
  },
  hmr: {
    port: 3000,
    clientPort: env.WDS_SOCKET_PORT ? Number(env.WDS_SOCKET_PORT) : 3000,
  },
}
```

## Build Optimization

### Chunk Splitting Strategy

The build configuration includes intelligent chunk splitting:

**Vendor chunks**:
- `react-vendor`: React, React DOM, React Router
- `antd-vendor`: Ant Design and icons
- `pdf-vendor`: PDF viewer libraries

**Benefits**:
- Better browser caching (vendor code changes less frequently)
- Parallel download of chunks
- Smaller main bundle size

### Dependency Pre-bundling

Vite pre-bundles dependencies for faster cold starts:
- React and React DOM
- Ant Design components
- Common utility libraries

## Performance

### Vite vs Create React App

**Development server startup**:
- CRA: 10-30 seconds
- Vite: 1-2 seconds

**Hot Module Replacement**:
- CRA: 2-5 seconds
- Vite: < 1 second

**Production build**:
- CRA: 60-120 seconds
- Vite: 30-60 seconds

### Bundle Size

Optimized production build includes:
- Tree-shaking for unused code elimination
- Minification with terser
- Asset optimization
- Dynamic imports for route-based code splitting

## Troubleshooting

### Common Issues

#### Environment Variables Not Loading

**Problem**: Variables are undefined or showing default values.

**Solution**:
1. Ensure variables use `VITE_` prefix (not `REACT_APP_`)
2. Access via `import.meta.env.VITE_*` (not `process.env`)
3. Restart dev server after changing `.env` files

```javascript
// ✅ Correct
const url = import.meta.env.VITE_BACKEND_URL;

// ❌ Wrong
const url = process.env.REACT_APP_BACKEND_URL;
```

#### HMR Not Working in Docker

**Problem**: Changes to files don't trigger updates.

**Solution**:
1. Verify `CHOKIDAR_USEPOLLING=true` in `.env`
2. Check `vite.config.js` has `watch: { usePolling: true }`
3. Ensure Docker volume is properly mounted

#### Build Fails with "Cannot find module"

**Problem**: Import errors during build.

**Solution**:
1. Verify the import path is correct
2. Check if the module is installed: `npm list <package-name>`
3. Clear node_modules and reinstall: `rm -rf node_modules && npm install`
4. Clear Vite cache: `rm -rf node_modules/.vite`

#### Port Already in Use

**Problem**: Cannot start dev server, port 3000 in use.

**Solution**:
```bash
# Find process using port 3000
lsof -ti:3000

# Kill the process
kill -9 $(lsof -ti:3000)

# Or use a different port
vite --port 3001
```

### Performance Issues

If you experience slow builds or dev server:

1. **Clear Vite cache**: `rm -rf node_modules/.vite`
2. **Update dependencies**: `npm update`
3. **Check for large files** in `src/` directory
4. **Disable source maps** in `vite.config.js` (development only)

## Migration from Create React App

If you're working with older branches or need to understand the migration:

- **See**: [docs/VITE_MIGRATION.md](docs/VITE_MIGRATION.md) for comprehensive migration guide
- **Migration date**: 2025-10-19
- **Breaking changes**: Environment variables, proxy setup, SVG imports
- **Key differences**: Build tool, dev server, configuration approach

### Quick Migration Checklist

- [ ] Update all `REACT_APP_*` to `VITE_*` in `.env` files
- [ ] Replace `process.env` with `import.meta.env` in code
- [ ] Update SVG imports to use `?react` query parameter
- [ ] Remove `%PUBLIC_URL%` from HTML and use absolute paths
- [ ] Update proxy configuration if using custom setup
- [ ] Test HMR and ensure file watching works

## Learning Resources

### Vite Documentation

- [Official Vite Guide](https://vite.dev/guide/)
- [Vite Configuration Reference](https://vite.dev/config/)
- [Environment Variables in Vite](https://vite.dev/guide/env-and-mode.html)
- [Vite Build Optimizations](https://vite.dev/guide/build.html)

### React Documentation

- [React Official Docs](https://react.dev/)
- [React Router v6](https://reactrouter.com/en/main)
- [React Hooks Reference](https://react.dev/reference/react)

### Project-Specific Documentation

- [CLAUDE.md](../CLAUDE.md) - Project overview and development guidelines
- [VITE_MIGRATION.md](docs/VITE_MIGRATION.md) - Detailed migration documentation
- [Ant Design Components](https://ant.design/components/overview/) - UI component library

## Contributing

### Code Style

- Follow existing code patterns and conventions
- Run `npm run lint:all` before committing
- Ensure all tests pass: `npm test`
- Use meaningful component and variable names

### Pre-commit Hooks

The project may use pre-commit hooks for:
- ESLint validation
- Prettier formatting
- Test execution

### Pull Request Guidelines

1. Create a feature branch from `main`
2. Make your changes with clear, descriptive commits
3. Ensure all linting and tests pass
4. Update documentation if needed
5. Submit PR with detailed description

## Project Structure

```
frontend/
├── docs/                    # Documentation files
│   └── VITE_MIGRATION.md   # Vite migration guide
├── public/                  # Static assets (served as-is)
│   ├── manifest.json
│   └── robots.txt
├── src/                     # Source code
│   ├── assets/             # Images, fonts, etc.
│   ├── components/         # Reusable React components
│   ├── helpers/            # Utility functions and helpers
│   ├── pages/              # Page components
│   ├── config.js           # App configuration
│   └── index.jsx           # Application entry point
├── index.html              # HTML entry point (Vite)
├── vite.config.js          # Vite configuration
├── package.json            # Dependencies and scripts
└── .env                    # Environment variables (VITE_ prefix)
```

## Support

For questions or issues:

1. Check [VITE_MIGRATION.md](docs/VITE_MIGRATION.md) for migration-related issues
2. Review [Vite documentation](https://vite.dev) for build tool questions
3. Consult [CLAUDE.md](../CLAUDE.md) for project-specific guidelines
4. Open an issue in the project repository with detailed information

---
