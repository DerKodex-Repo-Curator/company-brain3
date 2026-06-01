"""Branded HTML output for generated documents.

Wraps the rendered markdown body inside a minimal but branded HTML
document. The wrapper template lives at ``templates/html-wrapper.html.j2``;
overriding it via ``<vault>/_branding/templates/html-wrapper.html.j2`` lets
a company control the entire page chrome.

The markdown body is converted to HTML via ``markdown-it-py`` (already a
transitive dependency through ``rich``). We enable the GFM-style table
plugin so the MRD's tables render as real HTML tables.

When ``branding.logo_path`` resolves, the logo is encoded as a base64
data URL and threaded into the template as ``logo_data_url``. Embedding
inline keeps the rendered HTML self-contained — a single file that can
be emailed without losing branding — at the cost of size proportional
to the logo. The default scaffold logos are small (< 50 KB), so the
overhead is negligible.
"""

from __future__ import annotations

import base64
from pathlib import Path

from markdown_it import MarkdownIt

from .engine import Branding, build_environment


_LOGO_MIME_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg": "image/svg+xml",
}


def render_html(
    *,
    title: str,
    body_markdown: str,
    branding: Branding,
    vault_path: Path,
) -> str:
    """Render branded HTML around the given markdown body.

    ``vault_path`` is passed in so the Jinja loader can pick up any
    ``_branding/templates/html-wrapper.html.j2`` override the vault provides.
    """

    md = MarkdownIt("commonmark").enable("table")
    body_html = md.render(body_markdown)

    env = build_environment(vault_path)
    template = env.get_template("html-wrapper.html.j2")

    return template.render(
        title=title,
        body_html=body_html,
        branding=branding.as_dict(),
        logo_data_url=_logo_to_data_url(branding.logo_path),
    )


def _logo_to_data_url(logo_path: Path | None) -> str | None:
    """Encode the branding logo as a ``data:`` URL for inline HTML embedding.

    Returns ``None`` when no logo is configured or the file does not
    exist (defensive — :func:`load_branding` already gates on
    existence, but the file could disappear between load and render).
    """

    if logo_path is None or not logo_path.is_file():
        return None
    mime = _LOGO_MIME_BY_SUFFIX.get(logo_path.suffix.lower())
    if mime is None:
        return None
    encoded = base64.b64encode(logo_path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"
