/**
 * The openssl commands the panel offers for making MQTT certificates.
 *
 * Kept as plain functions so the exact text shown to people is also the text
 * the tests run through a real openssl (openSslGuide.test.ts): a recipe that
 * produces a certificate Python's strict verification rejects is worse than
 * no recipe, because it looks like it worked.
 *
 * Shape choices, each one because something rejects the alternative:
 *   - an explicit Authority/Subject Key Identifier — Python 3.13 (Home
 *     Assistant, boneIO) refuses leaves without one by default;
 *   - SAN entries for every name clients use — the CN is ignored for
 *     hostname checks;
 *   - no reliance on the local openssl.cnf — Windows and macOS builds ship
 *     different ones, so every extension is spelled out.
 */

/** Names a certificate must cover. */
export interface GuideNames {
  dns: string[];
  ips: string[];
}

const IPV4 = /^\d{1,3}(\.\d{1,3}){3}$/;
const IPV6 = /^[0-9a-f:]+$/i;

/** Split addresses the device reports into DNS names and IPs. */
export function splitNames(addresses: string[]): GuideNames {
  const dns: string[] = [];
  const ips: string[] = [];
  for (const raw of addresses) {
    const value = raw.trim();
    if (!value) continue;
    const bucket = IPV4.test(value) || (value.includes(':') && IPV6.test(value)) ? ips : dns;
    if (!bucket.includes(value)) bucket.push(value);
  }
  return { dns, ips };
}

/** A SAN line for an extensions file. */
export function subjectAltName(names: GuideNames): string {
  const entries = [...names.dns.map((n) => `DNS:${n}`), ...names.ips.map((n) => `IP:${n}`)];
  return entries.length ? entries.join(', ') : 'DNS:boneio.local';
}

/** Step 1: a CA of your own, made once on your computer. */
export function caCommands(): string {
  return [
    'openssl req -x509 -new -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes \\',
    '  -days 3650 -subj "/CN=MQTT CA" \\',
    '  -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \\',
    '  -addext "keyUsage=critical,keyCertSign,cRLSign" \\',
    '  -keyout ca.key -out ca.crt',
  ].join('\n');
}

function leafCommands(stem: string, cn: string, usage: 'serverAuth' | 'clientAuth', san?: string): string {
  const ext = [
    `cat > ${stem}.ext <<'EOF'`,
    'basicConstraints = critical, CA:FALSE',
    'keyUsage = critical, digitalSignature',
    `extendedKeyUsage = ${usage}`,
    ...(san ? [`subjectAltName = ${san}`] : []),
    'subjectKeyIdentifier = hash',
    'authorityKeyIdentifier = keyid',
    'EOF',
  ];
  return [
    ...ext,
    'openssl req -new -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes \\',
    `  -subj "/CN=${cn}" -keyout ${stem}.key -out ${stem}.csr`,
    `openssl x509 -req -in ${stem}.csr -CA ca.crt -CAkey ca.key -CAcreateserial \\`,
    `  -days 825 -extfile ${stem}.ext -out ${stem}.crt`,
  ].join('\n');
}

/** Step 2 for the broker on this device: its certificate, for its names. */
export function brokerCommands(names: GuideNames): string {
  const cn = names.dns[0] ?? names.ips[0] ?? 'boneio.local';
  return leafCommands('broker', cn, 'serverAuth', subjectAltName(names));
}

/** Step 2 for boneIO as a client of a broker that asks for certificates. */
export function clientCommands(commonName = 'boneio'): string {
  return leafCommands('client', commonName, 'clientAuth');
}

/** A check worth running before uploading anything. */
export function verifyCommand(stem: 'broker' | 'client'): string {
  return `openssl verify -x509_strict -CAfile ca.crt ${stem}.crt`;
}
