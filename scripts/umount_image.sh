#!/bin/bash
# Helper script to unmount BeagleBone Black image
# Usage: ./umount_image.sh <mount_point>

set -e

MOUNT_POINT="$1"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    print_error "This script must be run as root (use sudo)"
    exit 1
fi

# Validate arguments
if [ -z "$MOUNT_POINT" ]; then
    print_error "Mount point not provided!"
    echo "Usage: sudo $0 <mount_point>"
    echo "Example: sudo $0 /mnt/boneio"
    exit 1
fi

if [ ! -d "$MOUNT_POINT" ]; then
    print_error "Mount point does not exist: $MOUNT_POINT"
    exit 1
fi

# Check if mounted
if ! mountpoint -q "$MOUNT_POINT"; then
    print_error "$MOUNT_POINT is not mounted!"
    exit 1
fi

# Find the loop device
LOOP_DEVICE=$(findmnt -n -o SOURCE "$MOUNT_POINT" | sed 's/p[0-9]*$//')

print_info "Unmounting $MOUNT_POINT"
umount "$MOUNT_POINT"

if [ -n "$LOOP_DEVICE" ] && [ -e "$LOOP_DEVICE" ]; then
    print_info "Detaching loop device: $LOOP_DEVICE"
    losetup -d "$LOOP_DEVICE"
fi

print_info "Image successfully unmounted!"
print_info "You can now flash the image to BeagleBone Black"
