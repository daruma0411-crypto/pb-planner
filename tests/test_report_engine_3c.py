"""report_engine_3c のテスト"""
import json
import os
import pytest
from project_manager import create_project, add_or_replace_sources
from report_engine_3c import (
    build_prompt, generate_3c_stream, load_project_data,
)


def _seed_project(tmp_dir, pid):
    """テスト用に scraped/ 配下に最小データを書き込む"""
    proj_dir = os.path.join(tmp_dir, pid)
    for sub in [("asone",), ("partner",), ("competitor", "yamato")]:
        d = os.path.join(proj_dir, "scraped", *sub)
        os.makedirs(d, exist_ok=True)
        if sub == ("partner",):
            path = os.path.join(d, "tomys.jsonl")
        else:
            path = os.path.join(d, "products.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "maker": "/".join(sub), "model": "MDL-1",
                "name": "test", "price": 100000, "specs": {"容量": "50L"},
            }, ensure_ascii=False) + "\n")


def test_load_project_data_aggregates_scraped(tmp_projects_dir):
    pid = create_project(name="x", category="autoclave", pb_concept="")
    _seed_project(tmp_projects_dir, pid)
    data = load_project_data(pid)
    assert "asone" in data
    assert "partner" in data
    assert "competitor" in data
    assert len(data["asone"]) == 1
    assert "yamato" in data["competitor"]
    assert len(data["competitor"]["yamato"]) == 1


def test_build_prompt_contains_required_sections(tmp_projects_dir):
    pid = create_project(name="x", category="autoclave", pb_concept="女性向け")
    _seed_project(tmp_projects_dir, pid)
    data = load_project_data(pid)
    prompt = build_prompt(meta={"name": "x", "category": "autoclave", "pb_concept": "女性向け"},
                          base_model={"maker": "tomys", "model": "MDL-1"},
                          data=data, web_results=[])
    assert "Customer" in prompt
    assert "Competitor" in prompt
    assert "Company" in prompt
    assert "アズワン PB" in prompt or "AS ONE" in prompt
    assert "MDL-1" in prompt


def test_generate_3c_stream_yields_chunks(tmp_projects_dir, monkeypatch):
    """Anthropic クライアントをモックしてストリーミング動作を確認"""
    pid = create_project(name="x", category="autoclave", pb_concept="")
    _seed_project(tmp_projects_dir, pid)

    class FakeStream:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        @property
        def text_stream(self):
            return iter(["Customer ", "セクション。", "Competitor "])

    class FakeMessages:
        def stream(self, **kw): return FakeStream()

    class FakeClient:
        def __init__(self, *a, **kw): self.messages = FakeMessages()

    import report_engine_3c
    monkeypatch.setattr(report_engine_3c, "Anthropic", FakeClient)

    chunks = list(generate_3c_stream(pid, base_model={"maker": "tomys", "model": "MDL-1"}))
    text = "".join(c for c in chunks if not c.startswith("[META]"))
    assert "Customer" in text
    assert "Competitor" in text
