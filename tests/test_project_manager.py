"""project_manager のテスト"""
import json
import os
import pytest
from project_manager import (
    create_project, get_project, list_projects,
    add_or_replace_sources, ProjectNotFound,
)


def test_create_project_returns_id_and_persists_meta(tmp_projects_dir):
    pid = create_project(
        name="テスト案件A",
        category="autoclave",
        pb_concept="女性向け 100L",
    )
    assert pid.startswith("prj_")
    meta_path = os.path.join(tmp_projects_dir, pid, "meta.json")
    assert os.path.exists(meta_path)
    meta = json.load(open(meta_path, encoding="utf-8"))
    assert meta["name"] == "テスト案件A"
    assert meta["category"] == "autoclave"
    assert meta["pb_concept"] == "女性向け 100L"


def test_get_project_returns_meta(tmp_projects_dir):
    pid = create_project(name="x", category="autoclave", pb_concept="y")
    proj = get_project(pid)
    assert proj["meta"]["id"] == pid
    assert proj["sources"] == {"asone": {"filter_urls": []},
                                "partner": [], "competitor": []}


def test_get_project_raises_when_missing(tmp_projects_dir):
    with pytest.raises(ProjectNotFound):
        get_project("prj_does_not_exist")


def test_list_projects_returns_all_meta(tmp_projects_dir):
    create_project(name="A", category="autoclave", pb_concept="")
    create_project(name="B", category="centrifuge", pb_concept="")
    items = list_projects()
    assert len(items) == 2
    names = sorted([p["name"] for p in items])
    assert names == ["A", "B"]


def test_add_or_replace_sources_persists(tmp_projects_dir):
    pid = create_project(name="x", category="autoclave", pb_concept="")
    sources = {
        "asone": {"filter_urls": ["https://axel.as-1.co.jp/c/sterilization?maker=AS_ONE,NAVIS"]},
        "partner": [
            {"maker": "tomys", "url": "https://www.tomys.co.jp/", "models": ["FLS-1000"]}
        ],
        "competitor": [
            {"maker": "yamato", "url": "https://www.yamato-net.co.jp/", "models": ["SX-700"]},
        ],
    }
    add_or_replace_sources(pid, sources)
    proj = get_project(pid)
    assert proj["sources"] == sources


def test_delete_project_removes_directory(tmp_projects_dir):
    pid = create_project(name="x", category="autoclave", pb_concept="")
    import os
    assert os.path.exists(os.path.join(tmp_projects_dir, pid))
    from project_manager import delete_project
    delete_project(pid)
    assert not os.path.exists(os.path.join(tmp_projects_dir, pid))


def test_delete_project_raises_when_missing(tmp_projects_dir):
    from project_manager import delete_project
    with pytest.raises(ProjectNotFound):
        delete_project("prj_nope")
