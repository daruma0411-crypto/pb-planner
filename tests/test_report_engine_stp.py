"""STP engine のテスト"""
import pytest
from project_manager import create_project
from report_helpers import save_stream_report
from report_engine_stp import build_stp_prompt, generate_stp_stream


def test_generate_stp_raises_without_3c(tmp_projects_dir):
    pid = create_project(name="x", category="autoclave", pb_concept="")
    with pytest.raises(RuntimeError):
        list(generate_stp_stream(pid))


def test_generate_stp_raises_without_ksf(tmp_projects_dir):
    pid = create_project(name="x", category="autoclave", pb_concept="")
    save_stream_report(pid, "3c_seed", "# 3C body")
    with pytest.raises(RuntimeError, match="KSF"):
        list(generate_stp_stream(pid))


def test_build_stp_prompt_contains_previous_reports(tmp_projects_dir):
    prompt = build_stp_prompt(
        {"name": "x", "category": "autoclave", "pb_concept": "プロ用"},
        "# 3C content here",
        "# KSF content here",
        {},
    )
    assert "ブランドコンサル" in prompt
    assert "# 3C content here" in prompt
    assert "# KSF content here" in prompt
    assert "Segmentation" in prompt
    assert "Targeting" in prompt
    assert "Positioning" in prompt
    assert "空白地帯" in prompt
