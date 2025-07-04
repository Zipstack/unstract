import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react()
  ],
  assetsInclude: ['**/*.svg'],
  esbuild: {
    loader: 'jsx',
    include: /src\/.*\.[jt]sx?$/,
    exclude: []
  },
  optimizeDeps: {
    esbuildOptions: {
      loader: {
        '.js': 'jsx',
      },
    },
  },
  server: {
    port: 3000,
    host: true,
    hmr: {
      port: 3003, // Use port 3003 for HMR to avoid conflicts
    },
    proxy: {
      // Proxy API requests to backend with error handling
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
        configure: (proxy, options) => {
          proxy.on('error', (err, req, res) => {
            console.log('Backend not available, API request failed:', req.url);
            res.writeHead(503, {
              'Content-Type': 'application/json',
              'Access-Control-Allow-Origin': '*'
            });
            res.end(JSON.stringify({ error: 'Backend server not available' }));
          });
        }
      },
      '/deployment': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
        configure: (proxy, options) => {
          proxy.on('error', (err, req, res) => {
            console.log('Backend not available, deployment request failed:', req.url);
            res.writeHead(503, {
              'Content-Type': 'application/json',
              'Access-Control-Allow-Origin': '*'
            });
            res.end(JSON.stringify({ error: 'Backend server not available' }));
          });
        }
      },
    },
  },
  build: {
    outDir: 'build',
    sourcemap: false, // Disable sourcemaps to reduce warnings
    // Optimize chunk size for better performance
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom'],
          antd: ['antd', '@ant-design/icons'],
          router: ['react-router-dom'],
          utils: ['axios', 'moment', 'uuid']
        }
      }
    }
  },
  define: {
    // Handle process.env for compatibility
    'process.env': process.env
  },
  // Handle public assets
  publicDir: 'public',
  // Set base path
  base: '/',
})
