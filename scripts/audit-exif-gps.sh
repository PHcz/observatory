#!/usr/bin/env bash
# Exit non-zero if any committed image contains GPS EXIF data.
#
# Requires exiftool: `sudo apt install -y exiftool` (Pi) or `brew install exiftool` (macOS).
# Operator must chmod +x on first checkout if not already executable:
#   chmod +x scripts/audit-exif-gps.sh
set -euo pipefail
exit_code=0
while IFS= read -r f; do
  if exiftool -GPS:all "$f" 2>/dev/null | grep -qE 'GPS'; then
    echo "WARN: GPS EXIF found in $f"
    exit_code=1
  fi
done < <(git ls-files | grep -iE '\.(png|jpe?g|tiff|heic)$')
exit "$exit_code"
