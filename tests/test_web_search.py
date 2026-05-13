"""web_search のテスト"""
from web_search import search


def test_search_returns_empty_when_no_api_key(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    results = search("test query", num_results=3)
    assert isinstance(results, list)
    assert results == []


def test_search_returns_list_of_dicts(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "dummy")
    def fake_post(*a, **k):
        class R:
            def raise_for_status(self): pass
            def json(self):
                return {"results": [{"title": "t1", "url": "https://x", "content": "c1"}]}
        return R()
    import web_search
    monkeypatch.setattr(web_search.requests, "post", fake_post)
    results = search("q", num_results=1)
    assert len(results) == 1
    assert results[0]["title"] == "t1"
