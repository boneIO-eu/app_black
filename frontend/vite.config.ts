import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'
import path from 'path'
import tailwindcss from "@tailwindcss/vite";
// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [
      react(),
      tailwindcss(),
      VitePWA({
        registerType: 'autoUpdate',
        includeAssets: ['boneio.svg', 'boneio_fav.svg'],
        // Manifest is served dynamically by backend (app.py) with device name
        manifest: false,
        workbox: {
          // Monaco editor workers can be ~7MB after updates
          maximumFileSizeToCacheInBytes: 8 * 1024 * 1024,
          globPatterns: ['**/*.{js,css,html,svg,png,ico,woff2}'],
          // Exclude manifest (served dynamically) and large workers (cached at runtime)
          globIgnores: ['**/manifest.webmanifest', '**/*.worker-*.js'],
          // Don't precache API calls
          navigateFallback: '/index.html',
          navigateFallbackDenylist: [/^\/api/, /^\/schema/, /^\/nodered/],
          runtimeCaching: [
            {
              urlPattern: /^\/api\//,
              handler: 'NetworkOnly',
            },
            {
              urlPattern: /^\/schema\//,
              handler: 'NetworkOnly',
            },
            {
              // Always fetch fresh manifest (dynamic device name)
              urlPattern: /\/manifest\.webmanifest$/,
              handler: 'NetworkFirst',
            },
            {
              // Monaco workers — cache on first load, serve from cache thereafter
              urlPattern: /\.worker-.*\.js$/,
              handler: 'CacheFirst',
              options: {
                cacheName: 'monaco-workers',
                expiration: {
                  maxEntries: 5,
                  maxAgeSeconds: 30 * 24 * 60 * 60, // 30 days
                },
              },
            },
          ],
        },
        devOptions: {
          enabled: true,
        },
      }),
    ],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    build: {
      outDir: path.resolve(__dirname, '../boneio/webui/frontend-dist'),
      emptyOutDir: true,
      rollupOptions: {
        output: {
          manualChunks(id: string) {
            if (id.includes('monaco-editor') || id.includes('@monaco-editor/react') || id.includes('monaco-yaml')) {
              return 'monaco';
            }
            if (id.includes('react-dom') || id.includes('react-router-dom') || id.includes('/react/')) {
              return 'vendor';
            }
          }
        }
      },
    },
    publicDir: "public",
    test: {
      environment: 'node',
      include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      proxy: {
        '/api': {
          target: env.VITE_API_URL || 'http://localhost:8090',
          changeOrigin: true,
          secure: false,
          ws: true
        },
        // '/schema': {
        //   target: env.VITE_API_URL || 'http://localhost:8090',
        //   changeOrigin: true,
        //   secure: false,
        //   ws: true
        // },
        // Node-RED proxy (requires nginx from docker/nodered to be running)
        '/nodered-status': {
          target: env.VITE_NODERED_URL || 'http://localhost:8091',
          changeOrigin: true,
          secure: false
        },
        '/nodered': {
          target: env.VITE_NODERED_URL || 'http://localhost:8091',
          changeOrigin: true,
          secure: false,
          ws: true
        }
      }
    }
  }
})
