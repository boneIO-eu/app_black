#!/bin/bash

# Script downloads YAML files from boneIO-eu/app_black for selected kind of board (eg. 24x16)
# and copies them to ~/boneio/ directory, with optional backup and cleanup.

## USAGE: 
##   curl -fsSL https://raw.githubusercontent.com/boneIO-eu/app_black/refs/heads/dev/config_script.sh | bash -s -- 24x16
##   curl -fsSL https://raw.githubusercontent.com/boneIO-eu/app_black/refs/heads/dev/config_script.sh | bash -s -- 24x16 --remove-old

set -e

REMOVE_OLD=false

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --remove-old)
      REMOVE_OLD=true
      shift
      ;;
    *)
      SIZE="$1"
      shift
      ;;
  esac
done

if [ -z "$SIZE" ]; then
  echo "Usage: $0 <size> [--remove-old]"
  echo "Example: $0 24x16"
  echo "Example: $0 24x16 --remove-old"
  exit 1
fi

DEST_DIR="$HOME/boneio"
TMP_DIR=$(mktemp -d)

# Backup existing YAML files (non-recursive, only files in DEST_DIR)
if [ -d "$DEST_DIR" ]; then
  YAML_FILES=$(find "$DEST_DIR" -maxdepth 1 -type f -name "*.yaml" 2>/dev/null || true)
  
  if [ -n "$YAML_FILES" ]; then
    BACKUP_NAME="boneio_backup_$(date +%Y%m%d_%H%M%S).tar.gz"
    BACKUP_PATH="$HOME/$BACKUP_NAME"
    
    echo "Creating backup of existing YAML files..."
    tar -czf "$BACKUP_PATH" -C "$DEST_DIR" --no-recursion $(cd "$DEST_DIR" && ls -1 *.yaml 2>/dev/null || true)
    echo "Backup created: $BACKUP_PATH"
  else
    echo "No existing YAML files to backup"
  fi
fi

# Remove old config if flag is set
if [ "$REMOVE_OLD" = true ] && [ -d "$DEST_DIR" ]; then
  echo "Removing old YAML files..."
  find "$DEST_DIR" -maxdepth 1 -type f -name "*.yaml" -delete
  echo "Old YAML files removed"
fi

# Download new config
git clone --depth 1 --branch dev https://github.com/boneIO-eu/app_black.git "$TMP_DIR/app_black"

SRC_DIR="$TMP_DIR/app_black/boneio/example_config/$SIZE"

if [ ! -d "$SRC_DIR" ]; then
  echo "No such config: $SIZE"
  rm -rf "$TMP_DIR"
  exit 2
fi

mkdir -p "$DEST_DIR"
cp -vf "$SRC_DIR"/*.yaml "$DEST_DIR/"

rm -rf "$TMP_DIR"

echo "YAML files for $SIZE have been downloaded to $DEST_DIR"