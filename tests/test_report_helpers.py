"""report_helpers のテスト"""
import os
from project_manager import create_project
from report_helpers import latest_report_md, list_phase_reports, save_stream_report


def test_latest_report_md_returns_none_when_no_reports(tmp_projects_dir):
    pid = create_project(name="x", category="autoclave", pb_concept="")
    assert latest_report_md(pid, "3c") is None


def test_save_and_latest(tmp_projects_dir):
    pid = create_project(name="x", category="autoclave", pb_concept="")
    save_stream_report(pid, "3c_test_001", "# foo")
    assert latest_report_md(pid, "3c") == "# foo"


def test_list_phase_reports(tmp_projects_dir):
    pid = create_project(name="x", category="autoclave", pb_concept="")
    save_stream_report(pid, "3c_t1", "a")
    save_stream_report(pid, "ksf_t1", "b")
    out = list_phase_reports(pid)
    assert "3c_t1" in out["3c"]
    assert "ksf_t1" in out["ksf"]
    assert out["stp"] == []
    assert out["4p"] == []
    assert out["finish"] == []


def test_save_stream_report_writes_meta(tmp_projects_dir):
    import json
    pid = create_project(name="x", category="autoclave", pb_concept="")
    save_stream_report(pid, "stp_t1", "# hello", {"extra": "value"})
    meta_path = os.path.join(tmp_projects_dir, pid, "reports", "stp_t1.meta.json")
    assert os.path.exists(meta_path)
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    assert meta["report_id"] == "stp_t1"
    assert meta["char_count"] == len("# hello")
    assert meta["extra"] == "value"


def test_latest_report_md_picks_newest(tmp_projects_dir):
    import time
    pid = create_project(name="x", category="autoclave", pb_concept="")
    save_stream_report(pid, "3c_old", "old content")
    time.sleep(0.05)
    save_stream_report(pid, "3c_new", "new content")
    assert latest_report_md(pid, "3c") == "new content"
