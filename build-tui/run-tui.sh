#!/usr/bin/env bash
# Launcher for the LineageOS stallion build TUI.
cd "$(dirname "$0")"
exec python3 lineage_builder_tui.py "$@"
