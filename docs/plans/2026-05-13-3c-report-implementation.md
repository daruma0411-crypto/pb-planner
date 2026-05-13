# 機種選択 → 3C 一発レポート 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PB企画プランナーに「案件作成 → 競合/自社/パートナーをスクレイピング → Claude Opus 4.7 で 3C レポートを一発生成 → PDF エクスポート」までの専用ワークフローを追加する。

**Architecture:** 既存の Flask `app.py` を維持したまま新規モジュール（project_manager / scraper_orchestrator / report_engine_3c / web_search / pdf_exporter）と新規ルートを追加する。データは `projects/<id>/` ディレクトリに案件単位で格納。スクレイピングは既存 `scraper_base.fetch()` を再利用しつつ AS ONE/ナビス 用スクレイパーを新規追加。レポート生成は Claude SDK のストリーミング呼び出しを SSE で中継し、フロント Markdown レンダリング → PDF エクスポートまで段階的に出す。

**Tech Stack:** Python 3.11+ / Flask 3 / anthropic SDK / BeautifulSoup4 / Tavily API or Brave Search MCP / WeasyPrint / pytest / SSE

**Spec:** [2026-05-13-3c-report-design.md](2026-05-13-3c-report-design.md)

---

## File Structure（事前マップ）

### 新規作成
- `project_manager.py` — 案件 CRUD・ソース管理（責務: meta/sources.json の I/O のみ）
- `scraper_orchestrator.py` — 案件単位スクレイピング実行・進捗管理
- `scripts/scraper_axel.py` — AS ONE/ナビス AXEL スクレイパー
- `web_search.py` — Tavily 第一候補のフォールバック付きラッパー
- `report_engine_3c.py` — 3C レポート生成（プロンプト構築 + Claude ストリーミング）
- `pdf_exporter.py` — Markdown → PDF
- `templates/projects_list.html` — 案件一覧
- `templates/project_new.html` — 案件作成フォーム
- `templates/project_detail.html` — 案件詳細・ソース管理・スクレイピング起動
- `templates/report_3c.html` — レポート画面（SSE 受信）
- `tests/__init__.py`
- `tests/conftest.py` — pytest 共通フィクスチャ
- `tests/test_project_manager.py`
- `tests/test_scraper_orchestrator.py`
- `tests/test_scraper_axel.py`
- `tests/test_web_search.py`
- `tests/test_report_engine_3c.py`
- `tests/test_pdf_exporter.py`
- `tests/test_routes_projects.py`
- `tests/fixtures/axel_list_sample.html`
- `tests/fixtures/axel_detail_sample.html`
- `pytest.ini`

### 変更
- `app.py` — 新規ルート群追加（既存ルートには触らない）
- `requirements.txt` — pytest, weasyprint, tavily-python を追加

---

## 共通ルール

- **TDD**: 各機能は失敗するテスト → 実装 → 緑 → コミット
- **コミット粒度**: 1 タスク = 1 コミット（テストと実装は同一コミット OK）
- **既存コードに触らない**: app.py の既存ルート・FC ツール定義には絶対触らない。新規ルートのみ追加
- **テスト実行**: `cd pb-planner && pytest tests/test_xxx.py -v`
- **編集対象パス**: 全て `pb-planner/` 配下が起点（以下の `path` は pb-planner 相対）

---

## Phase 0: 環境準備

### Task 0.1: pytest セットアップ

**Files:**
- Create: `pytest.ini`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Modify: `requirements.txt`

- [ ] **Step 1: requirements.txt に追加**

`requirements.txt` の末尾に追加：
```
# ── Testing ─────────────────────────────────────
pytest>=8.0.0
pytest-mock>=3.12.0

# ── PDF ─────────────────────────────────────────
weasyprint>=62.0
markdown>=3.5.0

# ── Web Search ──────────────────────────────────
tavily-python>=0.5.0
```

- [ ] **Step 2: pytest.ini 作成**

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -v --tb=short
```

- [ ] **Step 3: tests/__init__.py 作成（空ファイル）**

- [ ] **Step 4: tests/conftest.py 作成**

```python
"""pytest 共通フィクスチャ"""
import os
import shutil
import tempfile
import pytest


@pytest.fixture
def tmp_projects_dir(monkeypatch):
    """テスト用に projects/ を一時ディレクトリに切り替える"""
    tmp = tempfile.mkdtemp(prefix='pb_test_')
    monkeypatch.setenv('PB_PROJECTS_DIR', tmp)
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)
```

- [ ] **Step 5: pip インストールと動作確認**

Run: `cd pb-planner && pip install -r requirements.txt && pytest --version`
Expected: pytest 8.x.x 表示

- [ ] **Step 6: コミット**

```bash
cd pb-planner
git add requirements.txt pytest.ini tests/__init__.py tests/conftest.py
git commit -m "chore: pytest/weasyprint/tavily 依存を追加し tests/ を新設"
```

---

## Phase 1: 案件 CRUD

### Task 1.1: project_manager.py コア機能

**Files:**
- Create: `project_manager.py`
- Create: `tests/test_project_manager.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_project_manager.py`:
```python
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
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `cd pb-planner && pytest tests/test_project_manager.py -v`
Expected: ModuleNotFoundError: No module named 'project_manager'

- [ ] **Step 3: project_manager.py を実装**

`pb-planner/project_manager.py`:
```python
"""案件 CRUD・ソース管理"""
import json
import os
import time
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
    with open(os.path.join(pdir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    with open(os.path.join(pdir, "sources.json"), "w", encoding="utf-8") as f:
        json.dump(_empty_sources(), f, ensure_ascii=False, indent=2)
    return pid


def get_project(pid: str) -> dict:
    pdir = _project_dir(pid)
    if not os.path.exists(pdir):
        raise ProjectNotFound(pid)
    with open(os.path.join(pdir, "meta.json"), encoding="utf-8") as f:
        meta = json.load(f)
    spath = os.path.join(pdir, "sources.json")
    if os.path.exists(spath):
        with open(spath, encoding="utf-8") as f:
            sources = json.load(f)
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
            with open(meta_path, encoding="utf-8") as f:
                out.append(json.load(f))
    return out


def add_or_replace_sources(pid: str, sources: dict) -> None:
    pdir = _project_dir(pid)
    if not os.path.exists(pdir):
        raise ProjectNotFound(pid)
    spath = os.path.join(pdir, "sources.json")
    with open(spath, "w", encoding="utf-8") as f:
        json.dump(sources, f, ensure_ascii=False, indent=2)
    # touch meta.updated_at
    mpath = os.path.join(pdir, "meta.json")
    with open(mpath, encoding="utf-8") as f:
        meta = json.load(f)
    meta["updated_at"] = _now_iso()
    with open(mpath, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
```

- [ ] **Step 4: テストが通ることを確認**

Run: `cd pb-planner && pytest tests/test_project_manager.py -v`
Expected: 全 5 件 PASSED

- [ ] **Step 5: コミット**

```bash
cd pb-planner
git add project_manager.py tests/test_project_manager.py
git commit -m "feat(project_manager): 案件 CRUD・ソース管理を追加"
```

---

### Task 1.2: 案件管理 Flask ルート

**Files:**
- Modify: `app.py`（末尾に新規ルート群を追加。既存ルートには触らない）
- Create: `tests/test_routes_projects.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_routes_projects.py`:
```python
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
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `cd pb-planner && pytest tests/test_routes_projects.py -v`
Expected: 404 や AttributeError 等で全件 FAIL

- [ ] **Step 3: app.py に新規ルートを追加**

`pb-planner/app.py` の **末尾** に追加（既存 `if __name__ == '__main__':` の手前）：

```python
# ================================================================
# 案件管理ルート（新機能: 機種選択→3C 一発レポート）
# ================================================================
import project_manager as _pm


@app.route('/api/projects', methods=['GET'])
def api_list_projects():
    return jsonify(_pm.list_projects())


@app.route('/api/projects', methods=['POST'])
def api_create_project():
    data = request.get_json(force=True) or {}
    name = (data.get('name') or '').strip()
    category = (data.get('category') or '').strip()
    pb_concept = (data.get('pb_concept') or '').strip()
    if not name or not category:
        return jsonify({"error": "name と category は必須"}), 400
    pid = _pm.create_project(name=name, category=category, pb_concept=pb_concept)
    return jsonify({"id": pid})


@app.route('/api/projects/<pid>', methods=['GET'])
def api_get_project(pid):
    try:
        return jsonify(_pm.get_project(pid))
    except _pm.ProjectNotFound:
        return jsonify({"error": "not found"}), 404


@app.route('/api/projects/<pid>/sources', methods=['POST'])
def api_post_sources(pid):
    sources = request.get_json(force=True) or {}
    try:
        _pm.add_or_replace_sources(pid, sources)
        return jsonify({"ok": True})
    except _pm.ProjectNotFound:
        return jsonify({"error": "not found"}), 404
```

- [ ] **Step 4: テストが通ることを確認**

Run: `cd pb-planner && pytest tests/test_routes_projects.py -v`
Expected: 全 5 件 PASSED

- [ ] **Step 5: コミット**

```bash
cd pb-planner
git add app.py tests/test_routes_projects.py
git commit -m "feat(app): 案件管理 API (/api/projects 系) を追加"
```

---

### Task 1.3: 案件作成フォーム UI

**Files:**
- Create: `templates/projects_list.html`
- Create: `templates/project_new.html`
- Modify: `app.py`（HTML を返すルート 2 本を追加）

- [ ] **Step 1: テスト書く**

`tests/test_routes_projects.py` の末尾に追加：
```python
def test_get_projects_list_page(client):
    resp = client.get("/projects")
    assert resp.status_code == 200
    assert b"projects_list" in resp.data or b"<html" in resp.data


def test_get_project_new_page(client):
    resp = client.get("/projects/new")
    assert resp.status_code == 200
    assert b"<form" in resp.data
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `cd pb-planner && pytest tests/test_routes_projects.py::test_get_projects_list_page tests/test_routes_projects.py::test_get_project_new_page -v`
Expected: 404 で FAIL

- [ ] **Step 3: templates/projects_list.html 作成**

```html
<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>案件一覧 — PB企画プランナー</title>
<style>
body { font-family: -apple-system, "Segoe UI", sans-serif; max-width: 960px; margin: 2em auto; padding: 0 1em; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #ddd; padding: 0.6em; text-align: left; }
th { background: #f5f5f5; }
a.btn { display: inline-block; padding: 0.5em 1em; background: #2a7; color: #fff; text-decoration: none; border-radius: 4px; }
</style>
</head>
<body>
<h1>案件一覧</h1>
<p><a class="btn" href="/projects/new">+ 新規案件</a> &nbsp; <a href="/">← チャット UI へ</a></p>
<table id="projects_list">
  <thead><tr><th>名前</th><th>カテゴリ</th><th>作成日</th><th></th></tr></thead>
  <tbody id="tbody"></tbody>
</table>
<script>
fetch('/api/projects').then(r => r.json()).then(items => {
  const tb = document.getElementById('tbody');
  if (items.length === 0) {
    tb.innerHTML = '<tr><td colspan="4">案件がありません</td></tr>';
    return;
  }
  tb.innerHTML = items.map(p =>
    `<tr><td>${p.name}</td><td>${p.category}</td><td>${p.created_at.slice(0, 10)}</td>
     <td><a href="/projects/${p.id}">詳細 →</a></td></tr>`
  ).join('');
});
</script>
</body>
</html>
```

- [ ] **Step 4: templates/project_new.html 作成**

```html
<!DOCTYPE html>
<html lang="ja">
<head><meta charset="utf-8"><title>新規案件 — PB企画プランナー</title>
<style>
body { font-family: -apple-system, "Segoe UI", sans-serif; max-width: 720px; margin: 2em auto; padding: 0 1em; }
label { display: block; margin: 1em 0 0.3em; font-weight: 600; }
input, select, textarea { width: 100%; padding: 0.5em; box-sizing: border-box; font-size: 1em; }
button { padding: 0.6em 1.4em; background: #2a7; color: #fff; border: 0; border-radius: 4px; font-size: 1em; cursor: pointer; }
</style></head>
<body>
<h1>新規案件</h1>
<p><a href="/projects">← 案件一覧へ</a></p>
<form id="form">
  <label>案件名 <input name="name" required></label>
  <label>対象カテゴリ
    <select name="category" required>
      <option value="">選択してください</option>
      <option value="autoclave">オートクレーブ</option>
      <option value="centrifuge">遠心機</option>
      <option value="other">その他</option>
    </select>
  </label>
  <label>PB コンセプト（任意）<textarea name="pb_concept" rows="3"></textarea></label>
  <p><button type="submit">作成</button></p>
</form>
<script>
document.getElementById('form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const body = Object.fromEntries(fd.entries());
  const resp = await fetch('/api/projects', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body),
  });
  if (!resp.ok) { alert('作成失敗'); return; }
  const data = await resp.json();
  location.href = `/projects/${data.id}`;
});
</script>
</body>
</html>
```

- [ ] **Step 5: app.py に HTML ルートを追加**

`pb-planner/app.py` の前タスクで追加した案件管理セクションの末尾に追加：
```python
@app.route('/projects', methods=['GET'])
def page_projects_list():
    return send_from_directory(_TEMPLATES_DIR, 'projects_list.html')


@app.route('/projects/new', methods=['GET'])
def page_project_new():
    return send_from_directory(_TEMPLATES_DIR, 'project_new.html')
```

- [ ] **Step 6: テストが通ることを確認**

Run: `cd pb-planner && pytest tests/test_routes_projects.py -v`
Expected: 全件 PASSED

- [ ] **Step 7: コミット**

```bash
cd pb-planner
git add templates/projects_list.html templates/project_new.html app.py tests/test_routes_projects.py
git commit -m "feat(ui): 案件一覧 + 新規案件作成ページを追加"
```

---

### Task 1.4: 案件詳細ページ（ソース登録 UI）

**Files:**
- Create: `templates/project_detail.html`
- Modify: `app.py`

- [ ] **Step 1: テスト書く**

`tests/test_routes_projects.py` 末尾に追加：
```python
def test_get_project_detail_page(client):
    cr = client.post("/api/projects", json={"name": "x", "category": "autoclave", "pb_concept": ""})
    pid = cr.get_json()["id"]
    resp = client.get(f"/projects/{pid}")
    assert resp.status_code == 200
    assert b"sources" in resp.data.lower() or b"\xe7\xab\xb6\xe5\x90\x88" in resp.data  # "競合"
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `cd pb-planner && pytest tests/test_routes_projects.py::test_get_project_detail_page -v`
Expected: 404 FAIL

- [ ] **Step 3: templates/project_detail.html 作成**

```html
<!DOCTYPE html>
<html lang="ja">
<head><meta charset="utf-8"><title>案件詳細 — PB企画プランナー</title>
<style>
body { font-family: -apple-system, "Segoe UI", sans-serif; max-width: 960px; margin: 2em auto; padding: 0 1em; }
section { border: 1px solid #ddd; padding: 1em; margin: 1em 0; border-radius: 6px; }
h2 { margin-top: 0; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #ddd; padding: 0.5em; }
input { width: 100%; box-sizing: border-box; padding: 0.4em; }
button { padding: 0.5em 1em; background: #2a7; color: #fff; border: 0; border-radius: 4px; cursor: pointer; }
button.secondary { background: #888; }
.row-actions { text-align: center; }
</style></head>
<body>
<h1 id="title">案件詳細</h1>
<p><a href="/projects">← 案件一覧</a></p>

<section>
  <h2>自社（AS ONE / ナビス）</h2>
  <p>AXEL のカテゴリ絞り URL を 1 つ以上：</p>
  <table id="asone_tbl">
    <thead><tr><th>絞り URL</th><th></th></tr></thead>
    <tbody></tbody>
  </table>
  <button onclick="addAsoneRow()">+ URL 追加</button>
</section>

<section>
  <h2>製造パートナー</h2>
  <table id="partner_tbl">
    <thead><tr><th>社名</th><th>公式 URL</th><th>主要型番（カンマ区切り）</th><th></th></tr></thead>
    <tbody></tbody>
  </table>
  <button onclick="addPartnerRow()">+ パートナー追加</button>
</section>

<section>
  <h2>競合</h2>
  <table id="competitor_tbl">
    <thead><tr><th>社名</th><th>公式 URL</th><th>主要型番（カンマ区切り）</th><th></th></tr></thead>
    <tbody></tbody>
  </table>
  <button onclick="addCompetitorRow()">+ 競合追加</button>
</section>

<p><button onclick="saveSources()">ソースを保存</button></p>

<script>
const pid = location.pathname.split('/').pop();

function row(html) { const tr = document.createElement('tr'); tr.innerHTML = html; return tr; }
function addAsoneRow(url='') {
  document.querySelector('#asone_tbl tbody').appendChild(row(
    `<td><input class="asone_url" value="${url}"></td>
     <td class="row-actions"><button class="secondary" onclick="this.closest('tr').remove()">削除</button></td>`
  ));
}
function addPartnerRow(d={maker:'',url:'',models:''}) {
  document.querySelector('#partner_tbl tbody').appendChild(row(
    `<td><input class="p_maker" value="${d.maker}"></td>
     <td><input class="p_url" value="${d.url}"></td>
     <td><input class="p_models" value="${d.models}"></td>
     <td class="row-actions"><button class="secondary" onclick="this.closest('tr').remove()">削除</button></td>`
  ));
}
function addCompetitorRow(d={maker:'',url:'',models:''}) {
  document.querySelector('#competitor_tbl tbody').appendChild(row(
    `<td><input class="c_maker" value="${d.maker}"></td>
     <td><input class="c_url" value="${d.url}"></td>
     <td><input class="c_models" value="${d.models}"></td>
     <td class="row-actions"><button class="secondary" onclick="this.closest('tr').remove()">削除</button></td>`
  ));
}
function readSources() {
  return {
    asone: { filter_urls: Array.from(document.querySelectorAll('.asone_url')).map(i => i.value).filter(Boolean) },
    partner: Array.from(document.querySelectorAll('#partner_tbl tbody tr')).map(tr => ({
      maker: tr.querySelector('.p_maker').value,
      url: tr.querySelector('.p_url').value,
      models: tr.querySelector('.p_models').value.split(',').map(s => s.trim()).filter(Boolean),
    })).filter(x => x.maker || x.url),
    competitor: Array.from(document.querySelectorAll('#competitor_tbl tbody tr')).map(tr => ({
      maker: tr.querySelector('.c_maker').value,
      url: tr.querySelector('.c_url').value,
      models: tr.querySelector('.c_models').value.split(',').map(s => s.trim()).filter(Boolean),
    })).filter(x => x.maker || x.url),
  };
}
async function saveSources() {
  const sources = readSources();
  const r = await fetch(`/api/projects/${pid}/sources`, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(sources),
  });
  alert(r.ok ? '保存しました' : '保存失敗');
}

fetch(`/api/projects/${pid}`).then(r => r.json()).then(proj => {
  document.getElementById('title').textContent = `案件: ${proj.meta.name} (${proj.meta.category})`;
  (proj.sources.asone.filter_urls || []).forEach(u => addAsoneRow(u));
  if ((proj.sources.asone.filter_urls || []).length === 0) addAsoneRow('');
  (proj.sources.partner || []).forEach(p => addPartnerRow({ ...p, models: (p.models || []).join(',') }));
  if ((proj.sources.partner || []).length === 0) addPartnerRow();
  (proj.sources.competitor || []).forEach(c => addCompetitorRow({ ...c, models: (c.models || []).join(',') }));
  if ((proj.sources.competitor || []).length === 0) addCompetitorRow();
});
</script>
</body>
</html>
```

- [ ] **Step 4: app.py に詳細ページルートを追加**

```python
@app.route('/projects/<pid>', methods=['GET'])
def page_project_detail(pid):
    return send_from_directory(_TEMPLATES_DIR, 'project_detail.html')
```

- [ ] **Step 5: テストが通ることを確認**

Run: `cd pb-planner && pytest tests/test_routes_projects.py -v`
Expected: 全件 PASSED

- [ ] **Step 6: コミット**

```bash
cd pb-planner
git add templates/project_detail.html app.py tests/test_routes_projects.py
git commit -m "feat(ui): 案件詳細ページ（ソース登録 UI）を追加"
```

---

## Phase 2: スクレイピングオーケストレータ

### Task 2.1: scraper_orchestrator.py — ディスパッチャと進捗管理

**Files:**
- Create: `scraper_orchestrator.py`
- Create: `tests/test_scraper_orchestrator.py`

- [ ] **Step 1: 失敗するテストを書く**

`tests/test_scraper_orchestrator.py`:
```python
"""scraper_orchestrator のテスト"""
import json
import os
import pytest
from project_manager import create_project, add_or_replace_sources
from scraper_orchestrator import run_scraping, get_progress


def test_run_scraping_creates_progress_file(tmp_projects_dir, monkeypatch):
    # 各スクレイパー関数をモック化
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
    # 各 scraped ファイルが書かれた
    asone_path = os.path.join(tmp_projects_dir, pid, "scraped", "asone", "products.jsonl")
    assert os.path.exists(asone_path)


def test_get_progress_returns_pending_when_never_run(tmp_projects_dir):
    pid = create_project(name="t", category="autoclave", pb_concept="")
    p = get_progress(pid)
    assert p["status"] == "pending"
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `cd pb-planner && pytest tests/test_scraper_orchestrator.py -v`
Expected: ModuleNotFoundError

- [ ] **Step 3: scraper_orchestrator.py 実装**

```python
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
    with open(_progress_path(pid), "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


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


def _scrape_url_generic(url: str, dest_path: str, models: list[str] | None = None) -> int:
    """汎用スクレイパー（既存メーカーは既存スクレイパー、未知メーカーはフォールバック）"""
    # Phase 3 で AXEL 専用、Phase 4 以降で既存スクレイパー統合
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    # 最小実装: URL を 1 ページだけ取得して text を保存（後続タスクで型番抽出に拡張）
    from scripts.scraper_base import fetch
    html = fetch(url)
    if html is None:
        return 0
    with open(dest_path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"maker": "", "model": "", "url": url,
                            "raw_html_len": len(html)}, ensure_ascii=False) + "\n")
    return 1


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

        # AS ONE
        if asone_urls:
            try:
                count = 0
                for u in asone_urls:
                    dest = os.path.join(_scraped_dir(pid, "asone"), "products.jsonl")
                    count += _scrape_axel(u, dest)
                _mark("asone", status="completed", count=count)
            except Exception as e:
                progress["errors"].append({"source": "asone", "error": str(e), "tb": traceback.format_exc()})
                _mark("asone", status="failed", count=0)

        # Partner
        for p in sources.get("partner", []):
            name = f"partner:{p['maker']}"
            try:
                dest = os.path.join(_scraped_dir(pid, "partner"), f"{p['maker']}.jsonl")
                count = _scrape_url_generic(p["url"], dest, models=p.get("models"))
                _mark(name, status="completed", count=count)
            except Exception as e:
                progress["errors"].append({"source": name, "error": str(e)})
                _mark(name, status="failed", count=0)

        # Competitor
        for c in sources.get("competitor", []):
            name = f"competitor:{c['maker']}"
            try:
                dest = os.path.join(_scraped_dir(pid, "competitor"),
                                    c["maker"], "products.jsonl")
                count = _scrape_url_generic(c["url"], dest, models=c.get("models"))
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
```

- [ ] **Step 4: テストが通ることを確認**

Run: `cd pb-planner && pytest tests/test_scraper_orchestrator.py -v`
Expected: 2 件 PASSED

- [ ] **Step 5: コミット**

```bash
cd pb-planner
git add scraper_orchestrator.py tests/test_scraper_orchestrator.py
git commit -m "feat(scraper_orchestrator): 案件単位スクレイピング進捗管理を追加"
```

---

### Task 2.2: スクレイピング起動・進捗ポーリング API

**Files:**
- Modify: `app.py`
- Modify: `tests/test_routes_projects.py`

- [ ] **Step 1: テスト追加**

`tests/test_routes_projects.py` 末尾に追加：
```python
def test_post_scrape_triggers_scraping(client, monkeypatch):
    cr = client.post("/api/projects", json={
        "name": "z", "category": "autoclave", "pb_concept": "",
    })
    pid = cr.get_json()["id"]
    # ソース登録（空）
    client.post(f"/api/projects/{pid}/sources", json={
        "asone": {"filter_urls": []}, "partner": [], "competitor": [],
    })
    # スクレイピングを同期実行に切り替えるためモック
    from scraper_orchestrator import run_scraping
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
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `cd pb-planner && pytest tests/test_routes_projects.py::test_post_scrape_triggers_scraping tests/test_routes_projects.py::test_get_progress -v`
Expected: 404 FAIL

- [ ] **Step 3: app.py に追加**

案件管理ルートセクションの末尾に追加：
```python
from scraper_orchestrator import run_scraping, get_progress  # noqa: E402


@app.route('/api/projects/<pid>/scrape', methods=['POST'])
def api_scrape(pid):
    try:
        _pm.get_project(pid)
    except _pm.ProjectNotFound:
        return jsonify({"error": "not found"}), 404
    run_scraping(pid, async_=True)
    return jsonify({"ok": True, "status": "running"})


@app.route('/api/projects/<pid>/progress', methods=['GET'])
def api_progress(pid):
    try:
        _pm.get_project(pid)
    except _pm.ProjectNotFound:
        return jsonify({"error": "not found"}), 404
    return jsonify(get_progress(pid))
```

- [ ] **Step 4: テスト確認**

Run: `cd pb-planner && pytest tests/test_routes_projects.py -v`
Expected: 全件 PASSED

- [ ] **Step 5: 詳細ページの UI 追加（簡易進捗バー）**

`templates/project_detail.html` の `</body>` 直前に追加：
```html
<section>
  <h2>スクレイピング</h2>
  <p><button onclick="startScraping()">スクレイピング開始</button></p>
  <div id="progress"></div>
</section>
<script>
async function startScraping() {
  const r = await fetch(`/api/projects/${pid}/scrape`, {method: 'POST'});
  if (!r.ok) { alert('起動失敗'); return; }
  pollProgress();
}
async function pollProgress() {
  const r = await fetch(`/api/projects/${pid}/progress`);
  const p = await r.json();
  document.getElementById('progress').innerHTML =
    `<p>状態: ${p.status}</p><ul>` +
    (p.items || []).map(it =>
      `<li>${it.source}: ${it.status} (${it.count || 0} 件)</li>`).join('') +
    `</ul>`;
  if (p.status === 'running') setTimeout(pollProgress, 2000);
}
</script>
```

- [ ] **Step 6: コミット**

```bash
cd pb-planner
git add app.py templates/project_detail.html tests/test_routes_projects.py
git commit -m "feat(app,ui): スクレイピング起動・進捗ポーリング API と UI を追加"
```

---

## Phase 3: AS ONE / ナビス AXEL スクレイパー

### Task 3.1: 固定 HTML フィクスチャ作成

**Files:**
- Create: `tests/fixtures/axel_list_sample.html`
- Create: `tests/fixtures/axel_detail_sample.html`

- [ ] **Step 1: 実物 HTML を取得**

Run:
```bash
curl -L -A 'Mozilla/5.0' \
  'https://axel.as-1.co.jp/c/sterilization' \
  -o pb-planner/tests/fixtures/axel_list_sample.html
```

実行後、ファイルが 50KB 以上あることを確認（小さすぎる場合は別カテゴリ URL で再取得）。

- [ ] **Step 2: 詳細ページサンプルも 1 件取得**

一覧 HTML から商品詳細 URL を 1 つ抜き、curl で取得して `axel_detail_sample.html` に保存。

- [ ] **Step 3: コミット**

```bash
cd pb-planner
git add tests/fixtures/axel_list_sample.html tests/fixtures/axel_detail_sample.html
git commit -m "test: AXEL 一覧・詳細ページの HTML フィクスチャを追加"
```

---

### Task 3.2: scraper_axel.py — AS ONE/ナビス フィルタ抽出

**Files:**
- Create: `scripts/scraper_axel.py`
- Create: `tests/test_scraper_axel.py`

- [ ] **Step 1: テスト書く**

`tests/test_scraper_axel.py`:
```python
"""AXEL スクレイパーのテスト"""
import json
import os
import pytest
from scripts.scraper_axel import (
    parse_product_list,
    parse_product_detail,
    filter_pb_brands,
)


FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _read(name):
    with open(os.path.join(FIXTURE_DIR, name), encoding="utf-8") as f:
        return f.read()


def test_parse_product_list_extracts_items():
    html = _read("axel_list_sample.html")
    items = parse_product_list(html, base_url="https://axel.as-1.co.jp")
    assert len(items) >= 1
    sample = items[0]
    assert "name" in sample
    assert "url" in sample
    assert sample["url"].startswith("https://")


def test_filter_pb_brands_keeps_as_one_and_navis():
    items = [
        {"name": "x", "url": "/x", "maker": "アズワン"},
        {"name": "y", "url": "/y", "maker": "ナビス"},
        {"name": "z", "url": "/z", "maker": "ヤマト科学"},
        {"name": "w", "url": "/w", "maker": ""},
    ]
    out = filter_pb_brands(items)
    makers = {it["maker"] for it in out}
    assert "アズワン" in makers
    assert "ナビス" in makers
    assert "ヤマト科学" not in makers


def test_parse_product_detail_returns_specs():
    html = _read("axel_detail_sample.html")
    detail = parse_product_detail(html)
    assert isinstance(detail.get("specs"), dict)
    # 何らかのキーがあること
    assert len(detail["specs"]) >= 1 or detail.get("name")
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `cd pb-planner && pytest tests/test_scraper_axel.py -v`
Expected: ModuleNotFoundError

- [ ] **Step 3: scripts/scraper_axel.py を実装**

```python
"""AS ONE / ナビス AXEL スクレイパー"""
import json
import os
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup

from scripts.scraper_base import fetch, parse_spec_table


PB_BRAND_KEYWORDS = ("アズワン", "ナビス", "AS ONE", "NAVIS", "AS_ONE")


def parse_product_list(html: str, base_url: str = "https://axel.as-1.co.jp") -> list[dict]:
    """商品一覧 HTML から商品リストを抽出。

    AXEL は商品カード要素を持つ。実装は以下のヒューリスティック:
    - 各商品リンクは商品詳細ページへの a タグ
    - メーカー名は親要素のテキストから抽出
    """
    soup = BeautifulSoup(html, 'html.parser')
    items = []
    # 商品リンクを広く拾う（実 HTML 構造に合わせて要調整）
    for a in soup.select('a[href*="/p/"], a[href*="/asone-product/"]'):
        name = a.get_text(strip=True)
        href = a.get('href', '')
        if not name or not href:
            continue
        url = urljoin(base_url, href)
        # 親要素からメーカー名を推定
        parent = a.find_parent(['li', 'div', 'tr'])
        maker = ""
        if parent:
            text = parent.get_text(' ', strip=True)
            for kw in PB_BRAND_KEYWORDS:
                if kw in text:
                    maker = "アズワン" if kw in ("アズワン", "AS ONE", "AS_ONE") else "ナビス"
                    break
        items.append({"name": name, "url": url, "maker": maker})
    # 重複除去（URL 基準）
    seen = set()
    out = []
    for it in items:
        if it["url"] in seen:
            continue
        seen.add(it["url"])
        out.append(it)
    return out


def filter_pb_brands(items: list[dict]) -> list[dict]:
    """AS ONE / ナビス ブランドのみ残す"""
    out = []
    for it in items:
        m = (it.get("maker") or "").strip()
        if any(kw in m for kw in ("アズワン", "ナビス", "AS ONE", "NAVIS")):
            out.append(it)
    return out


def parse_product_detail(html: str) -> dict:
    """商品詳細ページから名前・型番・価格・スペックを抽出"""
    soup = BeautifulSoup(html, 'html.parser')
    name = ""
    if soup.h1:
        name = soup.h1.get_text(strip=True)
    # 価格: 「¥123,456」パターン
    price = None
    m = re.search(r'¥\s*([\d,]+)', soup.get_text(' '))
    if m:
        try:
            price = int(m.group(1).replace(",", ""))
        except ValueError:
            pass
    specs = parse_spec_table(html)
    return {"name": name, "price": price, "specs": specs}


def scrape_to_jsonl(filter_url: str, dest_path: str, max_items: int = 60) -> int:
    """カテゴリ絞り URL から AS ONE/ナビス 製品を全件取得して JSONL 保存"""
    list_html = fetch(filter_url)
    if list_html is None:
        return 0
    items = filter_pb_brands(parse_product_list(list_html))
    items = items[:max_items]
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    count = 0
    with open(dest_path, "a", encoding="utf-8") as f:
        for it in items:
            detail_html = fetch(it["url"])
            if detail_html is None:
                continue
            detail = parse_product_detail(detail_html)
            row = {**it, **detail, "category": "autoclave"}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count
```

- [ ] **Step 4: テストが通ることを確認**

Run: `cd pb-planner && pytest tests/test_scraper_axel.py -v`

セレクタ調整が必要であれば、fixture HTML を見て `parse_product_list` の CSS セレクタを修正する。

Expected: 3 件 PASSED

- [ ] **Step 5: コミット**

```bash
cd pb-planner
git add scripts/scraper_axel.py tests/test_scraper_axel.py
git commit -m "feat(scraper_axel): AS ONE/ナビス AXEL スクレイパーを追加"
```

---

## Phase 4: 3C レポート生成（Web 検索なしバージョン）

### Task 4.1: web_search.py — スタブ実装

**Files:**
- Create: `web_search.py`
- Create: `tests/test_web_search.py`

- [ ] **Step 1: テスト書く**

`tests/test_web_search.py`:
```python
"""web_search のテスト"""
from web_search import search


def test_search_returns_empty_when_no_api_key(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    results = search("test query", num_results=3)
    assert isinstance(results, list)
    assert results == []  # スタブモードでは空


def test_search_returns_list_of_dicts(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "dummy")
    # 実 API を呼ばないためモック
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
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `cd pb-planner && pytest tests/test_web_search.py -v`
Expected: ModuleNotFoundError

- [ ] **Step 3: web_search.py 実装**

```python
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
```

- [ ] **Step 4: テストが通ることを確認**

Run: `cd pb-planner && pytest tests/test_web_search.py -v`
Expected: 2 件 PASSED

- [ ] **Step 5: コミット**

```bash
cd pb-planner
git add web_search.py tests/test_web_search.py
git commit -m "feat(web_search): Tavily ベースの検索ラッパー（API キー無しは空）"
```

---

### Task 4.2: report_engine_3c.py — プロンプト構築 + Claude ストリーミング

**Files:**
- Create: `report_engine_3c.py`
- Create: `tests/test_report_engine_3c.py`

- [ ] **Step 1: テスト書く**

`tests/test_report_engine_3c.py`:
```python
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
        def text_stream(self):
            for chunk in ["Customer ", "セクション。", "Competitor "]:
                yield chunk

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
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `cd pb-planner && pytest tests/test_report_engine_3c.py -v`
Expected: ModuleNotFoundError

- [ ] **Step 3: report_engine_3c.py 実装**

```python
"""3C レポート生成エンジン"""
import json
import os
from anthropic import Anthropic

import project_manager as _pm
import web_search


MODEL_ID = "claude-opus-4-7"  # 1M context 不要であれば claude-sonnet-4-6 でも可


def load_project_data(pid: str) -> dict:
    """案件の scraped データを集約"""
    pdir = _pm._project_dir(pid)
    out = {"asone": [], "partner": {}, "competitor": {}}

    def _read_jsonl(path):
        items = []
        if not os.path.exists(path):
            return items
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    items.append(json.loads(line))
        return items

    out["asone"] = _read_jsonl(os.path.join(pdir, "scraped", "asone", "products.jsonl"))
    partner_dir = os.path.join(pdir, "scraped", "partner")
    if os.path.exists(partner_dir):
        for fname in os.listdir(partner_dir):
            if fname.endswith(".jsonl"):
                key = fname[:-len(".jsonl")]
                out["partner"][key] = _read_jsonl(os.path.join(partner_dir, fname))
    comp_dir = os.path.join(pdir, "scraped", "competitor")
    if os.path.exists(comp_dir):
        for maker in os.listdir(comp_dir):
            jsonl_path = os.path.join(comp_dir, maker, "products.jsonl")
            if os.path.exists(jsonl_path):
                out["competitor"][maker] = _read_jsonl(jsonl_path)
    return out


def _format_products(items: list[dict]) -> str:
    if not items:
        return "(データなし)"
    lines = []
    for it in items[:40]:  # トークン抑制
        spec_str = ", ".join(f"{k}={v}" for k, v in (it.get("specs") or {}).items()[:8])
        lines.append(f"- {it.get('maker','?')} {it.get('model','?')} {it.get('name','')} "
                     f"価格={it.get('price','?')} | {spec_str}")
    return "\n".join(lines)


def build_prompt(meta: dict, base_model: dict, data: dict, web_results: list[dict]) -> str:
    """3C プロンプトを構築"""
    parts = []
    parts.append(f"""あなたはアズワンの PB企画コンサルタントです。以下の案件について、プロのマーケッター成果物相当の厚みを持つ **3C 分析レポート**を Markdown 形式で生成してください。

# 案件概要
- 案件名: {meta.get('name','')}
- 対象カテゴリ: {meta.get('category','')}
- PB コンセプト: {meta.get('pb_concept','')}
- ベース機種候補: {base_model.get('maker','?')} {base_model.get('model','?')}

# 出力指示
1. **Customer**（最低800字）: 市場規模・成長性、セグメント別プロファイル（大学/製薬/食品/医療/バイオ）、JTBD、ペルソナ別ペイン、VOC 引用、未充足ニーズ
2. **Competitor**（最低1200字）: 競合マッピング図記述、TOP 機種スペック比較表（パイプテーブル）、各社訴求メッセージ、シェア推定、サポート密度、直近 12-24 ヶ月動向
3. **Company（アズワン PB ブランド = AS ONE + ナビス）**（最低600字）: PB ブランドの強み、既存ラインアップとの整合（共食い検証）、販社チャネル適合性、製造パートナー（補足）
4. **最終セクション**: 未充足ニーズ × 自社強みのクロスを軽く（KSF/4P は別レポート扱い）

**ルール**:
- スペック・価格は提供データから引用。データに無い情報は「データに記載なし」と明記。
- VOC・市場動向は Web 検索結果から引用、出典 URL を脚注。
- ハルシネーション厳禁。表は Markdown パイプテーブルで作る。
""")

    parts.append("\n# 提供データ\n")
    parts.append("\n## 自社（AS ONE / ナビス）製品一覧\n")
    parts.append(_format_products(data.get("asone", [])))

    parts.append("\n\n## 製造パートナー製品（ベース機種候補周辺）\n")
    for maker, items in (data.get("partner") or {}).items():
        parts.append(f"\n### {maker}\n")
        parts.append(_format_products(items))

    parts.append("\n\n## 競合製品\n")
    for maker, items in (data.get("competitor") or {}).items():
        parts.append(f"\n### {maker}\n")
        parts.append(_format_products(items))

    if web_results:
        parts.append("\n\n## Web 検索結果（顧客・市場・VOC）\n")
        for r in web_results:
            parts.append(f"- [{r.get('title','')}]({r.get('url','')}): {r.get('content','')[:300]}")
    return "\n".join(parts)


def _collect_web_results(category: str, competitor_makers: list[str]) -> list[dict]:
    """市場・JTBD・VOC・競合評判 を Web 検索で取得（Phase 5 で実 API 統合）"""
    queries = [
        f"{category} 市場規模 日本",
        f"{category} 用途 セグメント 大学 製薬 食品",
        f"{category} 選定基準 ペインポイント",
    ]
    for maker in competitor_makers[:3]:
        queries.append(f"{maker} {category} 評判 レビュー")

    results = []
    for q in queries:
        results.extend(web_search.search(q, num_results=3))
    return results


def generate_3c_stream(pid: str, base_model: dict, save_report: bool = True):
    """3C レポートをストリーミング生成。yield で文字列を返す。
    最初に '[META] <report_id>' を yield、以降は本文 chunk。
    """
    proj = _pm.get_project(pid)
    data = load_project_data(pid)
    web_results = _collect_web_results(
        proj["meta"]["category"],
        [c["maker"] for c in proj["sources"].get("competitor", [])],
    )
    prompt = build_prompt(proj["meta"], base_model, data, web_results)

    client = Anthropic()
    accumulated = []
    with client.messages.stream(
        model=MODEL_ID,
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        from datetime import datetime, timezone, timedelta
        JST = timezone(timedelta(hours=9))
        ts = datetime.now(JST).strftime("%Y%m%d_%H%M%S")
        report_id = f"3c_{ts}"
        yield f"[META] {report_id}\n"
        for text in stream.text_stream:
            accumulated.append(text)
            yield text

    if save_report:
        reports_dir = os.path.join(_pm._project_dir(pid), "reports")
        os.makedirs(reports_dir, exist_ok=True)
        md_text = "".join(accumulated)
        with open(os.path.join(reports_dir, f"{report_id}.md"), "w", encoding="utf-8") as f:
            f.write(md_text)
        meta = {
            "report_id": report_id,
            "base_model": base_model,
            "char_count": len(md_text),
            "web_results_count": len(web_results),
        }
        with open(os.path.join(reports_dir, f"{report_id}.meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
```

- [ ] **Step 4: テストが通ることを確認**

Run: `cd pb-planner && pytest tests/test_report_engine_3c.py -v`
Expected: 3 件 PASSED

- [ ] **Step 5: コミット**

```bash
cd pb-planner
git add report_engine_3c.py tests/test_report_engine_3c.py
git commit -m "feat(report_engine_3c): 3C プロンプト構築と Claude ストリーミング生成を追加"
```

---

### Task 4.3: 3C レポート生成 SSE エンドポイント

**Files:**
- Modify: `app.py`
- Modify: `tests/test_routes_projects.py`

- [ ] **Step 1: テスト追加**

`tests/test_routes_projects.py` 末尾：
```python
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
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `cd pb-planner && pytest tests/test_routes_projects.py::test_post_report_3c_returns_sse -v`
Expected: 404 FAIL

- [ ] **Step 3: app.py に追加**

案件管理セクション末尾：
```python
from report_engine_3c import generate_3c_stream  # noqa: E402


@app.route('/api/projects/<pid>/reports/3c', methods=['POST'])
def api_generate_3c(pid):
    try:
        _pm.get_project(pid)
    except _pm.ProjectNotFound:
        return jsonify({"error": "not found"}), 404
    data = request.get_json(force=True) or {}
    base_model = data.get("base_model") or {}

    def event_stream():
        for chunk in generate_3c_stream(pid, base_model=base_model):
            yield f"data: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n"
        yield "data: {\"done\": true}\n\n"

    return Response(event_stream(), mimetype="text/event-stream")
```

- [ ] **Step 4: テスト確認**

Run: `cd pb-planner && pytest tests/test_routes_projects.py -v`
Expected: 全件 PASSED

- [ ] **Step 5: コミット**

```bash
cd pb-planner
git add app.py tests/test_routes_projects.py
git commit -m "feat(app): 3C レポート生成 SSE エンドポイントを追加"
```

---

### Task 4.4: レポート画面（SSE 受信 + Markdown 表示）

**Files:**
- Create: `templates/report_3c.html`
- Modify: `app.py`
- Modify: `templates/project_detail.html`

- [ ] **Step 1: templates/report_3c.html 作成**

```html
<!DOCTYPE html>
<html lang="ja">
<head><meta charset="utf-8"><title>3C レポート — PB企画プランナー</title>
<style>
body { font-family: -apple-system, "Segoe UI", sans-serif; max-width: 960px; margin: 2em auto; padding: 0 1em; }
#report { background: #fafafa; padding: 1em; border: 1px solid #ddd; border-radius: 6px; white-space: pre-wrap; font-size: 0.95em; }
.status { padding: 0.4em 0.8em; background: #ffd; border-radius: 4px; display: inline-block; }
button { padding: 0.5em 1em; background: #2a7; color: #fff; border: 0; border-radius: 4px; cursor: pointer; }
button:disabled { background: #aaa; cursor: not-allowed; }
</style>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
</head>
<body>
<h1>3C レポート</h1>
<p><span class="status" id="status">準備中</span> &nbsp; <button id="pdf_btn" disabled>PDF エクスポート</button></p>
<div id="report"></div>
<script>
const pid = location.pathname.split('/')[2];
const baseModel = JSON.parse(sessionStorage.getItem('base_model') || '{}');
let reportId = null;
let mdAccum = "";
async function start() {
  document.getElementById('status').textContent = '生成中...';
  const resp = await fetch(`/api/projects/${pid}/reports/3c`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ base_model: baseModel }),
  });
  const reader = resp.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf('\n\n')) >= 0) {
      const line = buf.slice(0, idx).trim();
      buf = buf.slice(idx + 2);
      if (line.startsWith('data:')) {
        try {
          const payload = JSON.parse(line.slice(5).trim());
          if (payload.text) {
            if (payload.text.startsWith('[META]')) {
              reportId = payload.text.replace('[META]', '').trim();
            } else {
              mdAccum += payload.text;
              document.getElementById('report').innerHTML = marked.parse(mdAccum);
            }
          }
          if (payload.done) {
            document.getElementById('status').textContent = '完了';
            const btn = document.getElementById('pdf_btn');
            btn.disabled = false;
            btn.onclick = () => location.href = `/api/projects/${pid}/reports/${reportId}/pdf`;
          }
        } catch (e) { console.warn(e); }
      }
    }
  }
}
start();
</script>
</body>
</html>
```

- [ ] **Step 2: app.py にレポート画面ルートを追加**

```python
@app.route('/projects/<pid>/report', methods=['GET'])
def page_report(pid):
    return send_from_directory(_TEMPLATES_DIR, 'report_3c.html')
```

- [ ] **Step 3: project_detail.html に「機種選択 → 3C 生成」UI を追加**

`</body>` 直前に追加：
```html
<section>
  <h2>3C 一発レポート</h2>
  <label>ベース機種: <input id="base_model_input" placeholder="例: tomys/FLS-1000 (maker/model)"></label>
  <p><button onclick="startReport()">3C 生成画面へ</button></p>
</section>
<script>
function startReport() {
  const v = document.getElementById('base_model_input').value.trim();
  if (!v.includes('/')) { alert('maker/model 形式で入力してください'); return; }
  const [maker, model] = v.split('/');
  sessionStorage.setItem('base_model', JSON.stringify({ maker, model }));
  location.href = `/projects/${pid}/report`;
}
</script>
```

- [ ] **Step 4: 確認**

Run: `cd pb-planner && pytest tests/test_routes_projects.py -v`
Expected: 既存テスト全件 PASSED

- [ ] **Step 5: コミット**

```bash
cd pb-planner
git add templates/report_3c.html app.py templates/project_detail.html
git commit -m "feat(ui): 3C レポート画面（SSE 受信 + Markdown 表示）を追加"
```

---

## Phase 5: PDF エクスポート

### Task 5.1: pdf_exporter.py

**Files:**
- Create: `pdf_exporter.py`
- Create: `tests/test_pdf_exporter.py`

- [ ] **Step 1: テスト書く**

`tests/test_pdf_exporter.py`:
```python
"""pdf_exporter のテスト"""
import os
from pdf_exporter import md_to_pdf


def test_md_to_pdf_creates_pdf_file(tmp_path):
    md = "# Title\n\nHello **world**.\n\n| A | B |\n|---|---|\n| 1 | 2 |\n"
    out = tmp_path / "out.pdf"
    md_to_pdf(md, str(out))
    assert out.exists()
    assert out.stat().st_size > 100  # 何らかのバイト数
    # PDF マジックヘッダ
    with open(out, "rb") as f:
        assert f.read(4) == b"%PDF"
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `cd pb-planner && pytest tests/test_pdf_exporter.py -v`
Expected: ModuleNotFoundError

- [ ] **Step 3: pdf_exporter.py 実装**

```python
"""Markdown → PDF（WeasyPrint 経由）"""
import markdown
from weasyprint import HTML


_CSS = """
@page { size: A4; margin: 18mm; }
body { font-family: 'Hiragino Sans', 'Yu Gothic', sans-serif; font-size: 10.5pt; line-height: 1.7; }
h1 { font-size: 18pt; border-bottom: 2px solid #333; padding-bottom: 0.3em; }
h2 { font-size: 14pt; border-bottom: 1px solid #888; padding-bottom: 0.2em; margin-top: 1.5em; }
h3 { font-size: 12pt; margin-top: 1.2em; }
table { border-collapse: collapse; width: 100%; margin: 0.8em 0; }
th, td { border: 1px solid #666; padding: 0.3em 0.5em; }
th { background: #eee; }
code { background: #f4f4f4; padding: 0.1em 0.3em; border-radius: 3px; font-family: monospace; }
blockquote { border-left: 4px solid #ccc; margin-left: 0; padding-left: 1em; color: #555; }
"""


def md_to_pdf(md_text: str, output_path: str) -> None:
    html_body = markdown.markdown(md_text, extensions=["tables", "fenced_code"])
    full_html = f"""<!DOCTYPE html><html lang='ja'><head><meta charset='utf-8'>
<style>{_CSS}</style></head><body>{html_body}</body></html>"""
    HTML(string=full_html).write_pdf(output_path)
```

- [ ] **Step 4: テストが通ることを確認**

Run: `cd pb-planner && pytest tests/test_pdf_exporter.py -v`
Expected: PASSED

> Windows で WeasyPrint がフォント解決に失敗する場合、GTK ランタイムインストールが必要。Railway 本番では Linux なので問題なし。ローカルで失敗する場合は xfail マークで保留可。

- [ ] **Step 5: コミット**

```bash
cd pb-planner
git add pdf_exporter.py tests/test_pdf_exporter.py
git commit -m "feat(pdf_exporter): Markdown→PDF 変換 (WeasyPrint) を追加"
```

---

### Task 5.2: PDF ダウンロード API

**Files:**
- Modify: `app.py`
- Modify: `tests/test_routes_projects.py`

- [ ] **Step 1: テスト追加**

`tests/test_routes_projects.py` 末尾：
```python
def test_get_report_pdf(client, tmp_projects_dir, monkeypatch):
    cr = client.post("/api/projects", json={"name": "x", "category": "autoclave", "pb_concept": ""})
    pid = cr.get_json()["id"]
    # 手動で reports/ に Markdown を置く
    import os
    rdir = os.path.join(tmp_projects_dir, pid, "reports")
    os.makedirs(rdir, exist_ok=True)
    with open(os.path.join(rdir, "3c_test.md"), "w", encoding="utf-8") as f:
        f.write("# Test\n\nHello.\n")
    resp = client.get(f"/api/projects/{pid}/reports/3c_test/pdf")
    assert resp.status_code == 200
    assert resp.data[:4] == b"%PDF"
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `cd pb-planner && pytest tests/test_routes_projects.py::test_get_report_pdf -v`
Expected: 404 FAIL

- [ ] **Step 3: app.py に追加**

案件管理セクション末尾：
```python
from pdf_exporter import md_to_pdf  # noqa: E402


@app.route('/api/projects/<pid>/reports/<rid>/pdf', methods=['GET'])
def api_report_pdf(pid, rid):
    try:
        _pm.get_project(pid)
    except _pm.ProjectNotFound:
        return jsonify({"error": "not found"}), 404
    pdir = _pm._project_dir(pid)
    md_path = os.path.join(pdir, "reports", f"{rid}.md")
    pdf_path = os.path.join(pdir, "reports", f"{rid}.pdf")
    if not os.path.exists(md_path):
        return jsonify({"error": "report not found"}), 404
    if not os.path.exists(pdf_path):
        with open(md_path, encoding="utf-8") as f:
            md_text = f.read()
        md_to_pdf(md_text, pdf_path)
    return send_file(pdf_path, mimetype="application/pdf",
                     as_attachment=True, download_name=f"{rid}.pdf")
```

- [ ] **Step 4: テスト確認**

Run: `cd pb-planner && pytest tests/test_routes_projects.py -v`
Expected: 全件 PASSED

- [ ] **Step 5: コミット**

```bash
cd pb-planner
git add app.py tests/test_routes_projects.py
git commit -m "feat(app): 3C レポート PDF エクスポート API を追加"
```

---

## Phase 6: 既存スクレイパー統合と汎用フォールバック調整

### Task 6.1: 既存 yamato/hirayama/alp スクレイパーをオーケストレータから呼べるよう統合

**Files:**
- Modify: `scraper_orchestrator.py`
- Modify: `tests/test_scraper_orchestrator.py`

- [ ] **Step 1: テスト追加**

`tests/test_scraper_orchestrator.py` 末尾：
```python
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
```

- [ ] **Step 2: テストが失敗することを確認**

Run: `cd pb-planner && pytest tests/test_scraper_orchestrator.py::test_competitor_yamato_dispatches_existing_scraper -v`
Expected: AttributeError 等 FAIL

- [ ] **Step 3: scraper_orchestrator.py を更新**

`_scrape_url_generic` を以下に置き換え、`_SCRAPER_REGISTRY` を追加：

```python
def _yamato_adapter(url, dest_path, models=None):
    from scripts import scraper_yamato
    # 既存スクレイパーは workspace/data/ に書く構造 → 案件 dest_path にコピー
    # 既存実装をそのまま呼ぶラッパー（実装は読みながら調整）
    return _generic_via_base(url, dest_path, models)


def _hirayama_adapter(url, dest_path, models=None):
    from scripts import scraper_hirayama
    return _generic_via_base(url, dest_path, models)


def _alp_adapter(url, dest_path, models=None):
    from scripts import scraper_alp
    return _generic_via_base(url, dest_path, models)


def _generic_via_base(url, dest_path, models=None):
    """フォールバック: URL を取得して 1 行 JSON で保存"""
    from scripts.scraper_base import fetch
    html = fetch(url)
    if html is None:
        return 0
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with open(dest_path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"maker": "", "model": "", "url": url,
                            "raw_html_len": len(html),
                            "models_requested": models or []},
                           ensure_ascii=False) + "\n")
    return 1


_SCRAPER_REGISTRY = {
    "yamato": _yamato_adapter,
    "hirayama": _hirayama_adapter,
    "alp": _alp_adapter,
}


def _scrape_url_generic(url: str, dest_path: str, models=None, maker: str = "") -> int:
    fn = _SCRAPER_REGISTRY.get(maker.lower())
    if fn:
        return fn(url, dest_path, models=models)
    return _generic_via_base(url, dest_path, models=models)
```

`run_scraping` 内の partner/competitor ループで `_scrape_url_generic` 呼び出しに `maker=p['maker']` / `maker=c['maker']` を渡すよう変更：

```python
            count = _scrape_url_generic(p["url"], dest, models=p.get("models"), maker=p["maker"])
            ...
            count = _scrape_url_generic(c["url"], dest, models=c.get("models"), maker=c["maker"])
```

- [ ] **Step 4: テスト確認**

Run: `cd pb-planner && pytest tests/test_scraper_orchestrator.py -v`
Expected: 全件 PASSED

- [ ] **Step 5: コミット**

```bash
cd pb-planner
git add scraper_orchestrator.py tests/test_scraper_orchestrator.py
git commit -m "feat(scraper_orchestrator): yamato/hirayama/alp の既存スクレイパー統合 + フォールバック"
```

> 既存スクレイパー（`scripts/scraper_yamato.py` 等）は `workspace/data/<maker>_<cat>/products.jsonl` に書く設計。本タスクではアダプタを「フォールバック呼び出し」として最低限実装した。実運用ベースで Phase 7 の E2E 検証時に必要であれば、既存スクレイパーから JSONL を取り出すコピーロジックを追加実装する。

---

## Phase 7: E2E 検証とデプロイ

### Task 7.1: E2E スモークテスト

**Files:**
- Create: `tests/test_e2e_smoke.py`

- [ ] **Step 1: E2E テストを書く**

```python
"""E2E スモーク: 案件作成 → ソース登録 → スクレイピング → レポート生成"""
import json
import os
import pytest


@pytest.fixture
def client(tmp_projects_dir):
    from app import app
    app.config['TESTING'] = True
    return app.test_client()


def test_full_flow_with_mocked_external_calls(client, tmp_projects_dir, monkeypatch):
    # 全外部呼び出しをモック
    def fake_axel(url, dest):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8") as f:
            f.write(json.dumps({"maker": "アズワン", "model": "PB-1",
                                "specs": {"容量": "50L"}, "price": 500000},
                               ensure_ascii=False) + "\n")
        return 1
    import scraper_orchestrator as so
    monkeypatch.setattr(so, "_scrape_axel", fake_axel)
    monkeypatch.setattr(so, "_SCRAPER_REGISTRY", {})  # フォールバック経由
    def fake_fetch(url, **kw):
        return "<html><body><h1>Dummy</h1></body></html>"
    monkeypatch.setattr("scripts.scraper_base.fetch", fake_fetch)

    # 1. 案件作成
    cr = client.post("/api/projects", json={
        "name": "E2E案件", "category": "autoclave", "pb_concept": "テスト",
    })
    pid = cr.get_json()["id"]

    # 2. ソース登録
    client.post(f"/api/projects/{pid}/sources", json={
        "asone": {"filter_urls": ["https://axel.as-1.co.jp/sample"]},
        "partner": [{"maker": "tomys", "url": "https://t.co/", "models": ["FLS-1000"]}],
        "competitor": [{"maker": "yamato", "url": "https://y.co/", "models": ["SX-700"]}],
    })

    # 3. スクレイピング（同期）
    so.run_scraping(pid, async_=False)
    p = client.get(f"/api/projects/{pid}/progress").get_json()
    assert p["status"] == "completed"

    # 4. 3C レポート生成（Anthropic SDK モック）
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

    # 5. PDF エクスポート
    pdf_resp = client.get(f"/api/projects/{pid}/reports/{rid}/pdf")
    assert pdf_resp.status_code == 200
    assert pdf_resp.data[:4] == b"%PDF"
```

- [ ] **Step 2: 実行**

Run: `cd pb-planner && pytest tests/test_e2e_smoke.py -v`
Expected: PASSED

> WeasyPrint がローカル Windows で動かない場合、この E2E テストの PDF 部分のみ skip マークを付ける（Railway Linux で再実行可能とする）。

- [ ] **Step 3: 全テスト実行**

Run: `cd pb-planner && pytest -v`
Expected: 全件 PASSED

- [ ] **Step 4: コミット**

```bash
cd pb-planner
git add tests/test_e2e_smoke.py
git commit -m "test(e2e): 案件作成→スクレイピング→3C 生成→PDF までのスモーク"
```

---

### Task 7.2: デプロイ（Railway）

**Files:**
- Modify: `render.yaml` or `railway.json`（環境変数 `TAVILY_API_KEY` 等が必要なら）

- [ ] **Step 1: Railway 環境変数の確認**

Railway ダッシュボードで以下を設定（または `.env.example` で文書化）：
- `ANTHROPIC_API_KEY` （既存）
- `TAVILY_API_KEY`（無くても動くが Web 検索結果が空になる）

- [ ] **Step 2: WeasyPrint の Linux 依存パッケージ**

Railway は Nixpacks を使う。`nixpacks.toml` がある場合は確認。WeasyPrint は Linux ではビルド済みで動くため通常追加設定不要。万一エラー出る場合は `aptPkgs = ["libpango-1.0-0", "libpangoft2-1.0-0"]` を追加。

- [ ] **Step 3: ヘルスチェック更新（任意）**

`/api/health` で `projects/` ディレクトリの書き込み可否も簡易チェック。既存 `/api/health` をそのまま維持で OK。

- [ ] **Step 4: push してデプロイ**

```bash
cd pb-planner
git push origin main
```

Railway が自動デプロイ。完了後 `https://web-production-1c92b.up.railway.app/projects` を確認。

- [ ] **Step 5: 本番スモーク**

ブラウザで以下を確認：
1. `/projects` に空一覧が表示される
2. 「+ 新規案件」から案件作成
3. 案件詳細でソース 1 件登録 → 保存
4. スクレイピング起動 → 進捗表示
5. 機種選択 → 3C 生成画面で生成成功
6. PDF ダウンロード可

- [ ] **Step 6: 本番動作ログを記録**

`pb-planner/docs/logs/2026-05-13.md` を作成し、本番確認結果を追記：

```markdown
# 2026-05-13 作業ログ

### [HH:MM] 3C 一発レポート機能 本番リリース
- やったこと: P1-P7 実装、Railway デプロイ
- 使ったファイル: project_manager.py, scraper_orchestrator.py, scripts/scraper_axel.py, web_search.py, report_engine_3c.py, pdf_exporter.py, templates/*, app.py 拡張
- 結果: 本番 /projects アクセス可、E2E スモーク全項目 OK
- コミット: <最終コミットハッシュ>
- 次やること: 実案件（FLS-1000 オートクレーブ）で本番品質を実評価
```

- [ ] **Step 7: コミット**

```bash
cd pb-planner
git add docs/logs/2026-05-13.md
git commit -m "docs(logs): 3C 一発レポート機能 本番リリース記録"
git push
```

---

## オープン論点（実装中に判断する事項）

1. **Web 検索ツールの最終決定**: Tavily 無料枠で十分か、Brave Search MCP 経由が良いか。Phase 4 で Tavily を採用、Phase 7 までに評価。
2. **AXEL スクレイパーの CSS セレクタ精度**: Task 3.2 のフィクスチャ実物確認時に微調整必要。
3. **既存スクレイパー（yamato/hirayama/alp）の出力統合**: Task 6.1 はフォールバック実装。実 PB企画で精度不足ならアダプタ拡充。
4. **WeasyPrint の日本語フォント**: Linux 側で `noto-sans-cjk` 等が入っていなければ Railway 設定追加。
5. **コスト見積もり**: Opus 4.7 1 回 ≒ 8000 tokens × ($15 in + $75 out / 1M) ≒ 数十円〜数百円/レポート。月次 100 レポートでも数千円〜1 万円程度の想定。

---

## 完了基準

- [ ] Phase 0〜7 すべての Task のチェックが付いている
- [ ] `cd pb-planner && pytest -v` で全件 PASS
- [ ] Railway 本番で /projects から E2E スモーク（案件作成 → ソース登録 → スクレイピング → 3C 生成 → PDF）が成功
- [ ] 既存チャット機能（/api/chat）に回帰がないこと確認
- [ ] `docs/logs/2026-05-13.md` に本番リリース記録
