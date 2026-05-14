"""KSF engine のテスト"""
import pytest
from project_manager import create_project
from report_helpers import save_stream_report
from report_engine_ksf import build_ksf_prompt, generate_ksf_stream


def test_generate_ksf_raises_without_3c(tmp_projects_dir):
    pid = create_project(name="x", category="autoclave", pb_concept="")
    with pytest.raises(RuntimeError):
        list(generate_ksf_stream(pid))


def test_build_ksf_prompt_contains_3c_content(tmp_projects_dir):
    pid = create_project(name="x", category="autoclave", pb_concept="女性向け")
    three_c = "# 3C 抜粋"
    prompt = build_ksf_prompt({"name": "x", "category": "autoclave", "pb_concept": "女性向け"},
                              three_c, {"pos": {"summary_note": "POS sample"}, "sns": {}})
    assert "シニアマーケター" in prompt
    assert "# 3C 抜粋" in prompt
    assert "POS sample" in prompt
    assert "ペイン" in prompt
