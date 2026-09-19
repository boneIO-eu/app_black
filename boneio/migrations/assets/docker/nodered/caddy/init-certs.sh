#!/bin/sh
# Caddy init script for non-cloud mode (self-signed HTTPS only).
# Generates a Caddyfile with HTTP and self-signed HTTPS reverse proxy
# for boneIO and Node-RED.

HOSTNAME_FILE="/data/last_hostname"
CURRENT_HOSTNAME="${HOST_HOSTNAME:-$(cat /etc/host_hostname 2>/dev/null || hostname)}"

echo "Current hostname: $CURRENT_HOSTNAME"
echo "Mode: local (self-signed HTTPS)"

# Check if hostname changed (for self-signed cert regeneration)
if [ -f "$HOSTNAME_FILE" ]; then
    LAST_HOSTNAME=$(cat "$HOSTNAME_FILE")
    if [ "$LAST_HOSTNAME" != "$CURRENT_HOSTNAME" ]; then
        echo "Hostname changed from $LAST_HOSTNAME to $CURRENT_HOSTNAME"
        echo "Removing old self-signed certificates..."
        rm -rf /data/caddy/certificates/local/*
        rm -rf /data/caddy/pki/*
        rm -rf /config/caddy/*
    fi
else
    echo "First run on this device, clearing any existing certificates..."
    rm -rf /data/caddy/certificates/local/*
    rm -rf /data/caddy/pki/*
    rm -rf /config/caddy/*
fi

echo "$CURRENT_HOSTNAME" > "$HOSTNAME_FILE"

# Which certificate to serve.
#
# An operator who does not want cloud registration can upload their own, and
# it is read from Caddy's data directory, which is already mounted. Anything
# else falls back to
# Caddy's own authority, issuing on demand: the device's address is not known
# here and changes with the lease, so there is no fixed name to ask for.
CUSTOM_CERT=/data/custom/fullchain.pem
CUSTOM_KEY=/data/custom/privkey.pem
if [ -f "$CUSTOM_CERT" ] && [ -f "$CUSTOM_KEY" ]; then
        echo "Serving the uploaded certificate from $CUSTOM_CERT"
        TLS_DIRECTIVE="tls $CUSTOM_CERT $CUSTOM_KEY"
else
        echo "Serving Caddy's own certificate (no uploaded one found)"
        TLS_DIRECTIVE="tls {
                issuer internal {
                        lifetime 180d
                }
                on_demand
        }"
fi

# Generate Caddyfile
cat > /tmp/Caddyfile << EOF
{
        # The device's own certificate authority issues for six months rather
        # than the twelve hours Caddy defaults to. Nobody trusts this authority
        # until they choose to, and when they do — by installing the root on
        # their own machines, or by clicking through once — a certificate that
        # expires the same evening undoes that daily. The intermediate has to
        # outlive the leaves it signs, or Caddy refuses to start.
        pki {
                ca local {
                        intermediate_lifetime 365d
                }
        }
}

# HTTP — redirect to HTTPS.
#
# This port used to serve the panel in the clear: the login form, the token it
# hands back and a configuration carrying passwords, all readable by anyone on
# the network. Nothing is served here now.
#
# The port comes from the environment, substituted by this shell as the file is
# written. Caddy only ever sees 443 from inside the container; the host
# publishes it as 8443, so a redirect built from the inside view would send
# browsers to a port where nothing is listening.
:80 {
        redir https://{host}:${PUBLIC_HTTPS_PORT:-8443}{uri}
}

# HTTPS with self-signed certificate (catch-all for hostname and IP access)
https:// {
        ${TLS_DIRECTIVE}

        handle_errors {
                @502-504 expression {err.status_code} >= 502 && {err.status_code} <= 504
                handle @502-504 {
                        root * /srv
                        rewrite * /502.html
                        file_server
                }
        }

        handle /nodered-status {
                header Content-Type application/json
                header X-NodeRed-Available "true"
                header Access-Control-Expose-Headers "X-NodeRed-Available"
                respond \`{"available": true}\` 200
        }

        handle /nodered/* {
                reverse_proxy node-red:1880 {
                        header_up X-Forwarded-Proto {scheme}
                        header_down X-NodeRed-Available "true"
                }
        }

        handle {
                reverse_proxy host.docker.internal:8090 {
                        header_up X-Forwarded-Proto {scheme}
                }
        }
}
EOF

# Start Caddy with generated config
exec caddy run --config /tmp/Caddyfile --adapter caddyfile
