#!/usr/bin/env node
/**
 * Script to check for missing translation keys in the codebase.
 * Usage: node scripts/check-translations.js
 */

const fs = require('fs');
const path = require('path');

const LOCALES_DIR = path.join(__dirname, '../src/locales');
const SRC_DIR = path.join(__dirname, '../src');

// Load translation files
function loadTranslations(lang) {
  const filePath = path.join(LOCALES_DIR, lang, 'common.json');
  const content = fs.readFileSync(filePath, 'utf-8');
  return JSON.parse(content);
}

// Extract all translation keys used in code
function extractTranslationKeysFromCode() {
  const keys = new Set();
  const codeFiles = [];

  function findTsxFiles(dir) {
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const entry of entries) {
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory() && !entry.name.includes('node_modules') && !entry.name.startsWith('.')) {
        findTsxFiles(fullPath);
      } else if (entry.isFile() && (entry.name.endsWith('.tsx') || entry.name.endsWith('.ts'))) {
        codeFiles.push(fullPath);
      }
    }
  }

  findTsxFiles(SRC_DIR);

  // Pattern to match t('namespace.key') or t("namespace.key")
  const tPattern = /t\(['"]([^'"]+)['"]\)/g;

  for (const file of codeFiles) {
    const content = fs.readFileSync(file, 'utf-8');
    let match;

    while ((match = tPattern.exec(content)) !== null) {
      keys.add(match[1]);
    }
  }

  return keys;
}

// Check if a key exists in translations
function keyExists(translations, fullKey) {
  const parts = fullKey.split('.');
  let current = translations;

  for (const part of parts) {
    if (current === undefined || current === null) {
      return false;
    }
    current = current[part];
  }

  return current !== undefined && (typeof current === 'string' || typeof current === 'object');
}

// Main function
function main() {
  console.log('🔍 Checking translations...\n');

  const enTranslations = loadTranslations('en');
  const plTranslations = loadTranslations('pl');
  const usedKeys = extractTranslationKeysFromCode();

  const missingInEn = [];
  const missingInPl = [];

  for (const key of usedKeys) {
    if (!keyExists(enTranslations, key)) {
      missingInEn.push(key);
    }
    if (!keyExists(plTranslations, key)) {
      missingInPl.push(key);
    }
  }

  // Report results
  let hasErrors = false;

  if (missingInEn.length > 0) {
    console.log('❌ Missing in English (en/common.json):');
    missingInEn.forEach(key => console.log(`   - ${key}`));
    hasErrors = true;
  }

  if (missingInPl.length > 0) {
    console.log('\n❌ Missing in Polish (pl/common.json):');
    missingInPl.forEach(key => console.log(`   - ${key}`));
    hasErrors = true;
  }

  // Check for keys that still exist only in system_update but are used in code
  const usedSystemUpdateKeys = Array.from(usedKeys).filter(k => k.startsWith('system_update.'));
  if (usedSystemUpdateKeys.length > 0) {
    console.log('\n⚠️  Still using legacy system_update namespace:');
    usedSystemUpdateKeys.forEach(key => console.log(`   - ${key}`));
    hasErrors = true;
  }

  // Summary
  console.log('\n📊 Summary:');
  const softwareUpdateKeys = Object.keys(enTranslations.software_update || {}).length;
  const deviceManagementKeys = Object.keys(enTranslations.device_management || {}).length;
  const systemUpdateKeys = Object.keys(enTranslations.system_update || {}).length;

  console.log(`   - software_update: ${softwareUpdateKeys} keys`);
  console.log(`   - device_management: ${deviceManagementKeys} keys`);
  console.log(`   - system_update (legacy): ${systemUpdateKeys} keys`);
  console.log(`   - Total keys used in code: ${usedKeys.size}`);

  if (!hasErrors) {
    console.log('\n✅ All translation keys are present!');
  } else {
    console.log('\n⚠️  Some translation keys are missing. Please fix them.');
  }

  process.exit(hasErrors ? 1 : 0);
}

main();
