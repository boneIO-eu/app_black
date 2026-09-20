#!/usr/bin/env node
/**
 * Fail the build if the DOMPurify that ships is the one monaco vendors.
 *
 * monaco-editor does not import the dompurify it declares in package.json. It
 * imports a copy vendored into its own ESM tree, and on 0.55.1 that copy is
 * 3.2.7 — a version every open DOMPurify advisory covers. vite.config.ts
 * aliases the vendored path at the real package to close that.
 *
 * The reason this check exists rather than a comment: the alias is a regex
 * against an import specifier, and when it stops matching — monaco moves the
 * file, renames it, changes the relative depth — nothing fails. The build stays
 * green, the lockfile still says 3.4.15, Dependabot still says nothing, and the
 * bundle quietly goes back to shipping 3.2.7. The only honest place to check is
 * the built output.
 *
 * The markers are string literals, so they survive minification. Identifiers do
 * not, which is why this does not look for anything like IS_ALLOWED_URI.
 */

const fs = require('fs')
const path = require('path')

const DIST = path.resolve(__dirname, '../../boneio/webui/frontend-dist/assets')

/** In 3.2.7's MathML allowlist, removed in 3.4.x. */
const STALE = 'columnsalign'
/** Added in 3.4.x. One is enough; three make a typo in any single one visible. */
const CURRENT = ['selectedcontent', 'commandfor', 'ADD_FORBID_CONTENTS']

function main() {
  if (!fs.existsSync(DIST)) {
    console.error(`✗ sanitizer check: no build output at ${DIST}`)
    process.exit(1)
  }

  const chunks = fs
    .readdirSync(DIST)
    .filter((f) => f.endsWith('.js'))
    .map((f) => ({ name: f, body: fs.readFileSync(path.join(DIST, f), 'utf8') }))

  const stale = chunks.filter((c) => c.body.includes(STALE))
  if (stale.length) {
    console.error(
      `✗ sanitizer check: the bundle ships DOMPurify 3.2.7 — monaco's vendored copy.\n` +
        `  Found "${STALE}" in: ${stale.map((c) => c.name).join(', ')}\n` +
        `  The resolve.alias for ./dompurify/dompurify.js in vite.config.ts is no\n` +
        `  longer matching. Check how monaco imports it now.`
    )
    process.exit(1)
  }

  const carrying = chunks.filter((c) => CURRENT.every((m) => c.body.includes(m)))
  if (!carrying.length) {
    console.error(
      `✗ sanitizer check: no chunk carries DOMPurify 3.4.x.\n` +
        `  Looked for ${CURRENT.map((m) => `"${m}"`).join(', ')} and found none. Either the\n` +
        `  editor is no longer bundled — in which case delete this check and the\n` +
        `  alias — or the markers are stale because dompurify moved on again.`
    )
    process.exit(1)
  }

  console.log(`✅ Bundled DOMPurify is 3.4.x (${carrying.map((c) => c.name).join(', ')}).`)
}

main()
