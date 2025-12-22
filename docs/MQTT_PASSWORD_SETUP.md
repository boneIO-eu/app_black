# MQTT Password Management Setup

## Overview

BoneIO WebUI now supports changing MQTT passwords for three users:
- `boneio` - Main BoneIO application user
- `homeassistant` - Home Assistant integration user
- `mqtt` - General MQTT user

## Installation Steps

### 1. Install Mosquitto (if not already installed)

```bash
sudo apt-get update
sudo apt-get install mosquitto mosquitto-clients
```

### 2. Create initial MQTT users

```bash
# Create password file and add users
sudo mosquitto_passwd -c /etc/mosquitto/passwd boneio
sudo mosquitto_passwd -b /etc/mosquitto/passwd homeassistant your_password_here
sudo mosquitto_passwd -b /etc/mosquitto/passwd mqtt your_password_here
```

### 3. Configure Mosquitto to use password file

Edit `/etc/mosquitto/mosquitto.conf`:

```conf
# Add these lines
password_file /etc/mosquitto/passwd
allow_anonymous false
```

Restart Mosquitto:

```bash
sudo systemctl restart mosquitto
```

### 4. Setup sudo permissions for boneio user

Copy the sudoers file:

```bash
sudo cp boneio/sudoers.d/boneio-mosquitto /etc/sudoers.d/
sudo chmod 0440 /etc/sudoers.d/boneio-mosquitto
```

Verify the configuration:

```bash
sudo visudo -c
```

### 5. Test the setup

Try changing a password from command line:

```bash
sudo mosquitto_passwd -b /etc/mosquitto/passwd boneio new_password
sudo systemctl reload mosquitto
```

## Usage in WebUI

1. Navigate to **Settings → System**
2. Scroll to **MQTT Passwords** section
3. Select user (boneio, homeassistant, or mqtt)
4. Enter new password and confirm
5. Click **Change Password**

## Security Considerations

### ⚠️ HTTP Warning

The WebUI shows a warning if you're using HTTP instead of HTTPS:

- **HTTP (not secure)**: Passwords are sent in plain text over the network
  - ✅ Safe in local network (192.168.x.x)
  - ❌ **NEVER** use over internet without VPN

- **HTTPS (secure)**: Passwords are encrypted
  - ✅ Safe for internet access
  - ✅ Safe for local network

### Setting up HTTPS (recommended for internet access)

Use nginx or caddy as reverse proxy with Let's Encrypt:

```bash
# Example with nginx
sudo apt-get install nginx certbot python3-certbot-nginx

# Get certificate
sudo certbot --nginx -d your-domain.com

# Configure nginx to proxy to BoneIO
# Edit /etc/nginx/sites-available/boneio
```

### Firewall Configuration (for local-only access)

```bash
# Allow only local network access to port 8091
sudo ufw allow from 192.168.0.0/16 to any port 8091
sudo ufw deny 8091
```

## Troubleshooting

### "mosquitto_passwd command not found"

Install mosquitto:
```bash
sudo apt-get install mosquitto
```

### "Permission denied"

Check sudo configuration:
```bash
sudo visudo -c
cat /etc/sudoers.d/boneio-mosquitto
```

### "Failed to reload mosquitto service"

Check mosquitto status:
```bash
sudo systemctl status mosquitto
sudo journalctl -u mosquitto -n 50
```

### Password change succeeds but MQTT still uses old password

Reload mosquitto manually:
```bash
sudo systemctl reload mosquitto
```

## API Endpoint

The password change endpoint is available at:

```
POST /api/mqtt/change_password
Content-Type: application/json

{
  "username": "boneio",
  "new_password": "your_new_password"
}
```

Response:
```json
{
  "status": "success",
  "message": "Password changed successfully for user: boneio"
}
```

## Password Requirements

- Minimum length: 8 characters
- No maximum length
- All characters allowed
- Passwords must match in confirmation field
