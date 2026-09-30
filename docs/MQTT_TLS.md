# MQTT over TLS

Two separate things, both set up from the panel:

| | What it protects | Where |
|---|---|---|
| **boneIO → a broker** | boneIO's own connection to the broker it reports to (Home Assistant's add-on, a server, a cloud broker) | Settings → Connections → MQTT → *Encryption (TLS)* |
| **clients → the broker on this controller** | Home Assistant, other boneIO devices and apps connecting to the Mosquitto that runs on the controller | Settings → Services → Mosquitto → *Broker encryption (TLS)* |

Plain MQTT sends the username and password in the clear in the very first
packet. On a home network that is often acceptable; on a network you share,
or across a VPN, it is not.

## The broker on this controller

### Certificate

The broker needs a certificate for the names clients use to reach it — the
controller's hostname, `hostname.local`, and its IP address. Two ways to get
one:

- **Make a certificate on this controller.** One click. boneIO creates a CA,
  signs the broker's certificate with it, and throws the CA's private key
  away — nothing on the controller can vouch for anything else. Download the
  CA (`ca.crt`) from the same card and give it to your clients. The
  certificate lasts ten years. Making a new one means a new CA, which every
  client must be given again.
- **Upload your own**: the certificate, its unencrypted key, and optionally
  the CA that signed it (the panel checks that it really did, and offers it
  for download afterwards). See [Making certificates with
  openssl](#making-certificates-with-openssl) below.

The key is installed as `/etc/mosquitto/certs/boneio.key`, `root:mosquitto
0640` — readable by the broker and nobody else.

> Apple's own TLS stack (native iOS/macOS apps) refuses server certificates
> valid for more than 825 days. Home Assistant, boneIO, mosquitto_sub, MQTT
> Explorer and Node-RED are not affected. If you need such a client, upload a
> certificate made with the recipe below, which uses 825 days.

### Mode

| Mode | Port 1883 (plain) | Port 8883 (TLS) |
|---|---|---|
| Off | everyone | — |
| TLS beside plain | everyone | everyone |
| TLS only on the network | this controller only (localhost) | everyone |

*TLS beside plain* is the one to start with: move clients to 8883 one at a
time, then switch to *TLS only on the network*.

In *TLS only on the network*, boneIO keeps talking to the broker over
`localhost:1883` — the traffic never leaves the controller. The panel refuses
the switch while boneIO's own MQTT host is the controller's network address
instead of `localhost`, because it would cut itself off. **Node-RED** on the
controller reaches the broker through `host.docker.internal`, which arrives
from Docker's network, not from localhost: move its broker node to port 8883
with TLS and the CA before switching.

Every change restarts the broker, which briefly disconnects everyone. If the
broker does not come back with the new settings, the previous ones are put
back and the panel says so.

The managed configuration is `/etc/mosquitto/conf.d/boneio.conf`. If you
edited it by hand, the panel will not overwrite it and TLS cannot be managed
there until the file is back to the two lines boneIO installs:

```
listener 1883
password_file /etc/mosquitto/passwd
```

### Home Assistant

1. Download `ca.crt` from the Broker encryption card.
2. Settings → Devices & services → MQTT → *Reconfigure*.
3. Port **8883**, and under *Advanced options*: *Broker certificate
   validation* → *Custom*, upload `ca.crt`.
4. Use the controller's hostname (or `hostname.local`) as the broker address,
   exactly as it appears in the certificate's *Valid for* list.

To check from any computer:

```bash
mosquitto_sub -h boneio-1234.local -p 8883 --cafile ca.crt \
  -u homeassistant -P 'your password' -t 'boneio/#' -v
```

## boneIO as a client of another broker

On the MQTT page, turn on *Encrypt the connection (TLS)*. The port moves to
8883 if it was the default 1883. Then choose what to check the broker's
certificate against:

- **Trusted public authorities** — a broker with a certificate from Let's
  Encrypt or another public CA.
- **My own CA** — upload the CA certificate (never its key). This is what you
  want for the broker of another boneIO, or a Home Assistant add-on with a
  certificate you made.
- **Don't check** — encrypts without checking who answers. Anyone able to
  intercept the connection can pose as the broker and read the password; use
  it only to test.

A broker that requires client certificates (`require_certificate true`) also
needs a client certificate and key — the second toggle.

Uploaded files are stored in `certs/` next to `config.yaml` (the key `0600`),
and the page's Save writes their paths into `mqtt.yaml`. The same thing by
hand:

```yaml
mqtt:
  host: broker.example.lan
  port: 8883
  username: boneio
  password: !secret mqtt_password
  tls:
    enabled: true
    ca_certs: certs/mqtt-ca.pem        # omit to use the public authorities
    # certfile: certs/mqtt-client.pem  # only for require_certificate
    # keyfile: certs/mqtt-client.key
    # insecure: false                  # true skips all checks — testing only
```

Relative paths start from the directory holding `config.yaml`. If TLS is on
and cannot be set up — a missing file, a key that does not match — boneIO does
**not** connect, rather than fall back to plain text, and the MQTT page shows
why.

The `certs/` directory is not part of the configuration backup, and never of
the diagnostics bundle. After restoring a backup on another controller,
upload the files again.

## Making certificates with openssl

Run these on your own computer, in an empty folder (Linux, macOS, or Git Bash
on Windows). `ca.key` can vouch for anything you choose: keep it off the
controller and somewhere safe. The panel shows the same commands with the
controller's own names filled in.

macOS ships LibreSSL under the name `openssl`; if a command below fails
there, install OpenSSL 3 (`brew install openssl`) and use that one.

<!-- openssl-guide:start -->

**1. Your own CA** (once):

```bash
openssl req -x509 -new -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes \
  -days 3650 -subj "/CN=MQTT CA" \
  -addext "basicConstraints=critical,CA:TRUE,pathlen:0" \
  -addext "keyUsage=critical,keyCertSign,cRLSign" \
  -keyout ca.key -out ca.crt
```

**2a. The broker's certificate.** List every name and address clients use in
`subjectAltName` — the CN is ignored for hostname checks:

```bash
cat > broker.ext <<'EOF'
basicConstraints = critical, CA:FALSE
keyUsage = critical, digitalSignature
extendedKeyUsage = serverAuth
subjectAltName = DNS:boneio-1234.local, DNS:boneio-1234, IP:192.168.1.50
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid
EOF
openssl req -new -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes \
  -subj "/CN=boneio-1234.local" -keyout broker.key -out broker.csr
openssl x509 -req -in broker.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -days 825 -extfile broker.ext -out broker.crt
```

**2b. A client certificate** (only for brokers with `require_certificate`):

```bash
cat > client.ext <<'EOF'
basicConstraints = critical, CA:FALSE
keyUsage = critical, digitalSignature
extendedKeyUsage = clientAuth
subjectKeyIdentifier = hash
authorityKeyIdentifier = keyid
EOF
openssl req -new -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes \
  -subj "/CN=boneio" -keyout client.key -out client.csr
openssl x509 -req -in client.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -days 825 -extfile client.ext -out client.crt
```

**3. Check before uploading:**

```bash
openssl verify -x509_strict -CAfile ca.crt broker.crt client.crt
```

<!-- openssl-guide:end -->

Upload `broker.crt`, `broker.key` and `ca.crt` on the Broker encryption card;
give `ca.crt` to clients. For boneIO as a client, upload `ca.crt` as the CA,
and `client.crt` + `client.key` if the broker asks for one.

Why these extensions: Python 3.13 — which Home Assistant and boneIO run —
verifies strictly by default and refuses a certificate without an Authority
Key Identifier, which many older recipes leave out. (For a CA you configure
on boneIO's own connection, boneIO relaxes that one rule; Home Assistant does
not.)

## Troubleshooting

- **`certificate verify failed: Hostname mismatch`** — the client connects by
  a name or address missing from the certificate's *Valid for* list. Connect
  by one that is listed, or make a certificate that lists it. A DHCP address
  that changed is the usual cause; prefer `hostname.local`.
- **`certificate is not yet valid`** — the client's (or the controller's)
  clock is wrong. Certificates made on the controller start a day early to
  allow for this.
- **`Missing Authority Key Identifier`** — a certificate from an older recipe;
  remake it with the commands above.
- **The broker card says the configuration was edited by hand** — see
  [Mode](#mode).
- boneIO's own connection errors are in the log under `boneio.core.messaging`;
  the broker's in `journalctl -u mosquitto`; the helper's in
  `/var/log/boneio-system.log`.
