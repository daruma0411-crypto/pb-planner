"""Web 検索ラッパー（Tavily 優先、API キー無しは空結果）"""
import os
import requests


TAVILY_ENDPOINT = "https://api.tavily.com/search"


def search(query: str, num_results: int = 5) -> list[dict]:
    """検索結果を [{title, url, content}, ...] で返す。
    TAVILY_API_KEY が無い場合は空配列。
    """
    api_key = os.environ.get("TAVILY_API_KEY", "").strip()
    if not api_key:
        return []
    try:
        resp = requests.post(
            TAVILY_ENDPOINT,
            json={
                "api_key": api_key,
                "query": query,
                "max_results": num_results,
                "search_depth": "basic",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return [{"title": r.get("title", ""),
                 "url": r.get("url", ""),
                 "content": r.get("content", "")}
                for r in data.get("results", [])]
    except Exception:
        return []
