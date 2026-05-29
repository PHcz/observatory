#!/usr/bin/env bash
# Exit non-zero if any committed image contains GPS EXIF data.
#
# Prerequisite: exiftool must be installed.
#   - macOS (operator dev): brew install exiftool
#   - Pi / Debian:          sudo apt install -y libimage-exiftool-perl
#
# Operator must chmod +x on first checkout if not already executable:
#   chmod +x scripts/audit-exif-gps.sh

set -euo pipefail

if ! command -v exiftool >/dev/null 2>&1; then
  echo "ERROR: exiftool not installed."
  echo "  macOS: brew install exiftool"
  echo "  Debian/Pi: sudo apt install -y libimage-exiftool-perl"
  exit 2
fi

images=$(git ls-files | grep -iE '\.(png|jpe?g|tiff|heic)$' || true)

if [[ -z "$images" ]]; then
  echo "INFO: no committed images — nothing to scan. PASS."
  exit 0
fi

exit_code=0
scanned=0
while IFS= read -r f; do
  scanned=$((scanned + 1))
  if exiftool -GPS:all "$f" 2>/dev/null | grep -qE 'GPS'; then
    echo "WARN: GPS EXIF found in $f"
    exit_code=1
  fi
done <<< "$images"

if [[ $exit_code -eq 0 ]]; then
  echo "PASS: $scanned image(s) scanned, no GPS EXIF found"
else
  echo "FAIL: GPS EXIF detected — run: exiftool -GPS:all= -overwrite_original <file>"
fi

exit "$exit_code"
