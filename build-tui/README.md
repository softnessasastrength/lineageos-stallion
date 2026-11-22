# LineageOS Builder — stallion (Pixel 10a)

A few-clicks TUI that walks a LineageOS 24.0 (Android 17) build for
**stallion** — your Google Pixel 10a — from an empty folder to a flashable
zip, with btop-style live telemetry across the top while it suffers.

Built by Ember, 2026-11-16. stdlib-only Python; telemetry read from /proc.

## Your forks

Forked into `softnessasastrength` on 2026-11-16 (from `LineageOS`):

- `android_device_google_stallion` — the device tree
- `android_device_google_zumapro` — its declared dependency (shared Tensor platform tree)
- `android_device_google_stallion-kernels` — its declared dependency (prebuilt kernels)

Menu item **5** toggles a local-manifest overlay so the build uses *your*
forks of those three instead of upstream. Default is upstream; flip it
before a sync if you want your copies in the tree. One sequencing note:
the overlay removes the upstream entries that `breakfast` generates in
`roomservice.xml`, so if a sync ever complains about a remove-project
before your first build, run **7** once (breakfast creates that file),
then toggle **5** and sync again.

## Appendix: putting WSL itself on the external drive

The build tree lives *inside* Ubuntu's virtual disk, so the fix is to move
the whole distro, not to build on a mounted Windows drive (the `/mnt/<drive>`
path is slow 9p filesystem and its case handling breaks Android trees).

Do this from **PowerShell** (Windows side), with Ubuntu closed:

1. `wsl --version` — note the WSL version. (`wsl --update` if it's ancient.)
2. `wsl --shutdown`
3. Make a folder on the external drive, e.g. `D:\WSL` — substitute your
   drive's letter, and give that drive a **permanent letter** in Disk
   Management so the path never moves. The drive should be **NTFS**.
4. Modern WSL (2.3+): `wsl --manage Ubuntu --move D:\WSL\Ubuntu`
   Older WSL: `wsl --export Ubuntu C:\ubuntu-backup.tar`, then
   `wsl --unregister Ubuntu`, then
   `wsl --import Ubuntu D:\WSL\Ubuntu C:\ubuntu-backup.tar --version 2`.
   The import route forgets your default user — afterwards, inside Ubuntu:
   `printf '[user]\ndefault=branden\n' | sudo tee /etc/wsl.conf`, then
   `wsl --terminate Ubuntu` from PowerShell.
5. Verify: start Ubuntu and run `df -h /` — the free space should now be
   the external drive's.

Space traps: older WSL caps the virtual disk at 256 GB even on a huge
drive. If a sync ever dies with "no space left" while the drive shows
room, grow it: `wsl --manage Ubuntu --resize 800GB` (WSL 2.3+; shut down
first). And keep the external plugged in for the whole build — a USB
disconnect mid-build is exactly as fun as it sounds.

## On the Windows PC (WSL Ubuntu)

1. Copy this `lineage-builder` folder into your Ubuntu home
   (e.g. from Windows: `\\wsl$\Ubuntu\home\branden\lineage-builder`).
2. In Ubuntu: `cd ~/lineage-builder && chmod +x run-tui.sh install_deps.sh`
3. `./run-tui.sh`
4. Press **2** once (dependencies — sudo will ask for your WSL password),
   then **3** (init), **4** (sync), **7** (build). Watch the telemetry.

`python3 lineage_builder_tui.py --plain` gives a no-curses fallback menu.

## Honest numbers

- **Disk:** the source tree is ~150–200 GB; with build output, keep
  **~350 GB free** on the drive holding `~/android/lineage`. In WSL that
  means the virtual disk grows — check your C: drive too.
- **First sync:** hours, mostly your connection.
- **First build:** hours, mostly your CPU. Later builds lean on ccache
  (50 GB cache configured by step 2; the telemetry header shows hit rate).
- **RAM:** under ~16 GB the link steps can OOM. If that happens, tell
  Ember — the fix is fewer parallel jobs, and it's a one-line change.
- **Blobs:** official device trees normally resolve vendor files during
  `breakfast`. Menu **6** (adb extraction from your phone on stock
  firmware) is there only if a build ever complains about missing vendor
  files.

## Keys inside a running job

- `Ctrl-C` — stop the job (the partial log survives in `~/android/lineage/build-logs/`)
- `PgUp` / `PgDn` — scroll the output
- any key when finished — back to the menu

The header always shows: per-core CPU bars, memory, swap, load average,
free disk, ccache hit rate, and — during sync/build — elapsed time and
ninja/sync progress parsed live from the build output.
