"""Tests for the html/docx output formats and branding integration (v0.3.0 sub-piece 4)."""

from __future__ import annotations

import base64
from datetime import date
from pathlib import Path

import pytest
from docx import Document

from company_brain.render import render_mrd, render_one_pager
from company_brain.scaffold import scaffold


REPO_ROOT = Path(__file__).parent.parent
MEDDEV_VAULT = REPO_ROOT / "examples" / "meddev-fictional"


# ---------------------------------------------------------------------------
# HTML output
# ---------------------------------------------------------------------------


def test_render_mrd_html_contains_branded_css(tmp_path: Path) -> None:
    out = tmp_path / "mrd.html"
    render_mrd(
        MEDDEV_VAULT,
        output_path=out,
        generation_date=date(2026, 5, 24),
        output_format="html",
    )
    html = out.read_text()
    assert "<!doctype html>" in html
    # The example vault's primary color appears in the CSS root variables.
    assert "--cb-primary: #1f3a5f" in html
    # Page title pulled from doc meta.
    assert "<title>Marketing Requirements Document</title>" in html


def test_render_mrd_html_renders_tables(tmp_path: Path) -> None:
    """GFM table markdown should become <table> elements in HTML."""

    out = tmp_path / "mrd.html"
    render_mrd(
        MEDDEV_VAULT,
        output_path=out,
        generation_date=date(2026, 5, 24),
        output_format="html",
    )
    html = out.read_text()
    assert "<table>" in html
    assert "<th>" in html
    # The sources bibliography is a table.
    assert "fda-510k-summary" in html


def test_render_mrd_html_is_idempotent(tmp_path: Path) -> None:
    a = tmp_path / "a.html"
    b = tmp_path / "b.html"
    pinned = date(2026, 5, 24)
    render_mrd(MEDDEV_VAULT, output_path=a, generation_date=pinned, output_format="html")
    render_mrd(MEDDEV_VAULT, output_path=b, generation_date=pinned, output_format="html")
    assert a.read_bytes() == b.read_bytes()


def test_render_one_pager_html_works(tmp_path: Path) -> None:
    out = tmp_path / "op.html"
    render_one_pager(
        MEDDEV_VAULT,
        output_path=out,
        generation_date=date(2026, 5, 24),
        output_format="html",
    )
    html = out.read_text()
    assert "<title>One-pager</title>" in html


def test_render_one_pager_does_not_support_docx() -> None:
    with pytest.raises(ValueError, match="one-pager"):
        render_one_pager(MEDDEV_VAULT, output_format="docx", write=False)


# ---------------------------------------------------------------------------
# DOCX output
# ---------------------------------------------------------------------------


def test_render_mrd_docx_writes_valid_file(tmp_path: Path) -> None:
    out = tmp_path / "mrd.docx"
    render_mrd(
        MEDDEV_VAULT,
        output_path=out,
        generation_date=date(2026, 5, 24),
        output_format="docx",
    )
    # docx is a zip; python-docx round-trips it.
    doc = Document(out)
    # Should have many paragraphs (headings, body, footers).
    assert len(doc.paragraphs) > 30
    # Should have at least the IFU table, regulatory table, and sources table.
    assert len(doc.tables) >= 3
    # First paragraph is the H1.
    assert doc.paragraphs[0].text == "Marketing Requirements Document"


def test_render_mrd_docx_includes_table_data(tmp_path: Path) -> None:
    """The sources bibliography table should round-trip with its rows."""

    out = tmp_path / "mrd.docx"
    render_mrd(
        MEDDEV_VAULT,
        output_path=out,
        generation_date=date(2026, 5, 24),
        output_format="docx",
    )
    doc = Document(out)
    table_text = "\n".join(
        cell.text
        for table in doc.tables
        for row in table.rows
        for cell in row.cells
    )
    assert "fda-510k-summary" in table_text
    assert "K231234" in table_text


def test_render_mrd_docx_is_byte_identical_on_repeat(tmp_path: Path) -> None:
    """docx is now byte-deterministic when --date is pinned.

    Before this fix only the visible paragraph/table text was equal —
    the underlying zip bytes varied per run because python-docx stamped
    each zip entry with the current local time and the docx core
    properties' `<dcterms:created>` / `<dcterms:modified>` with the
    wall clock. Both are now normalized so the bytes match the
    markdown / html idempotency contract.
    """

    a = tmp_path / "a.docx"
    b = tmp_path / "b.docx"
    pinned = date(2026, 5, 24)
    render_mrd(MEDDEV_VAULT, output_path=a, generation_date=pinned, output_format="docx")
    render_mrd(MEDDEV_VAULT, output_path=b, generation_date=pinned, output_format="docx")
    assert a.read_bytes() == b.read_bytes()


def test_render_mrd_docx_visible_content_equal_too(tmp_path: Path) -> None:
    """Regression guard: visible paragraph and table content stays
    equal across runs (the old contract, kept alongside the new
    byte-equal contract so a hypothetical regression in the
    normalization step that silently smuggles in content drift would
    still surface)."""

    a = tmp_path / "a.docx"
    b = tmp_path / "b.docx"
    pinned = date(2026, 5, 24)
    render_mrd(MEDDEV_VAULT, output_path=a, generation_date=pinned, output_format="docx")
    render_mrd(MEDDEV_VAULT, output_path=b, generation_date=pinned, output_format="docx")

    def extract_text(path: Path) -> tuple[list[str], list[list[str]]]:
        doc = Document(path)
        paragraphs = [p.text for p in doc.paragraphs]
        tables = [
            [cell.text for row in table.rows for cell in row.cells]
            for table in doc.tables
        ]
        return paragraphs, tables

    assert extract_text(a) == extract_text(b)


def test_render_mrd_docx_core_properties_match_generation_date(
    tmp_path: Path,
) -> None:
    """The visible 'Modified' date in Word lines up with the
    generation_date — and with the footer the markdown writer already
    emits — so the docx tells a consistent date story when opened."""

    out = tmp_path / "mrd.docx"
    pinned = date(2026, 5, 24)
    render_mrd(MEDDEV_VAULT, output_path=out, generation_date=pinned, output_format="docx")
    doc = Document(out)
    assert doc.core_properties.modified.date() == pinned
    assert doc.core_properties.created.date() == pinned
    # Author / last_modified_by stable too — would otherwise leak the
    # local OS user account name.
    assert doc.core_properties.author == "company-brain"
    assert doc.core_properties.last_modified_by == "company-brain"


# ---------------------------------------------------------------------------
# Branding integration into HTML
# ---------------------------------------------------------------------------


def test_branded_html_reflects_custom_colors(tmp_path: Path) -> None:
    """Overriding _branding/colors.yaml propagates into the HTML CSS."""

    vault = tmp_path / "vault"
    scaffold(vault, "default", init_git=False)
    branding_dir = vault / "_branding"
    branding_dir.mkdir(exist_ok=True)
    (branding_dir / "colors.yaml").write_text(
        "primary: \"#ff0066\"\nsecondary: \"#003366\"\n", encoding="utf-8"
    )

    out = tmp_path / "mrd.html"
    render_mrd(
        vault,
        output_path=out,
        generation_date=date(2026, 5, 24),
        output_format="html",
    )
    html = out.read_text()
    assert "--cb-primary: #ff0066" in html
    assert "--cb-secondary: #003366" in html


def test_html_wrapper_override_takes_precedence(tmp_path: Path) -> None:
    """Placing html-wrapper.html.j2 under _branding/templates/ wins."""

    vault = tmp_path / "vault"
    scaffold(vault, "default", init_git=False)
    overrides = vault / "_branding" / "templates"
    overrides.mkdir(parents=True, exist_ok=True)
    (overrides / "html-wrapper.html.j2").write_text(
        "<html><head><title>{{ title }}</title></head>"
        "<body><h1>CUSTOM SHELL</h1>{{ body_html }}</body></html>",
        encoding="utf-8",
    )
    out = tmp_path / "mrd.html"
    render_mrd(
        vault,
        output_path=out,
        generation_date=date(2026, 5, 24),
        output_format="html",
    )
    html = out.read_text()
    assert "CUSTOM SHELL" in html


# ---------------------------------------------------------------------------
# CLI surface guards
# ---------------------------------------------------------------------------


def test_render_mrd_rejects_unknown_format() -> None:
    with pytest.raises(ValueError, match="unknown output_format"):
        render_mrd(MEDDEV_VAULT, output_format="pdf", write=False)


# ---------------------------------------------------------------------------
# Branding logo embedding (v0.8.1)
# ---------------------------------------------------------------------------


# A 1x1 transparent PNG (canonical fixture; ~70 bytes). Small enough to keep
# tests fast, real enough that python-docx will round-trip it through the
# zip's media/ folder.
_TINY_PNG = base64.b64decode(
    b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgAAIAAAUAAeImBZsAAAAASUVORK5CYII="
)


def _make_vault_with_logo(tmp_path: Path) -> Path:
    vault = tmp_path / "v"
    scaffold(vault, "default", init_git=False)
    (vault / "_branding" / "logo.png").write_bytes(_TINY_PNG)
    return vault


def test_html_omits_logo_when_no_logo_file(tmp_path: Path) -> None:
    """Baseline: without a logo file the wrapper renders no <img>."""

    vault = tmp_path / "v"
    scaffold(vault, "default", init_git=False)
    out = tmp_path / "mrd.html"
    render_mrd(
        vault,
        output_path=out,
        generation_date=date(2026, 5, 24),
        output_format="html",
    )
    html = out.read_text()
    assert 'class="brand-logo"' not in html
    assert "data:image/png;base64," not in html


def test_html_embeds_logo_as_base64_data_url(tmp_path: Path) -> None:
    vault = _make_vault_with_logo(tmp_path)
    out = tmp_path / "mrd.html"
    render_mrd(
        vault,
        output_path=out,
        generation_date=date(2026, 5, 24),
        output_format="html",
    )
    html = out.read_text()
    assert 'class="brand-logo"' in html
    # The PNG MIME type is in the data URL prefix.
    assert "data:image/png;base64," in html
    # Self-contained — no relative path leaked.
    assert "logo.png" not in html


def test_html_with_logo_is_idempotent(tmp_path: Path) -> None:
    vault = _make_vault_with_logo(tmp_path)
    a = tmp_path / "a.html"
    b = tmp_path / "b.html"
    pinned = date(2026, 5, 24)
    render_mrd(vault, output_path=a, generation_date=pinned, output_format="html")
    render_mrd(vault, output_path=b, generation_date=pinned, output_format="html")
    assert a.read_bytes() == b.read_bytes()


def test_docx_omits_logo_when_no_logo_file(tmp_path: Path) -> None:
    """Baseline: without a logo file the docx zip has no media/ entries."""

    vault = tmp_path / "v"
    scaffold(vault, "default", init_git=False)
    out = tmp_path / "mrd.docx"
    render_mrd(
        vault,
        output_path=out,
        generation_date=date(2026, 5, 24),
        output_format="docx",
    )
    import zipfile

    with zipfile.ZipFile(out) as z:
        media_entries = [n for n in z.namelist() if n.startswith("word/media/")]
    assert media_entries == []


def test_docx_embeds_logo_in_media_folder(tmp_path: Path) -> None:
    vault = _make_vault_with_logo(tmp_path)
    out = tmp_path / "mrd.docx"
    render_mrd(
        vault,
        output_path=out,
        generation_date=date(2026, 5, 24),
        output_format="docx",
    )
    import zipfile

    with zipfile.ZipFile(out) as z:
        media_entries = sorted(n for n in z.namelist() if n.startswith("word/media/"))
        assert len(media_entries) == 1
        # The image bytes round-trip — python-docx stores PNGs uncompressed
        # and the zip's deflate may or may not shrink them, so compare bytes
        # not size.
        assert z.read(media_entries[0]) == _TINY_PNG


def test_docx_with_logo_is_byte_identical_on_repeat(tmp_path: Path) -> None:
    """Embedding a logo must not break the v0.6.0 byte-determinism contract."""

    vault = _make_vault_with_logo(tmp_path)
    a = tmp_path / "a.docx"
    b = tmp_path / "b.docx"
    pinned = date(2026, 5, 24)
    render_mrd(vault, output_path=a, generation_date=pinned, output_format="docx")
    render_mrd(vault, output_path=b, generation_date=pinned, output_format="docx")
    assert a.read_bytes() == b.read_bytes()


def test_docx_with_logo_still_validates_paragraph_structure(tmp_path: Path) -> None:
    """The logo paragraph adds one centered run at the top; the rest of the
    document structure should be unchanged."""

    vault = _make_vault_with_logo(tmp_path)
    out = tmp_path / "mrd.docx"
    render_mrd(
        vault,
        output_path=out,
        generation_date=date(2026, 5, 24),
        output_format="docx",
    )
    doc = Document(out)
    # First paragraph is now the logo (no text), second is the H1 title.
    assert doc.paragraphs[0].text == ""
    assert doc.paragraphs[1].text == "Marketing Requirements Document"
