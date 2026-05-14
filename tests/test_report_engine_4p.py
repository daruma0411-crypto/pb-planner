"""4P engine のテスト"""
import pytest
from project_manager import create_project
from report_helpers import save_stream_report
from report_engine_4p import build_4p_prompt, generate_4p_stream


def test_generate_4p_raises_without_3c(tmp_projects_dir):
    pid = create_project(name="x", category="autoclave", pb_concept="")
    with pytest.raises(RuntimeError):
        list(generate_4p_stream(pid))


def test_generate_4p_raises_without_stp(tmp_projects_dir):
    pid = create_project(name="x", category="autoclave", pb_concept="")
    save_stream_report(pid, "3c_seed", "# 3C body")
    save_stream_report(pid, "ksf_seed", "# KSF body")
    with pytest.raises(RuntimeError, match="STP"):
        list(generate_4p_stream(pid))


def test_build_4p_prompt_contains_previous_reports(tmp_projects_dir):
    prompt = build_4p_prompt(
        {"name": "x", "category": "autoclave", "pb_concept": "プロ用"},
        "# 3C content here",
        "# KSF content here",
        "# STP content here",
        {},
    )
    assert "プロダクトマーケター" in prompt
    assert "# 3C content here" in prompt
    assert "# KSF content here" in prompt
    assert "# STP content here" in prompt
    assert "Product" in prompt
    assert "Price" in prompt
    assert "Place" in prompt
    assert "Promotion" in prompt
