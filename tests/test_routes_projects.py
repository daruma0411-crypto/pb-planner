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


def test_upload_scraped_asone_json_array(client, tmp_projects_dir):
    cr = client.post("/api/projects", json={"name": "x", "category": "autoclave", "pb_concept": ""})
    pid = cr.get_json()["id"]
    payload = [
        {"maker": "アズワン", "model": "AZ-1", "name": "test1", "price": 50000, "specs": {"容量": "50L"}},
        {"maker": "ナビス", "model": "NV-2", "name": "test2", "price": 80000, "specs": {"容量": "100L"}},
    ]
    r = client.post(f"/api/projects/{pid}/scraped/asone", json=payload)
    assert r.status_code == 200
    body = r.get_json()
    assert body["written"] == 2
    # ファイル検証
    import os, json as J
    dest = os.path.join(tmp_projects_dir, pid, "scraped", "asone", "products.jsonl")
    assert os.path.exists(dest)
    with open(dest, encoding="utf-8") as f:
        lines = [J.loads(l) for l in f if l.strip()]
    assert len(lines) == 2
    assert lines[0]["model"] == "AZ-1"


def test_upload_scraped_competitor_jsonl(client, tmp_projects_dir):
    cr = client.post("/api/projects", json={"name": "x", "category": "autoclave", "pb_concept": ""})
    pid = cr.get_json()["id"]
    jsonl_body = '\n'.join([
        '{"maker":"yamato","model":"SX-700","name":"y1"}',
        '{"maker":"yamato","model":"SX-300","name":"y2"}',
    ])
    r = client.post(f"/api/projects/{pid}/scraped/competitor:yamato",
                    data=jsonl_body, headers={"Content-Type": "text/plain"})
    assert r.status_code == 200
    assert r.get_json()["written"] == 2


def test_upload_scraped_invalid_bucket_returns_400(client, tmp_projects_dir):
    cr = client.post("/api/projects", json={"name": "x", "category": "autoclave", "pb_concept": ""})
    pid = cr.get_json()["id"]
    # 不正な bucket 名 (regex に通らない) は 400 を返す
    # path-traversal (../) は Werkzeug が URL 正規化で吸収するため別 path に到達
    # する(=ルーティングレベルで防げる)。endpoint まで届く無効値は regex で弾く。
    r = client.post(f"/api/projects/{pid}/scraped/unknown_bucket", json=[])
    assert r.status_code == 400


def test_upload_scraped_404_when_pid_missing(client):
    r = client.post("/api/projects/prj_nope/scraped/asone", json=[])
    assert r.status_code == 404


def test_chat_history_empty_when_no_chat(client):
    cr = client.post("/api/projects", json={"name": "x", "category": "autoclave", "pb_concept": ""})
    pid = cr.get_json()["id"]
    r = client.get(f"/api/projects/{pid}/chat/history")
    assert r.status_code == 200
    assert r.get_json()["history"] == []


def test_chat_history_404_when_pid_missing(client):
    r = client.get("/api/projects/prj_nope/chat/history")
    assert r.status_code == 404


def test_chat_post_400_when_message_empty(client):
    cr = client.post("/api/projects", json={"name": "x", "category": "autoclave", "pb_concept": ""})
    pid = cr.get_json()["id"]
    r = client.post(f"/api/projects/{pid}/chat", json={"message": ""})
    assert r.status_code == 400


def test_chat_post_streams_response(client, monkeypatch):
    cr = client.post("/api/projects", json={"name": "x", "category": "autoclave", "pb_concept": ""})
    pid = cr.get_json()["id"]

    class FakeStream:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        @property
        def text_stream(self):
            return iter(["こんにちは", "、テスト応答です"])

    class FakeMessages:
        def stream(self, **kw): return FakeStream()

    class FakeClient:
        def __init__(self): self.messages = FakeMessages()

    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", lambda: FakeClient())

    r = client.post(f"/api/projects/{pid}/chat", json={"message": "テスト質問"})
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "こんにちは" in body
    assert "done" in body


def test_chat_delete_clears_history(client, tmp_projects_dir):
    cr = client.post("/api/projects", json={"name": "x", "category": "autoclave", "pb_concept": ""})
    pid = cr.get_json()["id"]
    # 履歴ファイル作成
    import os, json as J
    chat_path = os.path.join(tmp_projects_dir, pid, "chat.jsonl")
    with open(chat_path, "w", encoding="utf-8") as f:
        f.write(J.dumps({"role": "user", "content": "x"}, ensure_ascii=False) + "\n")
    r = client.delete(f"/api/projects/{pid}/chat")
    assert r.status_code == 200
    assert not os.path.exists(chat_path)
