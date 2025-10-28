#!/bin/bash

# BoneIO Remote Dev Container Setup Script
# Automatyczna konfiguracja Docker i środowiska na BeagleBone Black

set -e

echo "🚀 BoneIO Remote Dev Container Setup"
echo "======================================"

# Sprawdź czy jesteśmy na BeagleBone Black
if ! grep -q "BeagleBone" /proc/cpuinfo 2>/dev/null; then
    echo "⚠️  Warning: This script is designed for BeagleBone Black"
    echo "   Continuing anyway..."
fi

# Sprawdź architekturę
ARCH=$(uname -m)
echo "📋 Architecture: $ARCH"

if [[ "$ARCH" != "armv7l" ]]; then
    echo "⚠️  Warning: Expected armv7l, got $ARCH"
fi

# Sprawdź system operacyjny
if ! grep -q "Debian" /etc/os-release; then
    echo "❌ Error: This script requires Debian"
    exit 1
fi

echo "✅ Debian detected"

# Aktualizuj system
echo "📦 Updating system packages..."
sudo apt update
sudo apt upgrade -y

# Instaluj Docker
echo "🐳 Installing Docker..."
if ! command -v docker &> /dev/null; then
    sudo apt install -y docker.io docker-compose
    echo "✅ Docker installed"
else
    echo "✅ Docker already installed"
fi

# Konfiguruj Docker
echo "🔧 Configuring Docker..."
sudo systemctl enable docker
sudo systemctl start docker

# Dodaj użytkownika do grupy docker
echo "👤 Adding user to docker group..."
sudo usermod -aG docker $USER

# Dodaj użytkownika do grup hardware
echo "🔌 Adding user to hardware groups..."
sudo usermod -a -G i2c,gpio $USER

# Sprawdź dostępność urządzeń I2C/GPIO
echo "🔍 Checking hardware devices..."

if [ -e /dev/i2c-2 ]; then
    echo "✅ I2C-2 device found"
    sudo chmod 666 /dev/i2c-2
else
    echo "⚠️  I2C-2 device not found"
    echo "   You may need to enable I2C in device tree"
fi

if [ -e /dev/gpiochip0 ]; then
    echo "✅ GPIO device found"
    sudo chmod 666 /dev/gpiochip0
else
    echo "⚠️  GPIO device not found"
fi

# Sprawdź czy SSH jest włączony
echo "🔐 Checking SSH server..."
if systemctl is-active --quiet ssh; then
    echo "✅ SSH server is running"
else
    echo "⚠️  SSH server not running"
    echo "   Installing and starting SSH server..."
    sudo apt install -y openssh-server
    sudo systemctl enable ssh
    sudo systemctl start ssh
fi

# Pobierz IP adres
IP=$(hostname -I | awk '{print $1}')
echo "🌐 BeagleBone IP address: $IP"

# Test Docker
echo "🧪 Testing Docker..."
if sudo docker run --rm hello-world > /dev/null 2>&1; then
    echo "✅ Docker test successful"
else
    echo "❌ Docker test failed"
    exit 1
fi

# Sprawdź czy projekt BoneIO istnieje
if [ -d "/home/$USER/ProjektyPrywatne/bone/app_black" ]; then
    echo "✅ BoneIO project found"
    PROJECT_PATH="/home/$USER/ProjektyPrywatne/bone/app_black"
else
    echo "⚠️  BoneIO project not found in expected location"
    echo "   Please clone the project first"
    PROJECT_PATH=""
fi

# Stwórz skrypt konfiguracyjny SSH
echo "📝 Creating SSH configuration template..."
cat > ~/ssh_config_template.txt << EOF
# Add this to your ~/.ssh/config file on your local machine:

Host beaglebone
    HostName $IP
    User $USER
    Port 22
    ServerAliveInterval 60
    ServerAliveCountMax 3
EOF

echo ""
echo "🎉 Setup completed successfully!"
echo ""
echo "📋 Next steps:"
echo "1. Logout and login again to apply group changes"
echo "2. On your local machine, add the SSH config from ~/ssh_config_template.txt"
echo "3. Install VS Code extensions: Remote-SSH, Dev Containers"
echo "4. Connect to BeagleBone via VS Code Remote-SSH"
echo "5. Open the BoneIO project folder"
echo "6. Reopen in Dev Container"
echo ""
echo "🔧 Useful commands:"
echo "- Check Docker: docker --version"
echo "- Check groups: groups"
echo "- Check I2C: ls -la /dev/i2c-*"
echo "- Check GPIO: ls -la /dev/gpiochip*"
echo "- SSH config: cat ~/ssh_config_template.txt"
echo ""
echo "⚠️  Important:"
echo "- You need to logout/login for group changes to take effect"
echo "- Make sure your local machine can SSH to this BeagleBone"
echo "- The dev container will take 5-10 minutes to build on first run"
echo ""
echo "🐛 Troubleshooting:"
echo "- If Docker permission denied: logout/login or 'newgrp docker'"
echo "- If I2C not found: check device tree overlays"
echo "- If SSH fails: check firewall and network"
