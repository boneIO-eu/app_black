#!/bin/bash
# Helper script to mount BeagleBone Black image
# Usage: ./mount_image.sh <image_file> <mount_point>

set -e

IMAGE_FILE="$1"
MOUNT_POINT="$2"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    print_error "This script must be run as root (use sudo)"
    exit 1
fi

# Validate arguments
if [ -z "$IMAGE_FILE" ] || [ -z "$MOUNT_POINT" ]; then
    print_error "Missing arguments!"
    echo "Usage: sudo $0 <image_file> <mount_point>"
    echo "Example: sudo $0 boneio-black.img /mnt/boneio"
    exit 1
fi

if [ ! -f "$IMAGE_FILE" ]; then
    print_error "Image file not found: $IMAGE_FILE"
    exit 1
fi

# Create mount point if it doesn't exist
if [ ! -d "$MOUNT_POINT" ]; then
    print_info "Creating mount point: $MOUNT_POINT"
    mkdir -p "$MOUNT_POINT"
fi

# Check if already mounted
if mountpoint -q "$MOUNT_POINT"; then
    print_warning "Mount point $MOUNT_POINT is already in use!"
    echo "Do you want to unmount it first? (y/n)"
    read -r response
    if [ "$response" = "y" ]; then
        print_info "Unmounting $MOUNT_POINT"
        umount "$MOUNT_POINT"
    else
        exit 1
    fi
fi

# Find the loop device
print_info "Setting up loop device for $IMAGE_FILE"
LOOP_DEVICE=$(losetup -f)
losetup -P "$LOOP_DEVICE" "$IMAGE_FILE"

print_info "Loop device: $LOOP_DEVICE"

# List partitions
print_info "Available partitions:"
lsblk "$LOOP_DEVICE"

# Try to find the rootfs partition by filesystem type
# Look for ext4 partition (skip boot/FAT and swap partitions)
print_info "Detecting rootfs partition..."
ROOTFS_PARTITION=""

# Try each partition and check filesystem type
for part in "${LOOP_DEVICE}p"*; do
    if [ -e "$part" ]; then
        FS_TYPE=$(blkid -s TYPE -o value "$part" 2>/dev/null || echo "unknown")
        print_info "Partition $part: $FS_TYPE"
        
        # Look for ext4 filesystem (typical for rootfs)
        if [ "$FS_TYPE" = "ext4" ] || [ "$FS_TYPE" = "ext3" ]; then
            ROOTFS_PARTITION="$part"
            print_info "Found rootfs partition: $ROOTFS_PARTITION ($FS_TYPE)"
            break
        fi
    fi
done

# Fallback: if no ext4 found, try largest partition (skip first boot partition)
if [ -z "$ROOTFS_PARTITION" ]; then
    print_warning "No ext4 partition found, trying largest partition..."
    if [ -e "${LOOP_DEVICE}p3" ]; then
        ROOTFS_PARTITION="${LOOP_DEVICE}p3"
    elif [ -e "${LOOP_DEVICE}p2" ]; then
        ROOTFS_PARTITION="${LOOP_DEVICE}p2"
    elif [ -e "${LOOP_DEVICE}p1" ]; then
        ROOTFS_PARTITION="${LOOP_DEVICE}p1"
    fi
fi

if [ -z "$ROOTFS_PARTITION" ]; then
    print_error "Could not find rootfs partition!"
    losetup -d "$LOOP_DEVICE"
    exit 1
fi

print_info "Mounting rootfs partition: $ROOTFS_PARTITION"
mount "$ROOTFS_PARTITION" "$MOUNT_POINT"

print_info "Image successfully mounted!"
print_info "Mount point: $MOUNT_POINT"
print_info "Loop device: $LOOP_DEVICE"
print_info ""
print_info "To prepare the image for a specific device type, run:"
echo "  ./prepare_image.sh $MOUNT_POINT <device_type>"
echo ""
print_info "When done, unmount with:"
echo "  sudo umount $MOUNT_POINT"
echo "  sudo losetup -d $LOOP_DEVICE"
