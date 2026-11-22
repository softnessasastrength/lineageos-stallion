# lineageos-stallion

LineageOS 24.0 for the **Pixel 10a** (codename **stallion**, Tensor G4), built from the owner's own forks and flashed onto a phone that a former employer transferred to him outright — see the Chromebook sibling project, [violator](https://github.com/softnessasastrength/violator), for the other half of the severance package.

## Contents

- `RUNBOOK_muse.md` — state of play, build steps, flash sequence, and the standing warnings. Start here.
- `flash_stallion.sh` — the gated flash: codename verified twice, the unlock (and its wipe) behind explicit confirmations, only the images in your build output get written, sideload at the end. The recovery factory-reset stays a hands-on step because recovery menus don't take scripts and shouldn't.
- `build-tui/` — the LineageOS builder TUI from the G5 SE build programme: environment check, dependency install, repo init/sync, the forks-overlay toggle, and the build, with per-core load bars and live log streaming. Master copy lives in the owner's workspace; this is the published snapshot.

## The forks (the actual device trees)

- `android_device_google_stallion`
- `android_device_google_zumapro`
- `android_device_google_stallion-kernels`

All on `lineage-24.0`. The stallion tree declares exactly the other two as its dependencies.

## Honest status

The build was last seen mid-sync on the G5 SE (2026-11-17); the forks-overlay toggle and the build itself are the next steps, and there is no flashable zip yet. This repo is the runway, built before the plane lands — the same way the runbook's warnings were written before anyone's bootloader got unlocked.

There is no TWRP for the Pixel 10 family. LineageOS Recovery, from the build output, is the way in. Play Integrity will not pass on an unlocked custom build; that trade was accepted when the project started.

Runbook and flash script by Ember (Muse), at the owner's direction. LineageOS and the device trees belong to their respective authors and maintainers.
