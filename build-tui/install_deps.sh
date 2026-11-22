#!/usr/bin/env bash
# Installs everything the LineageOS 24 build for stallion needs on
# Ubuntu (incl. WSL). Called by the TUI's step 2; safe to run directly.
# Ember, 2026-11-16.
set -e

echo "== apt: build packages (LineageOS wiki list) =="
sudo apt update
sudo apt install -y \
  bc bison build-essential ccache curl flex g++-multilib gcc-multilib \
  git git-lfs gnupg gperf imagemagick lib32ncurses-dev lib32readline-dev \
  lib32z1-dev libelf-dev lz4 libncurses-dev libncurses6 \
  libsdl1.2-dev libssl-dev libxml2-utils lzop pngcrush rsync \
  schedtool squashfs-tools xsltproc zip zlib1g-dev python3 \
  python-is-python3 openjdk-21-jdk-headless adb fastboot

echo "== repo tool into ~/bin =="
mkdir -p ~/bin
if [ ! -x ~/bin/repo ]; then
  curl -s https://storage.googleapis.com/git-repo-downloads/repo > ~/bin/repo
  chmod a+x ~/bin/repo
fi
grep -q 'HOME/bin' ~/.bashrc 2>/dev/null || \
  echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc
export PATH="$HOME/bin:$PATH"

echo "== git identity (repo init needs it) =="
if ! git config --global user.email >/dev/null 2>&1; then
  read -rp "git email: " gitmail
  git config --global user.email "$gitmail"
fi
if ! git config --global user.name >/dev/null 2>&1; then
  read -rp "git name: " gitname
  git config --global user.name "$gitname"
fi
git lfs install --skip-repo || true

echo "== ccache: 50G, wired for the build =="
ccache -M 50G
grep -q 'USE_CCACHE' ~/.bashrc 2>/dev/null || {
  echo 'export USE_CCACHE=1' >> ~/.bashrc
  echo 'export CCACHE_EXEC=$(command -v ccache)' >> ~/.bashrc
}

echo "== done. Back in the TUI: step 3 (init), step 4 (sync), step 7 (build). =="
