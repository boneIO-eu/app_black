import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import tailwindcss from "@tailwindcss/vite";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [react(), tailwindcss()],
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
