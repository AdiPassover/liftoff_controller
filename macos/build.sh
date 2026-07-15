#!/bin/bash
# Build the HID gamepad server for macOS.
# Requires Xcode Command Line Tools: xcode-select --install

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC="$SCRIPT_DIR/hid_gamepad_server.m"
OUT="$SCRIPT_DIR/hid_gamepad_server"

echo "Compiling hid_gamepad_server..."
clang -framework Foundation -framework IOKit \
      -O2 -o "$OUT" "$SRC"

echo "Built: $OUT"
echo ""
echo "To test: $OUT"
echo "Note: SIP must be disabled for IOHIDUserDevice to work."
