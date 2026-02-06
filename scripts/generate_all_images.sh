#!/bin/bash
# OLD for new look at https://github.com/boneIO-eu/black_debian_images
# Script to generate all BoneIO Black image variants from a source image
# Usage: ./generate_all_images.sh <source_image.img> [version]
# Example: ./generate_all_images.sh BLACK_DEBIAN13_K6.18_APK_V1.0.1_32x10A_SDCARD.img 1.0.1

set -e

SOURCE_IMAGE="$1"
VERSION="${2:-1.0.1}"

# Get the actual user who invoked sudo (if any)
ACTUAL_USER="${SUDO_USER:-$USER}"
ACTUAL_UID="${SUDO_UID:-$(id -u)}"
ACTUAL_GID="${SUDO_GID:-$(id -g)}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

# Check if script is run with sudo/root privileges
if [[ $EUID -ne 0 ]]; then
    print_error "This script must be run with sudo privileges!"
    echo "Usage: sudo $0 <source_image.img> [version]"
    exit 1
fi

# Validate arguments
if [ -z "$SOURCE_IMAGE" ]; then
    print_error "Source image not provided!"
    echo "Usage: sudo $0 <source_image.img> [version]"
    echo "Example: sudo $0 BLACK_DEBIAN13_K6.18_APK_V1.0.1_32x10A_SDCARD.img 1.0.1"
    exit 1
fi

if [ ! -f "$SOURCE_IMAGE" ]; then
    print_error "Source image $SOURCE_IMAGE does not exist!"
    exit 1
fi

# Get script directory (where prepare_image.sh is located)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREPARE_SCRIPT="$SCRIPT_DIR/prepare_image.sh"

if [ ! -f "$PREPARE_SCRIPT" ]; then
    print_error "prepare_image.sh not found in $SCRIPT_DIR"
    exit 1
fi

# Mount point
MOUNT_POINT="/mnt/boneio_image"
mkdir -p "$MOUNT_POINT"

# Device types to generate
declare -A DEVICE_TYPES=(
    ["32x10A"]="32x10"
    ["24x16A"]="24x16"
    ["Cover"]="cover"
    ["Cover_Mix"]="cover_mix"
)

# Output directory (same as source image)
OUTPUT_DIR="$(dirname "$(realpath "$SOURCE_IMAGE")")"

# Base name for images
BASE_NAME="BLACK_DEBIAN13_K6.18_APK_V${VERSION}"

# Function to mount image
mount_image() {
    local img_file="$1"
    
    print_info "Setting up loop device for $img_file..."
    LOOP_DEVICE=$(losetup -fP --show "$img_file")
    
    if [ -z "$LOOP_DEVICE" ]; then
        print_error "Failed to create loop device!"
        return 1
    fi
    
    print_info "Loop device: $LOOP_DEVICE"
    
    # Wait for partitions to appear
    sleep 1
    partprobe "$LOOP_DEVICE" 2>/dev/null || true
    sleep 1
    
    # Find rootfs partition (ext4)
    ROOTFS_PARTITION=""
    for part in "${LOOP_DEVICE}p"*; do
        if [ -e "$part" ]; then
            FS_TYPE=$(blkid -s TYPE -o value "$part" 2>/dev/null || echo "unknown")
            if [ "$FS_TYPE" = "ext4" ] || [ "$FS_TYPE" = "ext3" ]; then
                ROOTFS_PARTITION="$part"
                print_info "Found rootfs partition: $ROOTFS_PARTITION ($FS_TYPE)"
                break
            fi
        fi
    done
    
    if [ -z "$ROOTFS_PARTITION" ]; then
        print_error "Could not find rootfs partition!"
        losetup -d "$LOOP_DEVICE"
        return 1
    fi
    
    # Mount rootfs
    print_info "Mounting rootfs..."
    mount "$ROOTFS_PARTITION" "$MOUNT_POINT"
    
    return 0
}

# Function to unmount image
unmount_image() {
    print_info "Unmounting image..."
    
    # Sync to ensure all writes are complete
    sync
    
    # Unmount boot if mounted
    umount "$MOUNT_POINT/boot" 2>/dev/null || true
    
    # Unmount rootfs
    umount "$MOUNT_POINT" 2>/dev/null || true
    
    # Detach loop device
    if [ -n "$LOOP_DEVICE" ]; then
        losetup -d "$LOOP_DEVICE" 2>/dev/null || true
    fi
    
    LOOP_DEVICE=""
}

# Function to enable flasher mode in uEnv.txt
enable_flasher_mode() {
    local uenv_file="$MOUNT_POINT/boot/uEnv.txt"
    
    if [ ! -f "$uenv_file" ]; then
        print_error "uEnv.txt not found at $uenv_file"
        return 1
    fi
    
    print_info "Enabling flasher mode in uEnv.txt..."
    
    # Uncomment the flasher line
    sed -i 's/^#cmdline=init=\/usr\/sbin\/init-beagle-flasher/cmdline=init=\/usr\/sbin\/init-beagle-flasher/' "$uenv_file"
    
    # Verify the change
    if grep -q "^cmdline=init=/usr/sbin/init-beagle-flasher" "$uenv_file"; then
        print_info "Flasher mode enabled successfully"
    else
        print_warning "Could not verify flasher mode was enabled"
    fi
}

# Function to process one device type
process_device_type() {
    local device_name="$1"
    local device_config="$2"
    
    local output_name="${OUTPUT_DIR}/${BASE_NAME}_${device_name}_EMMC.img"
    
    echo ""
    echo "========================================"
    print_step "Processing: $device_name"
    echo "========================================"
    
    # Step 1: Copy source image
    print_info "Copying source image to $output_name..."
    cp "$SOURCE_IMAGE" "$output_name"
    
    # Step 2: Mount the image
    if ! mount_image "$output_name"; then
        print_error "Failed to mount image for $device_name"
        rm -f "$output_name"
        return 1
    fi
    
    # Step 3: Run prepare_image.sh
    print_info "Running prepare_image.sh for $device_name..."
    if ! "$PREPARE_SCRIPT" "$MOUNT_POINT" "$device_name"; then
        print_error "prepare_image.sh failed for $device_name"
        unmount_image
        rm -f "$output_name"
        return 1
    fi
    
    # Step 4: Enable flasher mode
    enable_flasher_mode
    
    # Step 5: Unmount
    unmount_image
    
    # Step 6: Compress with xz
    print_info "Compressing $output_name with xz (this may take a while)..."
    xz -9 -T0 -v "$output_name"
    
    # Step 7: Change ownership to actual user
    if [ -n "$ACTUAL_UID" ] && [ -n "$ACTUAL_GID" ]; then
        chown "$ACTUAL_UID:$ACTUAL_GID" "${output_name}.xz"
        print_info "Changed ownership of ${output_name}.xz to $ACTUAL_USER"
    fi
    
    print_info "Created: ${output_name}.xz"
    
    return 0
}

# Cleanup function
cleanup() {
    print_warning "Cleaning up..."
    unmount_image
}

# Set trap for cleanup on exit
trap cleanup EXIT

# Main execution
echo ""
echo "========================================"
echo "  BoneIO Black Image Generator"
echo "========================================"
echo "Source image: $SOURCE_IMAGE"
echo "Version: $VERSION"
echo "Output directory: $OUTPUT_DIR"
echo ""

# Process each device type
for device_name in "${!DEVICE_TYPES[@]}"; do
    process_device_type "$device_name" "${DEVICE_TYPES[$device_name]}"
done

echo ""
echo "========================================"
print_info "All images generated successfully!"
echo "========================================"
echo ""
echo "Generated files:"
ls -lh ${BASE_NAME}_*.img.xz 2>/dev/null || echo "No compressed images found"
