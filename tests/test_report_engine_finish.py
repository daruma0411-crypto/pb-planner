"""Finish (キャッチ+マスタ) engine のテスト"""
import pytest
from project_manager import create_project
from report_helpers import save_stream_report
from report_engine_finish import build_finish_prompt, generate_finish_stream


def test_generate_finish_raises_without_3c(tmp_projects_dir):
    pid = create_project(name="x", category="autoclave", pb_concept="")
    with pytest.raises(RuntimeError):
        list(generate_finish_stream(pid))


def test_generate_finish_raises_without_4p(tmp_projects_dir):
    pid = create_project(name="x", category="autoclave", pb_concept="")
    save_stream_report(pid, "3c_seed", "# 3C body")
    save_stream_report(pid, "ksf_seed", "# KSF body")
    save_stream_report(pid, "stp_seed", "# STP body")
    with pytest.raises(RuntimeError, match="4P"):
        list(generate_finish_stream(pid))


def test_build_finish_prompt_contains_all_previous(tmp_projects_dir):
    prompt = build_finish_prompt(
        {"name": "x", "category": "autoclave", "pb_concept": "プロ用"},
        "# 3C content here",
        "# KSF content here",
        "# STP content here",
        "# 4P content here",
        {},
    )
    assert "コピーライター" in prompt
    assert "PIM" in prompt
    assert "# 3C content here" in prompt
    assert "# KSF content here" in prompt
    assert "# STP content here" in prompt
    assert "# 4P content here" in prompt
    assert "キャッチコピー" in prompt
    assert "商品マスタ" in prompt
    assert "asone_part_no" in prompt
