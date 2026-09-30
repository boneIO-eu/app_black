// @vitest-environment node
/// <reference types="node" />
import { execFileSync, spawnSync } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterAll, describe, expect, it } from 'vitest';
import {
  brokerCommands,
  caCommands,
  clientCommands,
  splitNames,
  subjectAltName,
  verifyCommand,
} from './openSslGuide';

const haveOpenssl = spawnSync('openssl', ['version']).status === 0;
const haveBash = spawnSync('bash', ['-c', 'true']).status === 0;

describe('splitNames', () => {
  it('sorts what the device reports into names and addresses', () => {
    expect(splitNames(['boneio', 'boneio.local', '192.168.1.50', 'boneio', ' '])).toEqual({
      dns: ['boneio', 'boneio.local'],
      ips: ['192.168.1.50'],
    });
  });

  it('writes a SAN with both kinds', () => {
    expect(subjectAltName({ dns: ['a.local'], ips: ['10.0.0.2'] })).toBe('DNS:a.local, IP:10.0.0.2');
  });

  it('never writes an empty SAN', () => {
    expect(subjectAltName({ dns: [], ips: [] })).toBe('DNS:boneio.local');
  });
});

// The text people copy is the text that runs here, through a real openssl and
// with no openssl.cnf, the way a Windows or macOS build might behave.
describe.skipIf(!haveOpenssl || !haveBash)('the recipe, run for real', () => {
  const dir = mkdtempSync(join(tmpdir(), 'boneio-openssl-'));
  afterAll(() => rmSync(dir, { recursive: true, force: true }));

  const run = (script: string) =>
    execFileSync('bash', ['-euo', 'pipefail', '-c', script], {
      cwd: dir,
      env: { ...process.env, OPENSSL_CONF: '/dev/null' },
      stdio: 'pipe',
    }).toString();

  it('makes a CA, a broker and a client certificate that pass strict verification', () => {
    const names = { dns: ['boneio-test.local', 'boneio-test'], ips: ['192.168.1.50'] };
    run(caCommands());
    run(brokerCommands(names));
    run(clientCommands());

    expect(run(verifyCommand('broker'))).toContain('broker.crt: OK');
    expect(run(verifyCommand('client'))).toContain('client.crt: OK');

    const san = run('openssl x509 -in broker.crt -noout -ext subjectAltName');
    expect(san).toContain('DNS:boneio-test.local');
    expect(san).toContain('IP Address:192.168.1.50');
    expect(run('openssl x509 -in broker.crt -noout -ext authorityKeyIdentifier')).toMatch(/[0-9A-F]{2}:/);
    expect(run('openssl x509 -in client.crt -noout -ext extendedKeyUsage')).toContain('TLS Web Client Authentication');
  });
});
