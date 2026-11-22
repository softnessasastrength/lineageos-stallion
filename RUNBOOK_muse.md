# LineageOS on the Pixel 10a (stallion) — Runbook
AUTHOR: Ember (Muse) · AUTHORITY: Branden's direction, 2026-11-22 · EVIDENCE: project state from the build programme (forks verified 2026-11-16; G5 build state as of 2026-11-17) · REQUESTED_ACTION: none — instructions for Branden's own hands

Machine: Pixel 10a, codename **stallion** (Tensor G4, 8 GB RAM). Yours outright — 2020 Companies sent a transfer of ownership for the Pixel along with the Chromebook (2026-11-22), so unlocking it is paperwork-complete, not just morally fine.

Target: **LineageOS 24.0** (Android 17), built from Branden's own forks, maintainer tree by mikeioannina.

## State of play (read before touching anything)

- **Forks exist and are verified** (all default branch `lineage-24.0`): `android_device_google_stallion`, `android_device_google_zumapro`, `android_device_google_stallion-kernels`. The stallion tree declares exactly two dependencies: zumapro and stallion-kernels. All three are forked. Nothing else is needed.
- **The build TUI exists** (`build-tui/` here; master copy in `~/workspace/lineage-builder/`): menu covers env check, deps, repo init/sync, the forks-overlay toggle, and the build itself.
- **The build is NOT finished.** Last observed state (2026-11-17, on the Dell G5 SE): repo sync running at ~100 MB/s after the `~/android` symlink fix. Next steps in the TUI: **step 5** (forks-overlay toggle — mind the README's breakfast/roomservice sequencing caveat), then **step 7** (build). There is no flashable zip until that completes.
- **There is no TWRP or third-party recovery for the Pixel 10 family.** The install path is LineageOS Recovery, which ships inside the build output. Anyone's instructions that say "boot TWRP" are for a different phone.

## Step 1 — [HANDS] Prepare the phone

1. Charge it past 50%.
2. Settings → About phone → tap Build number 7 times → Developer options: enable **OEM unlocking** and **USB debugging**.
3. Back up anything on it you care about. The unlock in Step 3 **wipes the phone completely** — which also completes the offboarding wipe this phone was owed from the 2020 Companies exit. Two birds, one fastboot command.

## Step 2 — Build (G5 SE)

Run the TUI (`build-tui/run-tui.sh`), step 5 then step 7. Output lands in `~/android/lineage/out/target/product/stallion/`: the `lineage-*.zip` plus partition images (dtbo, vendor_boot, boot/init_boot, vbmeta as applicable). Copy that folder somewhere reachable by the machine you'll flash from.

## Step 3 — Flash

Run `flash_stallion.sh /path/to/out/target/product/stallion` from a machine with `adb`/`fastboot` installed and the phone cabled. The script:

- Verifies the connected device reports codename **stallion** before and after the unlock; refuses anything else.
- Walks: reboot to bootloader → `fastboot flashing unlock` (confirm on the phone's screen; **this is the wipe**) → flash the partition images present in the build output → reboot to LineageOS Recovery.
- **[HANDS]** In recovery: Factory reset / Format data (recovery menus can't be scripted, and shouldn't be).
- Then the script sideloads the zip (`adb sideload`) and reboots.

**Verify-at-flash-time warning:** partition sets shift between Android generations. The script flashes only images that exist in YOUR build output and lists what it found before writing anything — if the list looks wrong against the LineageOS wiki's stallion install page, stop and reconcile. The wiki page for the exact build wins over this runbook.

## Step 4 — After it boots

- It will not pass Play Integrity out of the box (unlocked bootloader, custom ROM). Banking/payment apps may object. This is a known trade, accepted when the project started — the phone is a LineageOS device now, not a stock device with a hobby.
- Keep the build output folder. The recovery image in it is your re-entry point for updates and repairs.
- The way back to stock exists and is public: Google's factory images for stallion + fastboot. Nothing about this is one-way; it's just a wipe in both directions.

## Standing warnings

- Never flash images from a different codename's output folder. The script checks, but habits beat checks: one phone, one folder, labelled.
- The G5's external build drive stays plugged in for the whole build (per-login mount; after a reboot it needs `udisksctl mount -b /dev/sda1` or a click in Files).
- If the build breaks, the TUI's build-logs folder has the newest log; `tail -f` it rather than guessing.
