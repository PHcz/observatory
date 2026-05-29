#!/usr/bin/env bash
# Verify the .gitignore covers everything we expect to be ignored.
# Greps the repo for committed files that match risky patterns and exits
# non-zero on any finding (so verify-phase8-audit.sh can fail fast).
#
# False positives we deliberately exclude:
#   - *example* / *fixture* / *conftest* / *test*  (test data + worked samples)
#   - frontend/src/lib/styles/tokens.css           (CSS design tokens, not auth tokens)
#   - scripts/audit-panel-tokens.sh                (audit script grepping CSS tokens)
#   - .planning/                                   (planning docs reference secrets by name)
#
# Operator must chmod +x on first checkout if not already executable:
#   chmod +x scripts/audit-gitignore-completeness.sh

set -euo pipefail

findings=0

echo "--- Committed .db / .sqlite files (must be empty) ---"
db_hits=$(git ls-files | grep -E '\.(db|sqlite|sqlite3)$' || true)
if [[ -n "$db_hits" ]]; then
  echo "$db_hits"
  findings=$((findings + 1))
else
  echo "  none"
fi

echo "--- Committed .env files (must be empty; .env.example OK) ---"
env_hits=$(git ls-files | grep -E '(^|/)\.env$|(^|/)\.env\.[^.]+$' | grep -v '\.example$' || true)
if [[ -n "$env_hits" ]]; then
  echo "$env_hits"
  findings=$((findings + 1))
else
  echo "  none"
fi

echo "--- Committed password / token / secret / credential files (must be empty) ---"
# Filter chain:
#   - drop *example*, *fixture*, *conftest*, *test*
#   - drop the CSS design-token system (tokens.css + audit-panel-tokens.sh)
#   - drop .planning/ docs (reference these names by topic, never carry real secrets)
secret_hits=$(git ls-files \
  | grep -iE 'password|secret|token|credential' \
  | grep -v -iE '(example|test|fixture|conftest)' \
  | grep -v -E '^frontend/src/lib/styles/tokens\.css$' \
  | grep -v -E '^scripts/audit-panel-tokens\.sh$' \
  | grep -v -E '^\.planning/' \
  || true)
if [[ -n "$secret_hits" ]]; then
  echo "$secret_hits"
  findings=$((findings + 1))
else
  echo "  none"
fi

echo "--- Committed images (audit-exif-gps.sh sweeps these for GPS EXIF) ---"
img_hits=$(git ls-files | grep -iE '\.(png|jpe?g|tiff|heic)$' || true)
if [[ -n "$img_hits" ]]; then
  echo "$img_hits"
else
  echo "  none (no committed images — EXIF sweep is a no-op until images land)"
fi

echo "--- .gitignore pattern presence check ---"
# Required patterns for v1 OPS-06 coverage.
required_patterns=(
  '\*\.db'
  '\*\.sqlite'
  '\.env'
  '\*\.local'
  'frontend/build/'
  'passwords'
)
missing=0
for pat in "${required_patterns[@]}"; do
  if ! grep -qE "^${pat}$|^${pat}\$" .gitignore; then
    echo "  MISSING in .gitignore: ${pat}"
    missing=$((missing + 1))
  fi
done
if [[ $missing -eq 0 ]]; then
  echo "  all required patterns present"
else
  findings=$((findings + missing))
fi

if [[ $findings -gt 0 ]]; then
  echo ""
  echo "FAIL: $findings finding(s) — see above"
  exit 1
fi
echo ""
echo "PASS: gitignore completeness clean"
exit 0
