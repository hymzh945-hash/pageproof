"""PageProof behaviour tests — the checks must fire on the bundled bad PDF."""

from __future__ import annotations

from pathlib import Path

import pytest

from pageproof import audit, cli, report
from pageproof.licensing import PRODUCT


def _demo(tmp_path: Path) -> Path:
    return cli.demo_pdf(tmp_path / "demo.pdf")


def test_product_name_is_the_licence_scope():
    assert PRODUCT == "pageproof"


def test_demo_pdf_is_flagged(tmp_path):
    result = audit.audit(_demo(tmp_path))
    assert result["pages"] == 5
    assert result["score"] < 60, "a file this broken must not score as print-ready"
    names = {f["check"] for f in result["findings"]}
    for expected in {"mixed_page_size", "mixed_orientation", "no_text_layer", "blank_page",
                     "text_in_trim", "tiny_text", "low_dpi_image", "font_sprawl"}:
        assert expected in names, f"{expected} did not fire"


def test_mixed_page_size_reports_both_geometries(tmp_path):
    result = audit.audit(_demo(tmp_path))
    hit = next(f for f in result["findings"] if f["check"] == "mixed_page_size")
    assert "in against" in hit["detail"]


def test_scanned_page_is_high_severity(tmp_path):
    result = audit.audit(_demo(tmp_path))
    hit = next(f for f in result["findings"] if f["check"] == "no_text_layer")
    assert hit["severity"] == "high"
    assert "OCR" in hit["detail"]


def test_low_dpi_reports_the_number(tmp_path):
    result = audit.audit(_demo(tmp_path))
    hit = next(f for f in result["findings"] if f["check"] == "low_dpi_image")
    assert "DPI" in hit["detail"]


def test_findings_are_deduplicated(tmp_path):
    result = audit.audit(_demo(tmp_path))
    keys = {(f["check"], f["page"], f["target"]) for f in result["findings"]}
    assert len(keys) == len(result["findings"])


def test_rejects_non_pdf(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("hello")
    with pytest.raises(ValueError):
        audit.audit(path)


def test_report_free_tier_locks_findings(tmp_path):
    result = audit.audit(_demo(tmp_path))
    free = report.build(result, pro=False)
    assert "PageProof — document review" in free
    assert "Page-level findings are Pro" in free
    paid = report.build(result, pro=True)
    assert "no_text_layer" in paid
    assert "Page-level findings are Pro" not in paid


def test_summary_rows_add_up(tmp_path):
    result = audit.audit(_demo(tmp_path))
    rows = audit.summary_rows(result)
    assert rows and all(r["count"] > 0 for r in rows)
    assert sum(r["count"] for r in rows) == len(result["findings"])
