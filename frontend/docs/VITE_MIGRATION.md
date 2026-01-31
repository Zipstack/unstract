# Vite Migration Guide

**Migration Date:** 2025-10-19
**From:** Create React App (react-scripts 5.0.1)
**To:** Vite 6.0.5 + @vitejs/plugin-react 4.3.4

## Overview

The Unstract frontend has been migrated from Create React App to Vite for improved development experience and build performance.

## What Changed

### 1. Build Tool & Configuration

#### Removed
- `react-scripts` dependency
- `src/setupProxy.js` (proxy configuration)
- CRA-specific eslintConfig from package.json
- Webpack and Babel dependencies

#### Added
- `vite` (v6.0.5)
- `@vitejs/plugin-react` (v4.3.4)
- `vitest` (v2.1.8) for testing
- `vite.config.js` for build configuration

### 2. File Structure Changes

```
Before (CRA):
frontend/
├── public/
│   └── index.html
├── src/
│   ├── index.js
│   └── setupProxy.js
└── package.json

After (Vite):
frontend/
├── index.html          ← Moved to root
├── public/             ← Static assets only
├── src/
│   └── index.js
├── vite.config.js      ← New config file
└── package.json
```

### 3. Environment Variables

**IMPORTANT:** All environment variables must now use the `VITE_` prefix.

#### Migration Mapping
```
REACT_APP_BACKEND_URL        → VITE_BACKEND_URL
REACT_APP_ENABLE_POSTHOG     → VITE_ENABLE_POSTHOG
REACT_APP_FAVICON_PATH       → VITE_FAVICON_PATH
REACT_APP_CUSTOM_LOGO_URL    → VITE_CUSTOM_LOGO_URL
```

#### Code Changes Required
```javascript
// Before (CRA):
const backendUrl = process.env.REACT_APP_BACKEND_URL;
const isDev = process.env.NODE_ENV === 'development';

// After (Vite):
const backendUrl = import.meta.env.VITE_BACKEND_URL;
const isDev = import.meta.env.MODE === 'development';
```

### 4. Package.json Scripts

```json
{
  "scripts": {
    "dev": "vite",                    // New: preferred dev command
    "start": "vite",                  // Updated: now runs Vite
    "build": "vite build",            // Updated: Vite build
    "preview": "vite preview",        // New: preview production build
    "test": "vitest"                  // Updated: Vitest instead of Jest
  }
}
```

### 5. HTML Entry Point

**Location:** Moved from `public/index.html` to `index.html` (root)

**Changes:**
- Removed `%PUBLIC_URL%` placeholders
- Changed `href="%PUBLIC_URL%/manifest.json"` to `href="/manifest.json"`
- Added `<script type="module" src="/src/index.js"></script>`

### 6. Proxy Configuration

**Before (setupProxy.js):**
```javascript
module.exports = (app) => {
  app.use('/api/v1', createProxyMiddleware({
    target: process.env.REACT_APP_BACKEND_URL,
    changeOrigin: true,
  }));
};
```

**After (vite.config.js):**
```javascript
export default defineConfig({
  server: {
    proxy: {
      '/api': {
        target: env.VITE_BACKEND_URL,
        changeOrigin: true,
        secure: false,
      },
    },
  },
});
```

## Docker Build Configuration

### Dockerfile Changes for Vite

The `docker/dockerfiles/frontend.Dockerfile` has been updated for Vite:

**1. Environment Variables:**
```dockerfile
# Changed from REACT_APP_ to VITE_ prefix
ENV VITE_BACKEND_URL=""
```

**2. Runtime Config Injection:**
Since Vite processes all `<script>` tags during build, the runtime config script is injected AFTER the build:

```dockerfile
# Inject runtime config script into index.html after build
RUN sed -i 's|</head>|    <script src="/config/runtime-config.js"></script>\n  </head>|' /usr/share/nginx/html/index.html
```

**3. Runtime Config Script Updated:**
The `generate-runtime-config.sh` script now supports both `VITE_` and `REACT_APP_` prefixes for backward compatibility:

```bash
window.RUNTIME_CONFIG = {
  faviconPath: "${VITE_FAVICON_PATH:-${REACT_APP_FAVICON_PATH}}",
  logoUrl: "${VITE_CUSTOM_LOGO_URL:-${REACT_APP_CUSTOM_LOGO_URL}}"
};
```

### Vite Configuration for Docker

Vite is configured to use polling for file watching, which is critical for Docker volume mounts:

```javascript
// vite.config.js
export default defineConfig({
  server: {
    watch: {
      usePolling: true,
      interval: 100,
    },
  },
});
```

### HMR Configuration

Hot Module Replacement is configured for containerized environments:

```javascript
// vite.config.js
server: {
  host: '0.0.0.0',
  port: 3000,
  hmr: {
    port: 3000,
    clientPort: env.WDS_SOCKET_PORT ? Number(env.WDS_SOCKET_PORT) : 3000,
  },
}
```

## Performance Optimizations

### Manual Chunk Splitting

Vite configuration includes optimized chunk splitting for better caching:

```javascript
build: {
  rollupOptions: {
    output: {
      manualChunks: {
        'react-vendor': ['react', 'react-dom', 'react-router-dom'],
        'antd-vendor': ['antd', '@ant-design/icons'],
        'pdf-vendor': [
          '@react-pdf-viewer/core',
          '@react-pdf-viewer/default-layout',
          '@react-pdf-viewer/highlight',
          '@react-pdf-viewer/page-navigation',
          'pdfjs-dist',
        ],
      },
    },
  },
}
```

### Dependency Pre-bundling

Common dependencies are pre-bundled for faster cold starts:

```javascript
optimizeDeps: {
  include: [
    'react',
    'react-dom',
    'react-router-dom',
    'antd',
    '@ant-design/icons',
  ],
}
```

## Migration Checklist for Developers

- [ ] Update local `.env` files to use `VITE_` prefix
- [ ] Update any custom environment variables in deployment configs
- [ ] Verify all `process.env.REACT_APP_*` references are updated to `import.meta.env.VITE_*`
- [ ] Test development server: `npm start` or `npm run dev`
- [ ] Test production build: `npm run build`
- [ ] Verify HMR works correctly in Docker environment
- [ ] Check proxy configuration for backend API calls

## Common Issues & Solutions

### Issue: Environment variables not loading

**Solution:** Ensure variables use `VITE_` prefix and are accessed via `import.meta.env`

```javascript
// ❌ Wrong
console.log(process.env.REACT_APP_BACKEND_URL);

// ✅ Correct
console.log(import.meta.env.VITE_BACKEND_URL);
```

### Issue: HMR not working in Docker

**Solution:** Verify polling is enabled in `vite.config.js` and `CHOKIDAR_USEPOLLING=true` in `.env`

### Issue: Build output directory incorrect

**Solution:** Vite outputs to `dist/` by default, but we've configured it to use `build/` to maintain compatibility:

```javascript
// vite.config.js
build: {
  outDir: 'build',
}
```

### Issue: JSX syntax errors in .js files during build

**Solution:** Configure esbuild to treat .js files as JSX:

```javascript
// vite.config.js
esbuild: {
  loader: 'jsx',
  include: /src\/.*\.jsx?$/,
}

plugins: [
  react({
    include: '**/*.{jsx,js}',
  }),
]
```

### Issue: Runtime config script causing build failure

**Problem:** Vite tries to process `<script src="/config/runtime-config.js">` during build, but the file doesn't exist at build time.

**Solution:** Remove the script tag from source `index.html` and inject it AFTER build in the Dockerfile:

```dockerfile
# In docker/dockerfiles/frontend.Dockerfile
RUN sed -i 's|</head>|    <script src="/config/runtime-config.js"></script>\n  </head>|' /usr/share/nginx/html/index.html
```

### Issue: Import errors for static assets

**Solution:** Use `/` prefix for public assets instead of `%PUBLIC_URL%`:

```javascript
// ❌ Wrong (CRA)
<img src={`${process.env.PUBLIC_URL}/logo.png`} />

// ✅ Correct (Vite)
<img src="/logo.png" />
```

## Development Commands

```bash
# Install dependencies
npm install

# Start development server
npm start
# or
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview

# Run tests
npm test

# Lint code
npm run lint

# Format code
npm run prettier:fix
```

## TypeScript Support

If migrating TypeScript code, add type definitions:

```typescript
// src/vite-env.d.ts
/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_BACKEND_URL: string
  readonly VITE_ENABLE_POSTHOG: string
  readonly VITE_FAVICON_PATH?: string
  readonly VITE_CUSTOM_LOGO_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
```

## Benefits of Vite Migration

1. **Faster Development Server**: Near-instant server start
2. **Faster HMR**: Updates reflect immediately without full reload
3. **Optimized Builds**: Better tree-shaking and code splitting
4. **Smaller Bundle Size**: Improved chunking strategies
5. **Modern Tooling**: Built on native ES modules
6. **Better Docker Support**: Reliable file watching with polling

## Resources

- [Vite Official Documentation](https://vite.dev)
- [Vite Migration Guide](https://vite.dev/guide/migration.html)
- [Environment Variables in Vite](https://vite.dev/guide/env-and-mode.html)
- [Vite Configuration Reference](https://vite.dev/config/)

## Rollback Instructions

If you need to rollback to Create React App:

1. Restore `package.json` from git history
2. Delete `vite.config.js` and `index.html` (root)
3. Restore `public/index.html` and `src/setupProxy.js`
4. Revert environment variable changes (`VITE_*` → `REACT_APP_*`)
5. Revert code changes (`import.meta.env` → `process.env`)
6. Run `npm install` to restore react-scripts

## Support

For issues or questions about the Vite migration:
- Check this migration guide first
- Review `vite.config.js` for current configuration
- Consult Vite documentation for advanced configurations
- Check project's main CLAUDE.md for overall development guidelines
