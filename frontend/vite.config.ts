import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
// import basicSsl from '@vitejs/plugin-basic-ssl'

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
      // basicSsl(),
      VitePWA({
        registerType: 'autoUpdate',
        includeAssets: ['boneio.svg', 'boneio_fav.svg'],
        // Manifest is served dynamically by backend (app.py) with device name
        manifest: false,
        workbox: {
          // Monaco editor workers can be ~7MB after updates
          maximumFileSizeToCacheInBytes: 8 * 1024 * 1024,
          globPatterns: ['**/*.{js,css,html,svg,png,ico,woff2}'],
          // Exclude manifest (dynamic), Monaco chunk (~4MB), Monaco CSS,
          // workers, and ConfigEditor from precache.
          // These are loaded on-demand via runtime caching when user visits
          // the YAML editor. Precaching them forces ~6MB download on first
          // page load even if user never opens the editor.
          globIgnores: [
            '**/manifest.webmanifest',
            '**/monaco-*.js',       // Monaco editor core (~4MB)
            '**/monaco-*.css',      // Monaco editor styles
            '**/ConfigEditor-*.js', // ConfigEditor component
            '**/*.worker-*.js',     // Monaco language workers (~8MB total)
            '**/codicon-*.ttf',     // Monaco icon font
          ],
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
              // Monaco editor assets — cache on first use, serve from cache thereafter.
              // Matches: monaco-*.js, monaco-*.css, *.worker-*.js, ConfigEditor-*.js, codicon-*.ttf
              urlPattern: /\/(monaco-|ConfigEditor-|codicon-|.*\.worker-).*\.(js|css|ttf)$/,
              handler: 'CacheFirst',
              options: {
                cacheName: 'monaco-assets',
                expiration: {
                  maxEntries: 10,
                  maxAgeSeconds: 30 * 24 * 60 * 60, // 30 days
                },
              },
            },
          ],
        },
        devOptions: {
          // Off: the service worker would otherwise intercept requests on the
          // dev server too, serving a cached app shell so source edits appear
          // not to apply. The production build still ships the full PWA.
          enabled: false,
        },
      }),
    ],
    resolve: {
      // The array form, not the object form, because the dompurify entry below
      // has to be a regular expression.
      alias: [
        { find: "@", replacement: path.resolve(__dirname, "./src") },
        // monaco-yaml's worker imports Prettier unconditionally for its
        // optional "format document" provider, which only registers when
        // configureMonacoYaml() is given format.enable. boneIO never enables
        // it, so stub Prettier out and keep ~420 kB out of the YAML worker.
        { find: "prettier/standalone", replacement: path.resolve(__dirname, "./src/stubs/prettier-standalone.ts") },
        { find: "prettier/plugins/yaml", replacement: path.resolve(__dirname, "./src/stubs/prettier-plugin.ts") },
        { find: "prettier/plugins/estree", replacement: path.resolve(__dirname, "./src/stubs/prettier-plugin.ts") },
        // monaco does not import the dompurify it declares in package.json: it
        // imports a copy vendored into its own ESM tree, and on 0.55.1 that
        // copy is 3.2.7, which every open DOMPurify advisory covers. Lifting
        // the npm package (see pnpm-workspace.yaml) fixes the dependency graph
        // and silences the alerts but does not touch the sanitiser that ships,
        // so send the vendored path at the real package too. Both expose
        // exactly `export { purify as default }`, so it is a drop-in.
        //
        // It has to be a regex, and it has to match the *whole* specifier:
        // monaco imports the file relatively, as `./dompurify/dompurify.js`, so
        // an alias keyed on the package path never matches and fails silently,
        // while a regex matching only part of it leaves the unmatched half
        // behind and the build stops on `Could not load .dompurify`. That one
        // string is the only way the vendored copy is reached in the whole
        // tree, monaco-yaml included.
        //
        // scripts/check-bundled-sanitizer.cjs runs at the end of every build
        // and reads the emitted chunks, because an alias that stops matching
        // does not fail anything on its own. Drop both this entry and that
        // check once monaco vendors 3.4.13 or later.
        { find: /^\.\/dompurify\/dompurify\.js$/, replacement: "dompurify" },
      ],
    },
    build: {
      outDir: path.resolve(__dirname, '../boneio/webui/frontend-dist'),
      emptyOutDir: true,
      rollupOptions: {
        output: {
          // Name — but deliberately do NOT force — the Monaco chunk.
          //
          // A manualChunks rule for Monaco looks tempting, but it makes the
          // chunk a static dependency of the entry: the CommonJS interop helper
          // that Monaco's `marked`/`dompurify` deps share with axios lands
          // inside it, so index.js imports the chunk, index.html preloads it,
          // and all 3.6 MB downloads on every page load even though
          // ConfigEditor is React.lazy. Letting the bundler split on the
          // dynamic-import boundary and only renaming the result keeps Monaco
          // out of the entry graph while still giving the service-worker rules
          // below a "monaco-*" filename to match.
          chunkFileNames(chunk: { moduleIds?: string[] }) {
            const fromMonaco = (chunk.moduleIds ?? []).some((id) =>
              id.replace(/\\/g, '/').includes('/node_modules/monaco-editor/'),
            );
            return fromMonaco ? 'assets/monaco-[hash].js' : 'assets/[name]-[hash].js';
          },
          // Monaco's stylesheet is emitted as "editor.css", a name the
          // service-worker rules below do not recognise. Identify it by content
          // — every Monaco rule is prefixed .monaco- — rather than by a name the
          // bundler picks, and give it the monaco-* name those rules expect.
          // Binary assets (the codicon font) keep their own names.
          assetFileNames(asset: { source?: string | Uint8Array }) {
            const source = typeof asset.source === 'string' ? asset.source : '';
            return source.includes('.monaco-')
              ? 'assets/monaco-[hash][extname]'
              : 'assets/[name]-[hash][extname]';
          },
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
