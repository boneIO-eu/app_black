#!/usr/bin/env node
/**
 * Translation key completeness checker.
 *
 * Two passes, because keys reach t() in two different shapes.
 *
 * 1. Static keys. Scans all .tsx/.ts source files (excluding node_modules and
 *    locales) for t('some.key') calls and verifies that every extracted key
 *    exists in every locale JSON file (en/common.json, pl/common.json, etc.).
 *
 * 2. Section keys. SectionHeader and UISettings build their labels and help
 *    text at runtime — t(`sections.descriptions.${sectionName}`) — so pass 1
 *    is blind to them; that is how sections.descriptions.location reached the
 *    screen as a raw key. The section list is read from sectionDefinitions.ts
 *    and every section is required to have both a label and a description.
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

// The one place that knows which settings sections exist.
const SECTION_DEFS_FILE = path.join(
  SRC_DIR, 'components', 'UISettings', 'constants', 'sectionDefinitions.ts'
);

// Captures the section name out of `translationKey: 'sections.<name>'`.
const SECTION_DEF_RE = /translationKey:\s*['"]sections\.([a-zA-Z0-9_]+)['"]/g;

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

/**
 * Names of the settings sections the editor actually renders.
 *
 * Read from sectionDefinitions.ts rather than from the locale files, so that a
 * section added in code without translations fails, and a translation left
 * behind for a removed section does not.
 */
function collectSectionNames() {
  if (!fs.existsSync(SECTION_DEFS_FILE)) return [];
  const source = fs.readFileSync(SECTION_DEFS_FILE, 'utf-8');
  const names = new Set();
  let match;
  const re = new RegExp(SECTION_DEF_RE.source, 'g');
  while ((match = re.exec(source)) !== null) {
    names.add(match[1]);
  }
  return [...names];
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

  // 3. Pass 1 — static t('a.b') calls
  const missing = []; // { file, line, key, langs[] }
  const usedKeys = new Set();

  for (const file of files) {
    const source = fs.readFileSync(file, 'utf-8');
    const keys = extractKeys(source);
    for (const { key, line } of keys) {
      usedKeys.add(key);
      const missingLangs = langNames.filter(lang => !locales[lang].has(key));
      if (missingLangs.length > 0) {
        const relPath = path.relative(FRONTEND_ROOT, file);
        missing.push({ file: relPath, line, key, langs: missingLangs });
      }
    }
  }

  // 4. Pass 2 — sections, whose keys are assembled at runtime
  const sectionNames = collectSectionNames();
  const sectionMissing = []; // { key, langs[], section }

  for (const name of sectionNames) {
    for (const key of [`sections.${name}`, `sections.descriptions.${name}`]) {
      const langs = langNames.filter(lang => !locales[lang].has(key));
      if (langs.length > 0) {
        sectionMissing.push({ key, langs, section: name });
      }
    }
  }

  // Translations for sections nobody renders any more. A warning, not an
  // error: some of these (binary_sensor, event, lox_udp) belong to composite
  // sections and are reached through a static t() call, which pass 1 covers.
  const orphans = [];
  for (const key of locales[langNames[0]]) {
    if (!key.startsWith('sections.')) continue;
    if (usedKeys.has(key)) continue;
    const name = key.startsWith('sections.descriptions.')
      ? key.slice('sections.descriptions.'.length)
      : key.slice('sections.'.length);
    if (name.includes('.')) continue;
    if (!sectionNames.includes(name)) orphans.push(key);
  }

  // 5. Report
  if (orphans.length > 0) {
    console.warn(`\n⚠️  ${orphans.length} translation(s) for section(s) that no longer exist:`);
    for (const key of orphans) console.warn(`     ${key}`);
    console.warn('   Remove them, or add the section back to sectionDefinitions.ts.\n');
  }

  if (missing.length === 0 && sectionMissing.length === 0) {
    console.log(
      `✅ All translation keys found in ${langNames.join(', ')} ` +
      `(checked ${files.length} files, ${sectionNames.length} sections).`
    );
    process.exit(0);
  }

  if (missing.length > 0) {
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
  }

  if (sectionMissing.length > 0) {
    console.error(`\n❌ Found ${sectionMissing.length} missing section translation(s):\n`);
    for (const { key, langs, section } of sectionMissing) {
      console.error(`  🔑 ${key}`);
      console.error(`     Missing in: ${langs.join(', ')}`);
      console.error(`     Built at runtime for section '${section}' (sectionDefinitions.ts)`);
      console.error('');
    }
  }

  console.error(`Add the missing keys to: ${langNames.map(l => `src/locales/${l}/common.json`).join(', ')}`);
  process.exit(1);
}

main();
