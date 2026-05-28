#!/usr/bin/env bash
# Verify the .gitignore covers everything we expect to be ignored.
# Greps the repo for committed files that match risky patterns.
#
# Operator must chmod +x on first checkout if not already executable:
#   chmod +x scripts/audit-gitignore-completeness.sh
set -euo pipefail
echo "--- Committed .db files (must be empty) ---"
git ls-files | grep -E '\.db$|\.sqlite$|\.sqlite3$' || echo "  none"
echo "--- Committed .env files (must be empty; .env.example OK) ---"
git ls-files | grep -E '(^|/)\.env$|(^|/)\.env\.[^.]+$' | grep -v '\.example$' || echo "  none"
echo "--- Committed password / token / secret files (must be empty) ---"
git ls-files | grep -iE 'password|secret|token|credential' | grep -v -iE '(example|test|fixture|conftest)' || echo "  none"
echo "--- Committed images (audit EXIF GPS) ---"
git ls-files | grep -iE '\.(png|jpe?g|tiff|heic)$' || echo "  none"
