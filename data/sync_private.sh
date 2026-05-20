#!/usr/bin/env bash
# Pull source data from the private techteam-reporting-data repo into data/.
# Required before running load.py / aggregate.py / build.py locally.
#
# Usage: ./data/sync_private.sh
#
# Assumes you have SSH access to the private repo.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PRIVATE_REPO="${TECHTEAM_DATA_REPO:-https://github.com/synthesis-labs/techteam-reporting-data.git}"
PRIVATE_DIR="$ROOT/_data_private"

if [ ! -d "$PRIVATE_DIR/.git" ]; then
  echo "Cloning $PRIVATE_REPO → $PRIVATE_DIR"
  git clone "$PRIVATE_REPO" "$PRIVATE_DIR"
else
  echo "Pulling latest from $PRIVATE_REPO"
  git -C "$PRIVATE_DIR" pull --ff-only
fi

shopt -s nullglob
for d in "$PRIVATE_DIR"/[0-9][0-9][0-9][0-9]-[0-9][0-9]; do
  echo "  staging $(basename "$d")/"
  rsync -a --delete "$d/" "$ROOT/data/$(basename "$d")/"
done

if [ -f "$PRIVATE_DIR/aliases.csv" ]; then
  cp "$PRIVATE_DIR/aliases.csv" "$ROOT/data/aliases.csv"
  echo "  staged aliases.csv"
fi

echo "Sync complete."
