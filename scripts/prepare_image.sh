#!/bin/bash
# Script to prepare different BoneIO Black image versions
# Usage: ./prepare_image.sh <mount_point> <device_type>
# Example: ./prepare_image.sh /mnt/boneio "Cover Mix"

set -e

MOUNT_POINT="$1"
DEVICE_TYPE="$2"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored messages
print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Validate arguments
if [ -z "$MOUNT_POINT" ]; then
    print_error "Mount point not provided!"
    echo "Usage: $0 <mount_point> <device_type>"
    echo "Device types: 32x10A (default), Cover, Cover Mix, 24x16A"
    exit 1
fi

if [ ! -d "$MOUNT_POINT" ]; then
    print_error "Mount point $MOUNT_POINT does not exist!"
    exit 1
fi

# Default to 32x10A if no device type specified
if [ -z "$DEVICE_TYPE" ]; then
    DEVICE_TYPE="32x10A"
    print_warning "No device type specified, using default: 32x10A"
fi

# Normalize device type
DEVICE_TYPE_NORMALIZED=$(echo "$DEVICE_TYPE" | tr '[:upper:]' '[:lower:]' | tr -d ' ')

# Map device type to config directory
case "$DEVICE_TYPE_NORMALIZED" in
    "32x10a"|"32x10"|"32")
        CONFIG_DIR="32x10"
        DEVICE_NAME="32x10A"
        ;;
    "24x16a"|"24x16"|"24")
        CONFIG_DIR="24x16"
        DEVICE_NAME="24x16A"
        ;;
    "cover")
        CONFIG_DIR="cover"
        DEVICE_NAME="Cover"
        ;;
    "covermix"|"cover_mix"|"cm")
        CONFIG_DIR="cover_mix"
        DEVICE_NAME="Cover Mix"
        ;;
    *)
        print_error "Unknown device type: $DEVICE_TYPE"
        echo "Supported types: 32x10A, 24x16A, Cover, Cover Mix"
        exit 1
        ;;
esac

print_info "Preparing BoneIO Black $DEVICE_NAME image"
print_info "Mount point: $MOUNT_POINT"
print_info "Config directory: $CONFIG_DIR"

# Find the config directory in the mounted image
# Typical paths: /home/debian/boneio/config or /opt/boneio/config
CONFIG_PATHS=(
    "$MOUNT_POINT/home/boneio/boneio"
)

TARGET_CONFIG_DIR=""
for path in "${CONFIG_PATHS[@]}"; do
    if [ -d "$path" ]; then
        TARGET_CONFIG_DIR="$path"
        print_info "Found config directory: $TARGET_CONFIG_DIR"
        break
    fi
done

if [ -z "$TARGET_CONFIG_DIR" ]; then
    print_error "Could not find boneio config directory in mounted image!"
    print_info "Searched in:"
    for path in "${CONFIG_PATHS[@]}"; do
        echo "  - $path"
    done
    exit 1
fi

# Get the script directory (where this script is located)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SOURCE_CONFIG_DIR="$PROJECT_ROOT/boneio/example_config/$CONFIG_DIR"

if [ ! -d "$SOURCE_CONFIG_DIR" ]; then
    print_error "Source config directory not found: $SOURCE_CONFIG_DIR"
    exit 1
fi

# Backup existing config
BACKUP_DIR="$TARGET_CONFIG_DIR.backup.$(date +%Y%m%d_%H%M%S)"
print_info "Creating backup: $BACKUP_DIR"
cp -r "$TARGET_CONFIG_DIR" "$BACKUP_DIR"

# Remove old YAML files to avoid conflicts with different device types
print_info "Removing old configuration files"
rm -f "$TARGET_CONFIG_DIR"/*.yaml || {
    print_error "Failed to remove old config files!"
    print_info "Restoring backup..."
    rm -rf "$TARGET_CONFIG_DIR"
    mv "$BACKUP_DIR" "$TARGET_CONFIG_DIR"
    exit 1
}

# Copy new configuration files
print_info "Copying configuration files from $SOURCE_CONFIG_DIR"
cp -v "$SOURCE_CONFIG_DIR"/*.yaml "$TARGET_CONFIG_DIR/" || {
    print_error "Failed to copy config files!"
    print_info "Restoring backup..."
    rm -rf "$TARGET_CONFIG_DIR"
    mv "$BACKUP_DIR" "$TARGET_CONFIG_DIR"
    exit 1
}

# Set proper permissions
print_info "Setting permissions"
chown -R boneio:boneio "$TARGET_CONFIG_DIR" 2>/dev/null || \
chown -R 1000:1000 "$TARGET_CONFIG_DIR" 2>/dev/null || \
print_warning "Could not set ownership (may need root privileges)"

chmod -R 644 "$TARGET_CONFIG_DIR"/*.yaml 2>/dev/null || \
print_warning "Could not set file permissions"

print_info "Configuration successfully updated!"
print_info "Device type: $DEVICE_NAME"
print_info "Backup saved to: $BACKUP_DIR"
print_info ""
print_info "Summary of changes:"
echo "  - Copied config files from: $SOURCE_CONFIG_DIR"
echo "  - Updated device type to: $DEVICE_NAME"
echo "  - Config location: $TARGET_CONFIG_DIR"
print_info ""
print_info "You can now unmount the image and flash it to the BeagleBone Black"
