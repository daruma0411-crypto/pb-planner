"""pdf_exporter のテスト"""
import os
from pdf_exporter import md_to_pdf


def test_md_to_pdf_creates_pdf_file(tmp_path):
    md = "# Title\n\nHello **world**.\n\n| A | B |\n|---|---|\n| 1 | 2 |\n"
    out = tmp_path / "out.pdf"
    md_to_pdf(md, str(out))
    assert out.exists()
    assert out.stat().st_size > 100
    with open(out, "rb") as f:
        assert f.read(4) == b"%PDF"
