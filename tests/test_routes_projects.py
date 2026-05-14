"""案件管理ルートの統合テスト"""
import json
import pytest


@pytest.fixture
def client(tmp_projects_dir):
    from app import app
    app.config['TESTING'] = True
    return app.test_client()


def test_list_projects_empty(client):
    resp = client.get("/api/projects")
    assert resp.status_code == 200
    assert resp.get_json() == []


def test_create_project_returns_id(client):
    resp = client.post("/api/projects", json={
        "name": "案件X",
        "category": "autoclave",
        "pb_concept": "テスト用",
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["id"].startswith("prj_")


def test_get_project_after_create(client):
    cr = client.post("/api/projects", json={
        "name": "案件Y", "category": "autoclave", "pb_concept": "",
    })
    pid = cr.get_json()["id"]
    resp = client.get(f"/api/projects/{pid}")
    assert resp.status_code == 200
    proj = resp.get_json()
    assert proj["meta"]["name"] == "案件Y"
    assert proj["sources"]["competitor"] == []


def test_post_sources_persists(client):
    cr = client.post("/api/projects", json={
        "name": "z", "category": "autoclave", "pb_concept": "",
    })
    pid = cr.get_json()["id"]
    sources_payload = {
        "asone": {"filter_urls": ["https://axel.as-1.co.jp/x"]},
        "partner": [{"maker": "tomys", "url": "https://t.co/", "models": ["A"]}],
        "competitor": [{"maker": "yamato", "url": "https://y.co/", "models": ["B"]}],
    }
    r = client.post(f"/api/projects/{pid}/sources", json=sources_payload)
    assert r.status_code == 200

    g = client.get(f"/api/projects/{pid}")
    assert g.get_json()["sources"] == sources_payload


def test_get_project_404_when_missing(client):
    resp = client.get("/api/projects/prj_nope")
    assert resp.status_code == 404


def test_path_traversal_returns_404(client):
    """pid に ../ を含むパス攻撃が 404 になる"""
    resp = client.get("/api/projects/..%2F..%2Fetc%2Fpasswd")
    assert resp.status_code == 404


def test_create_project_400_when_name_empty(client):
    resp = client.post("/api/projects", json={
        "name": "", "category": "autoclave", "pb_concept": "",
    })
    assert resp.status_code == 400


def test_create_project_400_when_category_empty(client):
    resp = client.post("/api/projects", json={
        "name": "x", "category": "", "pb_concept": "",
    })
    assert resp.status_code == 400


def test_post_sources_404_when_pid_missing(client):
    r = client.post("/api/projects/prj_nope/sources", json={
        "asone": {"filter_urls": []}, "partner": [], "competitor": [],
    })
    assert r.status_code == 404


def test_get_projects_list_page(client):
    resp = client.get("/projects")
    assert resp.status_code == 200
    assert b"projects_list" in resp.data or b"<html" in resp.data


def test_get_project_new_page(client):
    resp = client.get("/projects/new")
    assert resp.status_code == 200
    assert b"<form" in resp.data


def test_get_project_detail_page(client):
    cr = client.post("/api/projects", json={"name": "x", "category": "autoclave", "pb_concept": ""})
    pid = cr.get_json()["id"]
    resp = client.get(f"/projects/{pid}")
    assert resp.status_code == 200
    assert b"sources" in resp.data.lower() or b"\xe7\xab\xb6\xe5\x90\x88" in resp.data


def test_post_scrape_triggers_scraping(client, monkeypatch):
    cr = client.post("/api/projects", json={
        "name": "z", "category": "autoclave", "pb_concept": "",
    })
    pid = cr.get_json()["id"]
    client.post(f"/api/projects/{pid}/sources", json={
        "asone": {"filter_urls": []}, "partner": [], "competitor": [],
    })
    called = {}
    def mock_run(pid_, async_=True):
        called['pid'] = pid_
        called['async_'] = async_
    monkeypatch.setattr("app.run_scraping", mock_run)
    resp = client.post(f"/api/projects/{pid}/scrape")
    assert resp.status_code == 200
    assert called['pid'] == pid


def test_get_progress(client):
    cr = client.post("/api/projects", json={
        "name": "z", "category": "autoclave", "pb_concept": "",
    })
    pid = cr.get_json()["id"]
    r = client.get(f"/api/projects/{pid}/progress")
    assert r.status_code == 200
    assert r.get_json()["status"] == "pending"


def test_post_report_3c_returns_sse(client, monkeypatch):
    cr = client.post("/api/projects", json={
        "name": "z", "category": "autoclave", "pb_concept": "",
    })
    pid = cr.get_json()["id"]

    def fake_stream(pid_, base_model, save_report=True):
        yield "[META] 3c_test\n"
        yield "Customer "
        yield "セクション。"

    monkeypatch.setattr("app.generate_3c_stream", fake_stream)
    resp = client.post(f"/api/projects/{pid}/reports/3c",
                       json={"base_model": {"maker": "tomys", "model": "X"}})
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Customer" in body
    assert "[META]" in body


def test_delete_project_returns_200_and_removes(client):
    cr = client.post("/api/projects", json={"name": "x", "category": "autoclave", "pb_concept": ""})
    pid = cr.get_json()["id"]
    r = client.delete(f"/api/projects/{pid}")
    assert r.status_code == 200
    g = client.get(f"/api/projects/{pid}")
    assert g.status_code == 404


def test_delete_project_404_when_missing(client):
    r = client.delete("/api/projects/prj_nope")
    assert r.status_code == 404
