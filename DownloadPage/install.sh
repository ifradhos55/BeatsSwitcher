#!/bin/bash

echo "🎧 Installing Beats Switcher..."

# In a real-world scenario, this URL would be your actual website domain.
DMG_URL="http://localhost:8000/BeatsSwitcher.dmg"
TEMP_DIR=$(mktemp -d)
DMG_FILE="$TEMP_DIR/BeatsSwitcher.dmg"

echo "📥 Downloading app..."
curl -sL "$DMG_URL" -o "$DMG_FILE"

echo "💿 Mounting disk image..."
# Mount and capture the mount point path
MOUNT_POINT=$(hdiutil attach -nobrowse "$DMG_FILE" | grep -o '/Volumes/.*')

echo "🚀 Copying to Applications folder..."
# Remove any existing version
rm -rf "/Applications/BeatsSwitcher.app"
# Copy the app to Applications
cp -R "$MOUNT_POINT/BeatsSwitcher.app" "/Applications/"

echo "🧹 Cleaning up..."
# Unmount the DMG
hdiutil detach "$MOUNT_POINT" -quiet
# Clear the quarantine attribute explicitly to ensure it runs
xattr -cr "/Applications/BeatsSwitcher.app" 2>/dev/null
# Remove the temporary download folder
rm -rf "$TEMP_DIR"

echo "✨ Launching Beats Switcher!"
open "/Applications/BeatsSwitcher.app"

echo "✅ Installation complete! Look for the headphones icon in your menu bar."
