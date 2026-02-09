#!/bin/sh
# Script to regenerate Caddy certificates when hostname changes
# This ensures each device gets its own valid certificate

HOSTNAME_FILE="/data/last_hostname"
# Read hostname from host's /etc/hostname (mounted as /etc/host_hostname)
CURRENT_HOSTNAME="${HOST_HOSTNAME:-$(cat /etc/host_hostname 2>/dev/null || hostname)}"

echo "Current hostname: $CURRENT_HOSTNAME"

# Check if hostname changed
if [ -f "$HOSTNAME_FILE" ]; then
    LAST_HOSTNAME=$(cat "$HOSTNAME_FILE")
    if [ "$LAST_HOSTNAME" != "$CURRENT_HOSTNAME" ]; then
        echo "Hostname changed from $LAST_HOSTNAME to $CURRENT_HOSTNAME"
        echo "Removing old certificates..."
        rm -rf /data/caddy/certificates/*
        rm -rf /data/caddy/pki/*
        rm -rf /config/caddy/*
    fi
else
    echo "First run on this device, clearing any existing certificates..."
    rm -rf /data/caddy/certificates/*
    rm -rf /data/caddy/pki/*
    rm -rf /config/caddy/*
fi

# Save current hostname
echo "$CURRENT_HOSTNAME" > "$HOSTNAME_FILE"

# Generate Caddyfile with actual hostname
cat > /tmp/Caddyfile << EOF
{
        # Global options - empty for internal issuer
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

# HTTPS with self-signed certificate (catch-all for hostname and IP access)
https:// {
        tls internal {
                on_demand
        }

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
