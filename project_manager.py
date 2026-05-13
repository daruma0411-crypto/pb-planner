"""案件 CRUD・ソース管理"""
import json
import os
import uuid
from datetime import datetime, timezone, timedelta


JST = timezone(timedelta(hours=9))


class ProjectNotFound(Exception):
    pass


def _projects_root() -> str:
    """テスト時は環境変数で上書き可能"""
    return os.environ.get(
        'PB_PROJECTS_DIR',
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'projects')
    )


def _now_iso() -> str:
    return datetime.now(JST).isoformat()


def _new_id() -> str:
    ts = datetime.now(JST).strftime("%Y%m%d_%H%M%S")
    suffix = uuid.uuid4().hex[:6]
    return f"prj_{ts}_{suffix}"


def _project_dir(pid: str) -> str:
    return os.path.join(_projects_root(), pid)


def _empty_sources() -> dict:
    return {"asone": {"filter_urls": []}, "partner": [], "competitor": []}


def _atomic_write_json(path: str, obj: dict) -> None:
    """tempfile + os.replace でアトミック書き込み（gunicorn マルチワーカー対策）"""
    tmp = f"{path}.tmp.{uuid.uuid4().hex[:6]}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def create_project(name: str, category: str, pb_concept: str) -> str:
    pid = _new_id()
    pdir = _project_dir(pid)
    os.makedirs(pdir, exist_ok=True)
    meta = {
        "id": pid,
        "name": name,
        "category": category,
        "pb_concept": pb_concept,
        "base_model_candidates": [],
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    _atomic_write_json(os.path.join(pdir, "meta.json"), meta)
    _atomic_write_json(os.path.join(pdir, "sources.json"), _empty_sources())
    return pid


def get_project(pid: str) -> dict:
    pdir = _project_dir(pid)
    if not os.path.exists(pdir):
        raise ProjectNotFound(pid)
    try:
        with open(os.path.join(pdir, "meta.json"), encoding="utf-8") as f:
            meta = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        raise ProjectNotFound(pid) from e
    spath = os.path.join(pdir, "sources.json")
    if os.path.exists(spath):
        try:
            with open(spath, encoding="utf-8") as f:
                sources = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            sources = _empty_sources()
    else:
        sources = _empty_sources()
    return {"meta": meta, "sources": sources}


def list_projects() -> list[dict]:
    root = _projects_root()
    if not os.path.exists(root):
        return []
    out = []
    for entry in sorted(os.listdir(root)):
        meta_path = os.path.join(root, entry, "meta.json")
        if os.path.exists(meta_path):
            try:
                with open(meta_path, encoding="utf-8") as f:
                    out.append(json.load(f))
            except (FileNotFoundError, json.JSONDecodeError):
                continue
    return out


def add_or_replace_sources(pid: str, sources: dict) -> None:
    pdir = _project_dir(pid)
    if not os.path.exists(pdir):
        raise ProjectNotFound(pid)
    spath = os.path.join(pdir, "sources.json")
    _atomic_write_json(spath, sources)
    mpath = os.path.join(pdir, "meta.json")
    with open(mpath, encoding="utf-8") as f:
        meta = json.load(f)
    meta["updated_at"] = _now_iso()
    _atomic_write_json(mpath, meta)
