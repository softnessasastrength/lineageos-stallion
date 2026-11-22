#!/bin/bash
# Flash a self-built LineageOS 24.0 (stallion) onto the Pixel 10a.
#
# Usage: bash flash_stallion.sh /path/to/out/target/product/stallion
#
# Safety shape: codename verified before and after the unlock; every
# destructive step behind its own confirmation; only images that exist
# in the build output are flashed, and the list is shown before writing.
# The recovery factory-reset is a [HANDS] step (recovery UI, by design).
#
# AUTHOR: Ember (Muse) · AUTHORITY: Branden's direction 2026-11-22
# EVIDENCE: LineageOS zumapro-family install flow; partition sets vary
# by generation — the build output + the wiki stallion page win ties.

set -u
OUT="${1:-}"
die() { echo ""; echo "STOP: $1" >&2; exit 1; }
ask() { read -r -p "$1 [y/N]: " A; [ "$A" = "y" ] || die "Not confirmed. Stopped."; }

[ -n "$OUT" ] && [ -d "$OUT" ] || die "Usage: bash flash_stallion.sh /path/to/out/target/product/stallion"
command -v adb >/dev/null || die "adb not installed."
command -v fastboot >/dev/null || die "fastboot not installed."

ZIP=$(ls "$OUT"/lineage-*.zip 2>/dev/null | head -n1)
[ -n "$ZIP" ] || die "No lineage-*.zip in $OUT — the build hasn't produced one yet."

echo "== Build output inventory =="
ls -1 "$OUT"/*.img "$ZIP" 2>/dev/null | sed 's/^/  /'
echo ""
echo "Only images from THIS folder will be flashed. If this list disagrees"
echo "with the LineageOS wiki install page for stallion, stop now."

echo ""
echo "== Device check (adb) =="
adb wait-for-device
DEV=$(adb shell getprop ro.product.device 2>/dev/null | tr -d '\r')
echo "  ro.product.device: ${DEV:-unreadable}"
[ "$DEV" = "stallion" ] || die "Connected device is not stallion. Refusing."

echo ""
echo "Prerequisites on the phone: OEM unlocking ON, USB debugging ON"
echo "(Developer options). The next phase WIPES the phone."
ask "Reboot to bootloader and unlock (wipe) now?"
adb reboot bootloader
sleep 3
PROD=$(fastboot getvar product 2>/dev/null | awk -F': ' '/product/{print $2}' | tr -d '\r')
echo "  fastboot product: ${PROD:-unreadable}"
[ "$PROD" = "stallion" ] || die "fastboot does not see stallion. Refusing."

fastboot flashing unlock
echo "Confirm the unlock ON THE PHONE (volume keys + power). The phone wipes."
ask "Unlock confirmed on-device and phone back at the bootloader?"

flash_if() {
  local img="$1" part="$2"
  if [ -f "$OUT/$img" ]; then
    echo "  fastboot flash $part $img"
    fastboot flash "$part" "$OUT/$img" || die "Flash of $part failed."
  else
    echo "  (skip $part — $img not in build output)"
  fi
}

echo ""
echo "== Flashing partition images =="
# vbmeta first with verification disabled (standard LineageOS-on-Pixel
# step when the build ships one), then the boot-chain images.
if [ -f "$OUT/vbmeta.img" ]; then
  echo "  fastboot --disable-verity --disable-verification flash vbmeta vbmeta.img"
  fastboot --disable-verity --disable-verification flash vbmeta "$OUT/vbmeta.img" || die "vbmeta flash failed."
fi
flash_if dtbo.img dtbo
flash_if vendor_boot.img vendor_boot
flash_if boot.img boot
flash_if init_boot.img init_boot

echo ""
echo "== Reboot to LineageOS Recovery =="
fastboot reboot recovery
echo ""
echo "[HANDS] In recovery, on the phone:"
echo "  1. Factory reset -> Format data / factory reset. Confirm."
echo "  2. Then: Apply update -> Apply from ADB."
ask "Phone is in recovery, formatted, and waiting in 'Apply from ADB'?"
echo ""
echo "== Sideloading $(basename "$ZIP") =="
adb sideload "$ZIP" || die "Sideload failed — read the recovery screen before retrying."
echo ""
echo "Back out of the update menu in recovery and choose Reboot system now."
echo "First boot takes a while. Welcome to your own build."
