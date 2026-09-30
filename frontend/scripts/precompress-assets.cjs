#!/usr/bin/env node
/**
 * Write a gzip copy next to every compressible file in frontend-dist/assets.
 *
 * The controller serves these as they are (boneio/webui/static_assets.py)
 * instead of compressing each bundle on every request, which on a BeagleBone
 * took longer than sending it uncompressed. Done once here, at level 9, on a
 * machine with CPU to spare.
 *
 * A copy that would not come out smaller is not written: the plain file is
 * then served, and nothing is lost.
 */
const fs = require('fs');
const path = require('path');
const zlib = require('zlib');

const ASSETS = path.resolve(__dirname, '../../boneio/webui/frontend-dist/assets');
const COMPRESSIBLE = new Set(['.js', '.css', '.svg', '.json', '.ttf', '.html', '.txt', '.map']);
const MIN_BYTES = 1024;

if (!fs.existsSync(ASSETS)) {
  console.error(`precompress: ${ASSETS} does not exist — run vite build first`);
  process.exit(1);
}

let written = 0;
let before = 0;
let after = 0;
for (const name of fs.readdirSync(ASSETS)) {
  const file = path.join(ASSETS, name);
  if (!COMPRESSIBLE.has(path.extname(name)) || !fs.statSync(file).isFile()) continue;
  const raw = fs.readFileSync(file);
  if (raw.length < MIN_BYTES) continue;
  const gz = zlib.gzipSync(raw, { level: 9 });
  if (gz.length >= raw.length) continue;
  fs.writeFileSync(`${file}.gz`, gz);
  written += 1;
  before += raw.length;
  after += gz.length;
}

const kb = (n) => `${Math.round(n / 1024)} KiB`;
console.log(`precompress: ${written} files, ${kb(before)} → ${kb(after)} gzip`);
