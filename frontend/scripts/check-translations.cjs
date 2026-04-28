#!/usr/bin/env node
/**
 * Translation key completeness checker.
 *
 * Scans all .tsx/.ts source files (excluding node_modules and locales)
 * for t('some.key') calls and verifies that every extracted key exists
 * in every locale JSON file (en/common.json, pl/common.json, etc.).
 *
 * Usage:
 *   node scripts/check-translations.js          # check all source files
 *   node scripts/check-translations.js --staged  # check only git-staged files
 *
 * Exit code:
 *   0 — all keys present in all locales
 *   1 — missing keys found (prints report to stderr)
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const FRONTEND_ROOT = path.resolve(__dirname, '..');
const SRC_DIR = path.join(FRONTEND_ROOT, 'src');
const LOCALES_DIR = path.join(SRC_DIR, 'locales');

// Regex that captures dot-separated keys inside t('...') or t("...")
// Handles both single and double quotes.
const T_CALL_RE = /\bt\(\s*['"]([a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)*)['"][\s,)]/g;

// Directories/files to ignore (dead code not imported anywhere).
// Relative to SRC_DIR, matched via path.includes().
const IGNORE_PATTERNS = [
  path.join('UISettings', 'sections'),
  path.join('UISettings', 'hooks', 'useSystemUpdate'),
  path.join('UISettings', 'hooks', 'useConfigBackup'),
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Recursively collect .ts / .tsx files under `dir`, skipping node_modules and locales.
 */
function collectSourceFiles(dir) {
  const results = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name === 'locales') continue;
      results.push(...collectSourceFiles(full));
    } else if (/\.(tsx?|jsx?)$/.test(entry.name)) {
      results.push(full);
    }
  }
  return results;
}

/**
 * Load and flatten a JSON translation file into a Set of dot-keys.
 * E.g. { "a": { "b": "x" } } -> Set(["a.b"])
 */
function flattenKeys(obj, prefix = '') {
  const keys = new Set();
  for (const [k, v] of Object.entries(obj)) {
    const full = prefix ? `${prefix}.${k}` : k;
    if (typeof v === 'object' && v !== null && !Array.isArray(v)) {
      for (const sub of flattenKeys(v, full)) {
        keys.add(sub);
      }
    } else {
      keys.add(full);
    }
  }
  return keys;
}

/**
 * Extract all t('key') calls from a source file string.
 * Returns an array of { key, line } objects.
 */
function extractKeys(source) {
  const results = [];
  const lines = source.split('\n');
  for (let i = 0; i < lines.length; i++) {
    let match;
    const lineRe = new RegExp(T_CALL_RE.source, 'g');
    while ((match = lineRe.exec(lines[i])) !== null) {
      results.push({ key: match[1], line: i + 1 });
    }
  }
  return results;
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

function main() {
  const stagedOnly = process.argv.includes('--staged');

  // 1. Discover all locale files
  const locales = {};
  for (const lang of fs.readdirSync(LOCALES_DIR)) {
    const jsonPath = path.join(LOCALES_DIR, lang, 'common.json');
    if (fs.existsSync(jsonPath)) {
      const data = JSON.parse(fs.readFileSync(jsonPath, 'utf-8'));
      locales[lang] = flattenKeys(data);
    }
  }
  const langNames = Object.keys(locales);
  if (langNames.length === 0) {
    console.error('❌ No locale files found!');
    process.exit(1);
  }

  // 2. Collect source files
  let files;
  if (stagedOnly) {
    // In staged mode, check if ANY frontend files are staged.
    // If so, scan ALL source files (a new t() call could reference a missing key).
    try {
      const stdout = execSync('git diff --cached --name-only --diff-filter=ACM', {
        cwd: path.resolve(FRONTEND_ROOT, '..'),
        encoding: 'utf-8',
      });
      const hasFrontendChanges = stdout
        .split('\n')
        .some(f => f.startsWith('frontend/src/'));

      if (hasFrontendChanges) {
        files = collectSourceFiles(SRC_DIR);
      } else {
        // No frontend source changes staged — nothing to check.
        files = [];
      }
    } catch {
      files = [];
    }
  } else {
    files = collectSourceFiles(SRC_DIR);
  }

  // Exclude locale files and dead code
  files = files.filter(f => {
    if (f.includes(path.join('src', 'locales'))) return false;
    for (const pattern of IGNORE_PATTERNS) {
      if (f.includes(pattern)) return false;
    }
    return true;
  });

  if (files.length === 0) {
    console.log('ℹ️  No source files to check.');
    process.exit(0);
  }

  // 3. Extract keys and check
  const missing = []; // { file, line, key, langs[] }

  for (const file of files) {
    const source = fs.readFileSync(file, 'utf-8');
    const keys = extractKeys(source);
    for (const { key, line } of keys) {
      const missingLangs = langNames.filter(lang => !locales[lang].has(key));
      if (missingLangs.length > 0) {
        const relPath = path.relative(FRONTEND_ROOT, file);
        missing.push({ file: relPath, line, key, langs: missingLangs });
      }
    }
  }

  if (missing.length === 0) {
    console.log(`✅ All translation keys found in ${langNames.join(', ')} (checked ${files.length} files).`);
    process.exit(0);
  }

  // 4. Report
  console.error(`\n❌ Found ${missing.length} missing translation key(s):\n`);

  // Group by key for cleaner output
  const byKey = new Map();
  for (const m of missing) {
    if (!byKey.has(m.key)) {
      byKey.set(m.key, { langs: m.langs, locations: [] });
    }
    byKey.get(m.key).locations.push(`${m.file}:${m.line}`);
  }

  for (const [key, { langs, locations }] of byKey) {
    console.error(`  🔑 ${key}`);
    console.error(`     Missing in: ${langs.join(', ')}`);
    for (const loc of locations) {
      console.error(`     Used at: ${loc}`);
    }
    console.error('');
  }

  console.error(`Add the missing keys to: ${langNames.map(l => `src/locales/${l}/common.json`).join(', ')}`);
  process.exit(1);
}

main();
