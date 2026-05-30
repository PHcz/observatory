#!/usr/bin/env bash
# Phase 9 public-release docs gate.
#
# Asserts the DOC-01..DOC-10 file-existence, content-grep, and internal-link
# conditions in one re-runnable command. Mirrors scripts/verify-phase8-audit.sh
# structure (set -euo pipefail, REPO_ROOT resolution, numbered gates, final
# PASS/FAIL line, non-zero exit on any failure).
#
# Design contract (CRITICAL):
#   - A check on a DOC file that does NOT yet exist is SKIPped (not failed), so
#     this gate is green in Wave 0 before any doc is authored, and downstream
#     plans (09-01..09-04) can reference it in their acceptance criteria.
#   - A check on a DOC file that DOES exist but is malformed FAILs loudly.
#   - README.md already exists as a pre-Phase-9 internal stub (Phase 1 Pi-setup
#     notes, still references bootstrap-pi.sh). The Phase-9 README rewrite is
#     owned by Plan 09-03 (DOC-01) and the bootstrap-pi.sh strip by Plan 09-02
#     (DOC-09). To keep this gate green NOW yet fail once the rewrite lands but
#     is malformed, the README-content checks (DOC-01) and the README-stripped
#     check (DOC-09 half) activate only once the README has been migrated to its
#     public form — detected by the presence of a `docs/HARDWARE` link, which is
#     DOC-01's required content and Plan 09-03's defining deliverable. Until then
#     they SKIP. (Deviation Rule 3 — reconciles the plan's "exit 0 right now"
#     acceptance with a pre-existing stub README; see 09-00-SUMMARY.md.)
#
# Always invoked as `bash scripts/verify-phase9-docs.sh` — does not rely on the
# executable bit. Operator may `chmod +x scripts/verify-phase9-docs.sh` on first
# checkout if a bare `./scripts/verify-phase9-docs.sh` is preferred.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

fail=0

# softcheck "label" FILE 'grep-expr'
#   SKIP if FILE absent; PASS/FAIL on the evaluated expression otherwise.
softcheck() {
  if [[ ! -e "$2" ]]; then echo "  SKIP: $1 ($2 absent)"; return; fi
  if eval "$3"; then echo "  PASS: $1"; else echo "  FAIL: $1"; fail=1; fi
}

# readme_is_public — true once README.md has been migrated to its Phase-9 public
# form (gated on the docs/HARDWARE link, DOC-01's required content). Until the
# Plan 09-03 rewrite lands, the pre-existing Phase-1 stub README is exempt.
readme_is_public() {
  [[ -e README.md ]] && grep -q 'docs/HARDWARE' README.md
}

# softcheck_readme "label" 'grep-expr' — like softcheck but keyed on the public
# README sentinel rather than mere existence.
softcheck_readme() {
  if ! readme_is_public; then echo "  SKIP: $1 (README.md is pre-Phase-9 stub)"; return; fi
  if eval "$2"; then echo "  PASS: $1"; else echo "  FAIL: $1"; fail=1; fi
}

echo "===== 1/4 file existence + content ====="

# DOC-01 README sections (public-form only)
softcheck_readme "DOC-01 README has headings + docs/HARDWARE + LICENSE refs" \
  "grep -qE '^#' README.md && grep -q 'docs/HARDWARE' README.md && grep -q 'LICENSE' README.md"

# DOC-02 LICENSE
softcheck "DOC-02 LICENSE is MIT with 2026 PHcz copyright" LICENSE \
  "head -1 LICENSE | grep -q 'MIT License' && grep -q 'Copyright (c) 2026 PHcz' LICENSE"

# DOC-03 SECURITY
softcheck "DOC-03 SECURITY.md has 'report a vulnerability'" SECURITY.md \
  "grep -qi 'report a vulnerability' SECURITY.md"

# DOC-04 CONTRIBUTING
softcheck "DOC-04 CONTRIBUTING.md has 'uv sync' + 'as-is'" CONTRIBUTING.md \
  "grep -q 'uv sync' CONTRIBUTING.md && grep -q 'as-is' CONTRIBUTING.md"

# DOC-05 Code of Conduct
softcheck "DOC-05 CODE_OF_CONDUCT.md is Contributor Covenant with contact filled in" CODE_OF_CONDUCT.md \
  "grep -q 'Contributor Covenant' CODE_OF_CONDUCT.md && ! grep -q 'INSERT CONTACT METHOD' CODE_OF_CONDUCT.md"

# DOC-06 issue/PR templates (existence; skip whole check if .github absent)
if [[ ! -e .github ]]; then
  echo "  SKIP: DOC-06 .github templates (.github absent)"
else
  if test -d .github/ISSUE_TEMPLATE && test -f .github/PULL_REQUEST_TEMPLATE.md; then
    echo "  PASS: DOC-06 .github/ISSUE_TEMPLATE + PULL_REQUEST_TEMPLATE.md present"
  else
    echo "  FAIL: DOC-06 .github/ISSUE_TEMPLATE + PULL_REQUEST_TEMPLATE.md present"
    fail=1
  fi
fi

# DOC-07 HARDWARE — no real London coordinate (51.5xxxx) leaked
softcheck "DOC-07 docs/HARDWARE.md has no real coord (51.5xxxx sentinel)" docs/HARDWARE.md \
  "! grep -qE '51\\.5[0-9]{4}' docs/HARDWARE.md"

# DOC-08 SETUP
softcheck "DOC-08 docs/SETUP.md has 'uv sync' + 'npm run build' + 'PROVISIONING.md'" docs/SETUP.md \
  "grep -q 'uv sync' docs/SETUP.md && grep -q 'npm run build' docs/SETUP.md && grep -q 'PROVISIONING.md' docs/SETUP.md"

# DOC-09 OPERATIONS content
softcheck "DOC-09 docs/OPERATIONS.md mentions obs-muon.service" docs/OPERATIONS.md \
  "grep -q 'obs-muon.service' docs/OPERATIONS.md"

# DOC-09 README — bootstrap-pi.sh must be stripped (public-form README only)
softcheck_readme "DOC-09 README.md no longer references bootstrap-pi.sh" \
  "! grep -q 'bootstrap-pi.sh' README.md"

echo ""
echo "===== 2/4 internal markdown link resolution ====="

# Collect the markdown docs that exist; gate the whole check if none do.
link_files=()
[[ -e README.md ]] && link_files+=("README.md")
while IFS= read -r d; do link_files+=("$d"); done < <(find docs -maxdepth 1 -name '*.md' 2>/dev/null || true)

if [[ ${#link_files[@]} -eq 0 ]]; then
  echo "  SKIP: no markdown docs to link-check yet"
else
  checked=0
  for f in "${link_files[@]}"; do
    [[ -e "$f" ]] || continue
    dir="$(dirname "$f")"
    # Extract relative markdown link targets: ](target)
    while IFS= read -r target; do
      [[ -z "$target" ]] && continue
      # Skip external / anchor-only / mailto links
      case "$target" in
        http://*|https://*|\#*|mailto:*) continue ;;
      esac
      # Strip any #anchor suffix and surrounding angle brackets / whitespace
      target="${target%%#*}"
      target="${target#<}"
      target="${target%>}"
      [[ -z "$target" ]] && continue
      checked=$((checked + 1))
      # Resolve relative to the file's directory (absolute targets honoured as-is)
      if [[ "$target" == /* ]]; then
        resolved="$REPO_ROOT$target"
      else
        resolved="$dir/$target"
      fi
      if [[ ! -e "$resolved" ]]; then
        echo "  FAIL: broken link $target in $f"
        fail=1
      fi
    done < <(grep -ohE '\]\(([^)]+)\)' "$f" | sed -E 's/^\]\(//; s/\)$//')
  done
  if [[ "$fail" -eq 0 ]]; then
    echo "  PASS: all relative markdown links resolve ($checked checked across ${#link_files[@]} file(s))"
  fi
fi

echo ""
echo "===== 3/4 screenshots + EXIF (DOC-10) ====="

if [[ -d docs/images ]] && compgen -G "docs/images/*.png" >/dev/null 2>&1; then
  if bash "$REPO_ROOT/scripts/audit-exif-gps.sh"; then
    echo "  PASS: DOC-10 docs/images/*.png present and EXIF-clean"
  else
    echo "  FAIL: DOC-10 EXIF GPS detected in docs/images"
    fail=1
  fi
else
  echo "  SKIP: DOC-10 screenshots (no docs/images/*.png yet)"
fi

echo ""
echo "===== 4/4 frontend/package-lock.json committed (DOC-12 npm ci) ====="

if git ls-files --error-unmatch frontend/package-lock.json >/dev/null 2>&1; then
  echo "  PASS: frontend/package-lock.json is committed"
else
  echo "  FAIL: frontend/package-lock.json is NOT committed — npm ci will not be reproducible"
  fail=1
fi

echo ""
if [[ "$fail" -ne 0 ]]; then
  echo "PHASE 9 DOCS: FAIL"
  exit 1
fi
echo "PHASE 9 DOCS: PASS"
exit 0
