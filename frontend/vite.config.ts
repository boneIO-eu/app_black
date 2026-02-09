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
          // Cache app shell (Monaco editor bundle is ~4MB)
          maximumFileSizeToCacheInBytes: 5 * 1024 * 1024,
          globPatterns: ['**/*.{js,css,html,svg,png,ico,woff2}'],
          // Exclude manifest - it's served dynamically by backend
          globIgnores: ['**/manifest.webmanifest'],
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
    },
    publicDir: "public",
    server: {
      proxy: {
        '/api': {
          target: env.VITE_API_URL || 'http://localhost:8090',
          changeOrigin: true,
          secure: false,
          ws: true
        },
        '/schema': {
          target: env.VITE_API_URL || 'http://localhost:8090',
          changeOrigin: true,
          secure: false,
          ws: true
        },
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
