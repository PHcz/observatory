#!/usr/bin/env bash
# Required pre-commit sensitive-data gate — runs on EVERY commit via pre-commit.
#
# Purpose: stop secrets and personal data from ever entering the public history.
# Complements the gitleaks hook (generic API keys/tokens) with project-specific
# checks:
#   1. commit author must be a no-reply identity (no personal email in history)
#   2. refuse to commit known secret/credential files (defence beyond .gitignore)
#   3. refuse images carrying GPS EXIF (home-location leak)
#   4. refuse any staged content matching local, gitignored sensitive patterns —
#      the real PII strings live ONLY in .git-sensitive-patterns, never in the repo
#
# pre-commit passes the staged filenames as "$@".
set -euo pipefail

fail=0
note() { echo "  ✗ $*"; fail=1; }

# 1) Author identity must not carry a personal email.
email="$(git config user.email 2>/dev/null || true)"
case "$email" in
  *@users.noreply.github.com) ;;
  *) note "git user.email '$email' is not a no-reply identity — run: git config user.email <id>@users.noreply.github.com" ;;
esac

# 2) Never commit real secret/credential files.
for f in "$@"; do
  case "$f" in
    *.example) ;;  # .env.example and *.example templates are safe — secrets must be blank
    .env|*/.env|.env.*|*/.env.*|*secret*.env|*.pem|*.key)
      note "refusing to commit secret file: $f" ;;
    deploy/mosquitto/passwords)
      note "refusing to commit the real mosquitto passwords file (use passwords.example): $f" ;;
  esac
done

# 3) GPS EXIF in staged images (needs exiftool; skipped if unavailable).
if command -v exiftool >/dev/null 2>&1; then
  for f in "$@"; do
    case "$f" in
      *.png|*.jpg|*.jpeg|*.tiff|*.tif|*.heic|*.webp)
        [ -f "$f" ] || continue
        if exiftool -GPS:all "$f" 2>/dev/null | grep -qiE 'GPS'; then
          note "GPS EXIF in image $f — strip with: exiftool -GPS:all= -overwrite_original '$f'"
        fi ;;
    esac
  done
fi

# 4) Project-specific PII/secret patterns, kept LOCAL and gitignored so the actual
#    sensitive strings are never committed. One POSIX extended-regex per line;
#    blank lines and lines starting with '#' are ignored.
patterns=".git-sensitive-patterns"
if [ -f "$patterns" ]; then
  while IFS= read -r rx || [ -n "$rx" ]; do
    [ -z "$rx" ] && continue
    case "$rx" in \#*) continue ;; esac
    for f in "$@"; do
      [ -f "$f" ] || continue
      if grep -nIEe "$rx" "$f" >/dev/null 2>&1; then
        note "staged file '$f' matches sensitive pattern /$rx/"
      fi
    done
  done < "$patterns"
fi

if [ "$fail" -ne 0 ]; then
  echo "✗ sensitive-data gate FAILED — commit aborted. Fix the items above or unstage them." >&2
  exit 1
fi
echo "✓ sensitive-data gate passed"
