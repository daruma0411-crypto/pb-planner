"""E2E スモーク: 案件作成 → ソース登録 → スクレイピング → レポート生成"""
import json
import os
import pytest


@pytest.fixture
def client(tmp_projects_dir):
    from app import app
    app.config['TESTING'] = True
    return app.test_client()


def _can_pdf():
    try:
        from weasyprint import HTML  # noqa
        return True
    except (OSError, ImportError):
        return False


def test_full_flow_with_mocked_external_calls(client, tmp_projects_dir, monkeypatch):
    # 外部依存をすべてモック化

    # 1. AXEL スクレイパー -> ダミー商品 1 件書き込み
    def fake_axel(url, dest):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8") as f:
            f.write(json.dumps({"maker": "アズワン", "model": "PB-1",
                                "specs": {"容量": "50L"}, "price": 500000},
                               ensure_ascii=False) + "\n")
        return 1
    import scraper_orchestrator as so
    monkeypatch.setattr(so, "_scrape_axel", fake_axel)
    # 既存メーカーのレジストリも空にして全部フォールバック化
    monkeypatch.setattr(so, "_SCRAPER_REGISTRY", {})

    # 2. scraper_base.fetch -> ダミー HTML
    def fake_fetch(url, **kw):
        return "<html><body><h1>Dummy</h1></body></html>"
    monkeypatch.setattr("scripts.scraper_base.fetch", fake_fetch)

    # 3. Anthropic SDK -> モック
    class FakeStream:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        @property
        def text_stream(self):
            return iter(["# 3C\n## Customer\n本文。\n## Competitor\n本文。\n## Company\n本文。"])
    class FakeMsgs:
        def stream(self, **kw): return FakeStream()
    class FakeClient:
        def __init__(self): self.messages = FakeMsgs()
    import report_engine_3c
    monkeypatch.setattr(report_engine_3c, "Anthropic", lambda: FakeClient())

    # --- フロー実行 ---

    # 1. 案件作成
    cr = client.post("/api/projects", json={
        "name": "E2E案件", "category": "autoclave", "pb_concept": "テスト",
    })
    assert cr.status_code == 200
    pid = cr.get_json()["id"]

    # 2. ソース登録
    src_resp = client.post(f"/api/projects/{pid}/sources", json={
        "asone": {"filter_urls": ["https://axel.as-1.co.jp/sample"]},
        "partner": [{"maker": "tomys", "url": "https://t.co/", "models": ["FLS-1000"]}],
        "competitor": [{"maker": "yamato", "url": "https://y.co/", "models": ["SX-700"]}],
    })
    assert src_resp.status_code == 200

    # 3. スクレイピング（同期実行）
    so.run_scraping(pid, async_=False)
    p_resp = client.get(f"/api/projects/{pid}/progress")
    assert p_resp.status_code == 200
    p = p_resp.get_json()
    assert p["status"] == "completed"

    # 4. 3C レポート生成（SSE）
    resp = client.post(f"/api/projects/{pid}/reports/3c",
                       json={"base_model": {"maker": "tomys", "model": "FLS-1000"}})
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Customer" in body

    # report_id 抽出
    rid = None
    for line in body.split("\n"):
        if "[META]" in line:
            payload = line.replace("data:", "").strip()
            obj = json.loads(payload)
            rid = obj["text"].replace("[META]", "").strip()
            break
    assert rid is not None

    # 5. PDF エクスポート (WeasyPrint 利用可能時のみ)
    if _can_pdf():
        pdf_resp = client.get(f"/api/projects/{pid}/reports/{rid}/pdf")
        assert pdf_resp.status_code == 200
        assert pdf_resp.data[:4] == b"%PDF"
