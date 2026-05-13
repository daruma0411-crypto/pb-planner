"""scraper_orchestrator のテスト"""
import json
import os
import pytest
from project_manager import create_project, add_or_replace_sources
from scraper_orchestrator import run_scraping, get_progress


def test_run_scraping_creates_progress_file(tmp_projects_dir, monkeypatch):
    calls = []
    def fake_scrape(url, dest_path, **kw):
        calls.append((url, dest_path))
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"maker": "fake", "model": "M1"}, ensure_ascii=False) + "\n")
        return 1

    import scraper_orchestrator as so
    monkeypatch.setattr(so, "_scrape_axel", fake_scrape)
    monkeypatch.setattr(so, "_scrape_url_generic", fake_scrape)

    pid = create_project(name="t", category="autoclave", pb_concept="")
    add_or_replace_sources(pid, {
        "asone": {"filter_urls": ["https://axel.as-1.co.jp/x"]},
        "partner": [{"maker": "tomys", "url": "https://t.co/", "models": []}],
        "competitor": [{"maker": "yamato", "url": "https://y.co/", "models": []}],
    })
    run_scraping(pid, async_=False)
    progress = get_progress(pid)
    assert progress["status"] == "completed"
    statuses = {item["source"]: item["status"] for item in progress["items"]}
    assert statuses["asone"] == "completed"
    assert statuses["partner:tomys"] == "completed"
    assert statuses["competitor:yamato"] == "completed"
    asone_path = os.path.join(tmp_projects_dir, pid, "scraped", "asone", "products.jsonl")
    assert os.path.exists(asone_path)


def test_get_progress_returns_pending_when_never_run(tmp_projects_dir):
    pid = create_project(name="t", category="autoclave", pb_concept="")
    p = get_progress(pid)
    assert p["status"] == "pending"


def test_competitor_yamato_dispatches_existing_scraper(tmp_projects_dir, monkeypatch):
    pid = create_project(name="t", category="autoclave", pb_concept="")
    add_or_replace_sources(pid, {
        "asone": {"filter_urls": []},
        "partner": [],
        "competitor": [{"maker": "yamato",
                        "url": "https://www.yamato-net.co.jp/",
                        "models": ["SX-700"]}],
    })

    called = {}
    def fake_yamato(url, dest_path, models=None):
        called['args'] = (url, dest_path, models)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"maker": "yamato", "model": "SX-700"}, ensure_ascii=False) + "\n")
        return 1

    import scraper_orchestrator as so
    monkeypatch.setattr(so, "_SCRAPER_REGISTRY", {"yamato": fake_yamato,
                                                  "hirayama": fake_yamato,
                                                  "alp": fake_yamato})
    run_scraping(pid, async_=False)
    p = get_progress(pid)
    assert p["status"] == "completed"
    assert called['args'][0] == "https://www.yamato-net.co.jp/"
