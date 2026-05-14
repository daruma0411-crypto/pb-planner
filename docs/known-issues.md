# PB企画プランナー 既知の不具合・運用課題

## 2026-05-14 時点（3C 一発レポート機能 本番リリース後）

### A. WeasyPrint PDF 変換が Railway 上で 500（優先度: 中）

**症状**: `/api/projects/<pid>/reports/<rid>/pdf` が 500 を返す
**詳細エラー**: `cannot load library 'libgobject-2.0-0': ... No such file or directory`
**試行履歴**:
1. `requirements.txt` に `weasyprint>=62.0` 追加 → Python パッケージは入るが native libs 不足
2. `nixpacks.toml` に `aptPkgs = ["libpango-1.0-0", "libpangoft2-1.0-0", "libcairo2", "shared-mime-info", "fonts-noto-cjk", ...]` → 効かず
3. `nixpacks.toml` に `nixPkgs = ["pango", "cairo", "gdk-pixbuf", "glib", "harfbuzz", "fontconfig", "noto-fonts-cjk-sans"]` 併用 → 効かず

**回避策**:
- レポート画面の **「ブラウザで印刷」ボタン**で `window.print()` → 「PDF として保存」を推奨
- API レベルでは `/api/projects/<pid>/reports/<rid>/md` から Markdown 直接ダウンロード可能（13 KB クラスの完全レポート）

**根本対応の候補**:
- Docker 化（Dockerfile で `apt-get install libpango1.0-dev libcairo2-dev ...`）
- WeasyPrint をやめて `pdfkit + wkhtmltopdf` or `playwright` に切り替え
- Railway support に nixpacks のネイティブ lib リンク問題を相談

### B. AXEL / トミー精工 / アルプ のスクレイパー 0 件（優先度: 高）

**症状**: 案件のスクレイピング実行時、以下が 0 件:
- `asone` (AXEL): URL `https://axel.as-1.co.jp/asone/s/G0000000/` を渡してもファイルが空
- `partner:tomys`: `https://www.tomys.co.jp/` を渡しても 0 件
- `competitor:alp`: `https://www.alpscience.co.jp/` を渡しても 0 件

**動作している**:
- `competitor:yamato` (https://www.yamato-net.co.jp/) → 1 件（フォールバック）
- `competitor:hirayama` (https://www.hirayama-hmc.co.jp/) → 1 件（フォールバック）

**推定原因**:
- AXEL: 一覧 HTML の構造が JavaScript ベースで `requests.get` では取れない可能性 → Playwright 化が必要
- tomys/alp: 既存スクレイパー（`scripts/scraper_tomys.py` 等が存在しない、フォールバックも該当 URL で意図しないレスポンス）

**根本対応の候補**:
- AXEL は SSR 部分があるか確認、または Playwright 経由
- tomys/alp の公式サイト構造を実調査して個別 scraper を追加実装
- ユーザーがソース登録時に「絞り込み済 URL」を渡せる構造になっている設計を踏まえ、AXEL は手動で AS ONE/ナビス絞り込み済 URL を入れてもらう

### C. Railway は ephemeral filesystem（優先度: 中）

**症状**: 再デプロイのたびに `projects/<id>/` が全消去される
**回避策**:
- Railway Volume を追加して `projects/` をマウント
- もしくは PostgreSQL に案件メタを移行（既存 `redis` 接続ロジックを参考）

**緊急性**: 現状は本番運用 1 ユーザー想定なので即時の問題ではないが、本格運用前に対応必須

### D. SSE クライアント切断時にレポート保存されない問題 → 解決済 (`84f5b3b`)

**修正**: `report_engine_3c.py` の generator を `try/finally` で囲み、`GeneratorExit` でも `_save()` を呼ぶよう変更。本番で `/md` ダウンロード 200 OK 確認済 (13921 bytes)。

### E. Tavily API 未設定 → Web 検索結果は空（優先度: 低）

**症状**: `web_search.search()` が `TAVILY_API_KEY` 環境変数なしのため常に空配列を返す
**影響**: 3C レポートの Customer セクション内「市場規模・VOC・JTBD」が実データに基づかず一般論で記述される。それでも Claude が「データに記載なし」と明記してハルシネーション防止が機能している
**対応**:
- Tavily (https://tavily.com) で無料サインアップして API キー取得
- Railway 環境変数に `TAVILY_API_KEY=tvly-...` 設定
- 既存コードがそのまま検索結果を活用する

### F. gunicorn timeout を 600 秒に変更済（情報のみ）

**変更**: `Procfile` / `railway.json` の `--timeout 120` → `--timeout 600`
**理由**: Claude Opus 4.7 ストリーミングが 120 秒で切られていたため
**コミット**: `f7e757c`
