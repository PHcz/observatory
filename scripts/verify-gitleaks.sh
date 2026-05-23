#!/usr/bin/env bash
# Verifies that the gitleaks pre-commit hook actually blocks a commit
# containing a fake AWS-key-shaped payload.
#
# Strategy:
#   1. Write a fake AWS key into a NEW file at repo root (not in tests/fixtures/).
#   2. git add it.
#   3. Run `pre-commit run gitleaks` on the staged file.
#   4. Assert exit code is non-zero (i.e., gitleaks blocked it).
#   5. Clean up: git reset, rm the file.
#
# The test key below matches the gitleaks aws-access-token rule
# (4-letter prefix + 16 alphanumeric chars) but is obviously synthetic and
# used ONLY in this script's temp-file context.
#
# This is destructive to the staging area while running, so it is NOT run by
# CI or by other tests — invoke manually as part of phase acceptance.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

if ! command -v pre-commit >/dev/null 2>&1; then
  echo "FAIL: pre-commit not installed"; exit 1
fi

# Save current staging state and stash anything currently staged
STASHED=0
if ! git diff --cached --quiet; then
  git stash push --staged -m "verify-gitleaks-temp" >/dev/null
  STASHED=1
fi

TMPFILE="$REPO_ROOT/_gitleaks_test_payload.txt"
cleanup() {
  git reset HEAD "$TMPFILE" >/dev/null 2>&1 || true
  rm -f "$TMPFILE"
  if [ "$STASHED" = "1" ]; then
    git stash pop >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

# Write the test payload to a file outside the gitleaks allowlist.
# The four-letter prefix is reconstructed from a base64 blob at runtime so this
# script's own source does not contain the literal pattern that secret-scanners
# (including this repo's own pre-commit hook) match on.
KEY_PREFIX="$(printf 'QUtJQQ==' | base64 -d)"
KEY_SUFFIX="FAKEKEYFORTEST00"
printf "fake_aws_access_key_id = %s%s\n" "$KEY_PREFIX" "$KEY_SUFFIX" > "$TMPFILE"

git add "$TMPFILE"

# Run only the gitleaks hook on the staged file
OUT="$(pre-commit run gitleaks --files "$TMPFILE" 2>&1)"
RC=$?

if [ "$RC" -eq 0 ]; then
  echo "FAIL: gitleaks did NOT block the staged secret. Output:"
  echo "$OUT"
  exit 1
fi

echo "OK: gitleaks blocked the staged secret (exit code $RC)"
exit 0
