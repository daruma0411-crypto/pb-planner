"""案件単位スクレイピングのオーケストレータ"""
import json
import os
import sys
import threading
import traceback
from datetime import datetime, timezone, timedelta

import project_manager as _pm


JST = timezone(timedelta(hours=9))


def _now_iso() -> str:
    return datetime.now(JST).isoformat()


def _progress_path(pid: str) -> str:
    return os.path.join(_pm._project_dir(pid), "scraping_progress.json")


def _scraped_dir(pid: str, sub: str) -> str:
    return os.path.join(_pm._project_dir(pid), "scraped", sub)


def _save_progress(pid: str, progress: dict) -> None:
    _pm._atomic_write_json(_progress_path(pid), progress)


def get_progress(pid: str) -> dict:
    path = _progress_path(pid)
    if not os.path.exists(path):
        return {"status": "pending", "items": [], "errors": []}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _scrape_axel(url: str, dest_path: str, **kw) -> int:
    """AS ONE/ナビス AXEL スクレイパー（Task 3.x で実装）"""
    from scripts import scraper_axel
    return scraper_axel.scrape_to_jsonl(url, dest_path)


def _copy_workspace_data(dirname: str, dest_path: str) -> int:
    """workspace/data/<dirname>/products.jsonl を案件 scraped/<...>/products.jsonl にコピー。

    既存スクレイパー（scripts/scraper_*.py）が事前に書き出したデータを
    案件単位 DB に流し込むためのアダプタ。Railway 本番のように live fetch が
    難しい環境でも、ローカルで取得した workspace データを git 経由で配布可能。
    """
    base = os.path.dirname(os.path.abspath(__file__))
    src = os.path.join(base, "workspace", "data", dirname, "products.jsonl")
    if not os.path.exists(src):
        return 0
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    count = 0
    with open(src, encoding="utf-8") as fin, open(dest_path, "w", encoding="utf-8") as fout:
        for line in fin:
            line = line.strip()
            if line:
                fout.write(line + "\n")
                count += 1
    return count


def _yamato_adapter(url, dest_path, models=None):
    n = _copy_workspace_data("yamato_autoclave", dest_path)
    if n > 0:
        return n
    return _generic_via_base(url, dest_path, models)


def _hirayama_adapter(url, dest_path, models=None):
    n = _copy_workspace_data("hirayama_autoclave", dest_path)
    if n > 0:
        return n
    return _generic_via_base(url, dest_path, models)


def _alp_adapter(url, dest_path, models=None):
    n = _copy_workspace_data("alp_autoclave", dest_path)
    if n > 0:
        return n
    return _generic_via_base(url, dest_path, models)


def _tomys_adapter(url, dest_path, models=None):
    n = _copy_workspace_data("tomys_autoclave", dest_path)
    if n > 0:
        return n
    return _generic_via_base(url, dest_path, models)


def _generic_via_base(url, dest_path, models=None):
    """フォールバック: URL を取得して 1 行 JSON で保存"""
    from scripts.scraper_base import fetch
    html = fetch(url)
    if html is None:
        return 0
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with open(dest_path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"maker": "", "model": "", "url": url,
                            "raw_html_len": len(html),
                            "models_requested": models or []},
                           ensure_ascii=False) + "\n")
    return 1


_SCRAPER_REGISTRY = {
    "yamato": _yamato_adapter,
    "hirayama": _hirayama_adapter,
    "alp": _alp_adapter,
    "tomys": _tomys_adapter,
}


def _scrape_url_generic(url: str, dest_path: str, models=None, maker: str = "") -> int:
    fn = _SCRAPER_REGISTRY.get((maker or "").lower())
    if fn:
        return fn(url, dest_path, models=models)
    return _generic_via_base(url, dest_path, models=models)


def run_scraping(pid: str, async_: bool = True) -> None:
    """案件のスクレイピングを実行"""
    proj = _pm.get_project(pid)
    sources = proj["sources"]

    def _worker():
        items: list[dict] = []
        asone_urls = sources.get("asone", {}).get("filter_urls", []) or []
        if asone_urls:
            items.append({"source": "asone", "status": "pending", "count": 0})
        for p in sources.get("partner", []):
            items.append({"source": f"partner:{p['maker']}", "status": "pending", "count": 0})
        for c in sources.get("competitor", []):
            items.append({"source": f"competitor:{c['maker']}", "status": "pending", "count": 0})

        progress = {
            "status": "running",
            "started_at": _now_iso(),
            "items": items,
            "errors": [],
        }
        _save_progress(pid, progress)

        def _mark(name, **patch):
            for it in progress["items"]:
                if it["source"] == name:
                    it.update(patch)
            _save_progress(pid, progress)

        if asone_urls:
            try:
                count = 0
                dest = os.path.join(_scraped_dir(pid, "asone"), "products.jsonl")
                # workspace/data/asone_autoclave/ があればそれを優先（Railway 本番で
                # axel.as-1.co.jp に届かない問題の回避）
                ws_count = _copy_workspace_data("asone_autoclave", dest)
                if ws_count > 0:
                    count = ws_count
                else:
                    for u in asone_urls:
                        count += _scrape_axel(u, dest)
                _mark("asone", status="completed", count=count)
            except Exception as e:
                progress["errors"].append({"source": "asone", "error": str(e), "tb": traceback.format_exc()})
                _mark("asone", status="failed", count=0)

        for p in sources.get("partner", []):
            name = f"partner:{p['maker']}"
            try:
                dest = os.path.join(_scraped_dir(pid, "partner"), f"{p['maker']}.jsonl")
                count = _scrape_url_generic(p["url"], dest, models=p.get("models"), maker=p["maker"])
                _mark(name, status="completed", count=count)
            except Exception as e:
                progress["errors"].append({"source": name, "error": str(e)})
                _mark(name, status="failed", count=0)

        for c in sources.get("competitor", []):
            name = f"competitor:{c['maker']}"
            try:
                dest = os.path.join(_scraped_dir(pid, "competitor"),
                                    c["maker"], "products.jsonl")
                count = _scrape_url_generic(c["url"], dest, models=c.get("models"), maker=c["maker"])
                _mark(name, status="completed", count=count)
            except Exception as e:
                progress["errors"].append({"source": name, "error": str(e)})
                _mark(name, status="failed", count=0)

        progress["status"] = "completed"
        progress["completed_at"] = _now_iso()
        _save_progress(pid, progress)

    if async_:
        t = threading.Thread(target=_worker, daemon=True)
        t.start()
    else:
        _worker()
