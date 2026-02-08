#!/bin/sh
# Script for Caddy with cloud wildcard SSL certificate (PWA mode)
# This version adds a *.black.boneio.app HTTPS block using the wildcard cert
# downloaded by boneIO Cloud Registration.
#
# Used when cloud_registration is enabled in boneio config.
# Falls back to self-signed cert for hostname-based access.

HOSTNAME_FILE="/data/last_hostname"
CURRENT_HOSTNAME="${HOST_HOSTNAME:-$(cat /etc/host_hostname 2>/dev/null || hostname)}"

echo "Current hostname: $CURRENT_HOSTNAME"
echo "Cloud mode: wildcard SSL cert for *.black.boneio.app"

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

# Check if wildcard cert exists
if [ -f "/data/ssl/fullchain.pem" ] && [ -f "/data/ssl/privkey.pem" ]; then
    echo "Wildcard SSL certificate found, enabling PWA HTTPS block"
    CLOUD_BLOCK="
# HTTPS with wildcard cert for PWA (*.black.boneio.app)
*.black.boneio.app {
        tls /data/ssl/fullchain.pem /data/ssl/privkey.pem

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
                header X-NodeRed-Available \"true\"
                header Access-Control-Expose-Headers \"X-NodeRed-Available\"
                respond \`{\"available\": true}\` 200
        }

        handle /nodered/* {
                reverse_proxy node-red:1880 {
                        header_up X-Forwarded-Proto {scheme}
                        header_down X-NodeRed-Available \"true\"
                }
        }

        handle {
                reverse_proxy host.docker.internal:8090 {
                        header_up X-Forwarded-Proto {scheme}
                }
        }
}
"
else
    echo "WARNING: Wildcard SSL certificate not found at /data/ssl/"
    echo "PWA HTTPS block will not be enabled until certificate is downloaded"
    CLOUD_BLOCK=""
fi

# Generate Caddyfile
cat > /tmp/Caddyfile << EOF
{
        # Global options
}

# HTTP - serve directly
:80 {
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

# HTTPS with hostname-based self-signed certificate (always available)
https://, ${CURRENT_HOSTNAME} {
        tls internal

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

${CLOUD_BLOCK}
EOF

# Start Caddy with generated config
exec caddy run --config /tmp/Caddyfile --adapter caddyfile
