"""The dashboard loads nothing from the internet (security audit F56).

Inter came from Google Fonts on every page load: each viewer's IP and the
dashboard URL went to Google, and the "local-first" dashboard broke offline.
"""

from __future__ import annotations

import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parent.parent / "frontend"


def test_app_html_references_no_remote_urls() -> None:
    html = (FRONTEND / "src" / "app.html").read_text()
    assert not re.search(r"(src|href)=\"https?://", html), "app.html must not load remote assets"


def test_app_html_has_no_inline_script() -> None:
    """Inline scripts in app.html are not covered by SvelteKit's CSP hashes."""
    html = (FRONTEND / "src" / "app.html").read_text()
    assert not re.search(r"<script>(?!\s*</script>)", html)


def test_inter_is_bundled() -> None:
    pkg = (FRONTEND / "package.json").read_text()
    assert "@fontsource/inter" in pkg


def test_sveltekit_emits_a_hash_csp() -> None:
    cfg = (FRONTEND / "vite.config.ts").read_text()
    assert re.search(r"csp:\s*\{[^}]*mode:\s*'hash'", cfg, re.S)
