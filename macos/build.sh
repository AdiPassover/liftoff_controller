#!/bin/bash
# Build the HID gamepad server for macOS.
# Requires Xcode Command Line Tools: xcode-select --install

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC="$SCRIPT_DIR/hid_gamepad_server.m"
OUT="$SCRIPT_DIR/hid_gamepad_server"

echo "Compiling hid_gamepad_server..."
clang -framework Foundation -framework IOKit -framework Security \
      -O2 -o "$OUT" "$SRC"

echo "Built: $OUT"
echo ""
echo "Verifying code signature..."
codesign --verify --strict --verbose=2 "$OUT"

SIGNATURE_INFO="$(codesign --display --verbose=4 "$OUT" 2>&1 || true)"
echo "$SIGNATURE_INFO"

ENTITLEMENTS="$(codesign --display --entitlements - --xml "$OUT" 2>/dev/null || true)"
echo ""
echo "Embedded entitlements:"
if [[ -n "$ENTITLEMENTS" ]]; then
    echo "$ENTITLEMENTS"
else
    echo "(none)"
fi

echo ""
if [[ "$ENTITLEMENTS" == *"com.apple.developer.hid.virtual.device"* ]]; then
    echo "Virtual HID entitlement is embedded."
    echo "Verify that the signature and provisioning profile authorize it."
else
    echo "WARNING: com.apple.developer.hid.virtual.device is not embedded."
    echo "The helper was compiled, but macOS will deny virtual HID creation."
    echo "This is a restricted entitlement; do not add it to an ad-hoc signature."
fi

echo ""
echo "To test: $OUT"
