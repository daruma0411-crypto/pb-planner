---
date: 2026-05-13
project: pb-planner
title: 機種選択 → 3C 一発レポート機能 設計書
status: draft
risk: 🟠 強化（影響分析+テスト強化、Worktree までは不要）
---

# 機種選択 → 3C 一発レポート機能 設計書

## 1. 背景と目的

### 現状の問題
現在の PB企画プランナー（`app.py`）では、Function Calling ツール `analyze_framework("3c")` をチャット内で呼び出すと 3C 分析カードが表示される。しかし出力は商品 DB 内の情報のみで構成され、プロのマーケッターが作る成果物としては極めて薄い。

スクショ実例（オートクレーブ FLS-1000 のケース）:
- Customer: 「ラボ用途」「女性ユーザーに着目」程度
- Competitor: 3 社・価格帯・平均価格のみ
- Company: ベース機種名と価格のみ（しかも「自社 = ベース機種メーカー」の誤定義）

### 目的
「機種を選んで一発でプロのコンサル成果物相当の 3C レポートを生成する」専用画面を追加する。データ層・フレームワーク定義・出力 UX を刷新し、コンサル提案書の上半分として使える厚みに引き上げる。

---

## 2. スコープ

### In Scope
- 案件管理レイヤー（案件 CRUD、自社/パートナー/競合の登録）
- 案件単位のスクレイピング（AS ONE/ナビス + 製造パートナー + 競合社）
- 実行時 Web 検索（顧客情報・市場・JTBD・VOC）
- 3C 一発レポート生成（Claude Opus 4.7、ストリーミング、Markdown 出力）
- レポート画面（Markdown レンダリング、PDF エクスポート）
- 既存チャット UI と並行運用

### Out of Scope（次フェーズ以降）
- KSF / STP / 4P / SWOT などの他フレームワークの一発レポート（同パイプラインで順次追加）
- PEST / 5Forces のマクロ環境分析
- 自社共通 DB の事前構築（案件単位スクレイピングで運用、必要になれば追加）
- アズワン社内 PIM からの CSV インポート
- 案件管理の権限制御・複数ユーザー機能

---

## 3. 合意済み設計事項一覧

| 項目 | 決定 |
|---|---|
| 起点 UX | 機種選択 → 「3C 一発生成」ボタン |
| データ層 | ハイブリッド（事前 DB + 実行時 Web 検索） |
| フロー | 事前ヒアリング → 案件作成 → スクレイピング → レポート生成 |
| DB 単位 | 案件単位（自社・パートナー・競合すべて） |
| 入力 UI | 構造化フォーム（社名 + URL + 機種型番） |
| 「自社」定義 | アズワン PB ブランド = **AS ONE + ナビス（NAVIS）** |
| 自社データ取得 | 案件カテゴリ × メーカー=AS ONE/ナビス フィルタ |
| FW 構成 | 3C 単独レポートで完結（他は将来別レポート） |
| 出力 | Markdown ストリーミング表示 + PDF エクスポート |
| 既存 UI | 並行運用（チャット維持、新画面を別ルートで追加） |

---

## 4. ユーザー体験フロー

### 4.1 事前ヒアリング（ツール外）
顧客（アズワン PB企画担当者）と打ち合わせし、以下を確定。
- 対象カテゴリ（例: オートクレーブ）
- PB 化のベース機種候補（例: トミー精工 FLS-1000）
- 想定する競合社・主要機種（例: ヤマト科学 SX-700、ヒラヤマ HV-50、アルプ TR-XX）

### 4.2 案件作成（ツール内）
1. 「新規案件」ボタン → 案件作成画面へ
2. 入力項目:
   - 案件名（自由入力）
   - 対象カテゴリ（オートクレーブ / 遠心機 / …）
   - PB コンセプト（自由テキスト）
   - **自社（アズワン PB）**: AXEL カテゴリ URL を 1 つ（例: `axel.as-1.co.jp/category/.../メーカー=AS_ONE,NAVIS`）
   - **製造パートナー**: 社名 + 公式 URL + 主要機種型番（既存 `tomys_*` データは流用可能）
   - **競合**: 社単位で「社名 + 公式 URL + 主要機種型番（複数）」をテーブル形式で複数行登録
3. 「保存」→ DB に案件レコード作成

### 4.3 スクレイピング起動
1. 案件詳細画面に「スクレイピング開始」ボタン
2. バックグラウンドジョブで各ソースをスクレイピング
3. 進捗バー表示（自社 X/Y 件取得、競合 A 社 完了、B 社 進行中…）
4. 完了通知 → レポート生成可能状態に遷移

### 4.4 3C 一発レポート生成
1. 案件詳細画面で「ベース機種を選択」→ プルダウンで選択
2. 「3C 一発生成」ボタン
3. レポート画面に遷移、即座に「生成中…」表示
4. SSE で Customer → Competitor → Company → 統合インサイト の順にストリーミング表示
5. 完了後「PDF エクスポート」ボタンが活性化

---

## 5. アーキテクチャ

### 5.1 全体図

```
┌─────────────────────────────────────────────────────────────┐
│ Frontend (新規画面 + 既存チャット並行)                       │
│  - /projects             案件一覧                            │
│  - /projects/new         案件作成フォーム                    │
│  - /projects/<id>        案件詳細・ソース登録・スクレイプ起動 │
│  - /projects/<id>/report 3C レポート画面（SSE 受信）          │
│  - /                     既存チャット UI（変更なし）          │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│ Flask app.py (拡張)                                          │
│  - 既存ルート（/api/chat 等）はそのまま                       │
│  - 新規ルート群（後述）を追加                                 │
└────────────────────────┬────────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┬─────────────────┐
        ▼                ▼                ▼                 ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ project_     │ │ scraper_     │ │ report_engine│ │ web_search.py│
│ manager.py   │ │ orchestrator │ │ _3c.py       │ │ (Brave/Tavily│
│ (案件 CRUD)   │ │ .py          │ │ (LLM 生成)    │ │  ラッパー)    │
└──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └──────┬───────┘
       │                │                │                 │
       ▼                ▼                ▼                 ▼
┌──────────────────────────────────────────────────────────────┐
│ projects/<id>/ ファイルシステム（後述データモデル）            │
└──────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
                       ┌──────────────────┐
                       │ pdf_exporter.py  │
                       │ (Markdown → PDF) │
                       └──────────────────┘
```

### 5.2 新規モジュール

| モジュール | 責務 | 主要関数 |
|---|---|---|
| `project_manager.py` | 案件 CRUD、ソース登録、メタ情報管理 | `create_project()`, `add_source()`, `get_project()`, `list_projects()` |
| `scraper_orchestrator.py` | 案件単位のスクレイピング実行、進捗管理、既存スクレイパーのディスパッチ | `run_scraping(project_id)`, `get_progress(project_id)` |
| `report_engine_3c.py` | 3C レポート生成。プロンプト構築、Web 検索結果統合、Claude ストリーミング呼び出し | `generate_3c_stream(project_id, base_model)` |
| `web_search.py` | Brave Search MCP / Tavily / Claude WebSearch のラッパー（フォールバック付き） | `search(query, num_results)` |
| `pdf_exporter.py` | Markdown を PDF に変換（既存 python-docx と同列の出力モジュール） | `md_to_pdf(md_text, output_path)` |

### 5.3 既存資産との関係

| 既存資産 | 関係 |
|---|---|
| `app.py` の Flask ルート | 既存はすべて維持。新規ルートを追記。 |
| `app.py` の Function Calling（特に `analyze_framework`） | 維持。将来「チャット内から一発レポートを呼ぶ」連携の余地あり。 |
| `scripts/scraper_{yamato,hirayama,alp}.py` | `scraper_orchestrator.py` から呼び出して流用。ヤマト/ヒラヤマ/アルプは既存実装をそのまま利用。 |
| `scripts/scraper_base.py` | 新規スクレイパー（AS ONE/ナビス AXEL 用、未登録メーカー用）の基底として活用。 |
| `scripts/update_yamato_alp_db.py` | 全社共通 DB を更新する目的のスクリプト。今回の案件単位パターンでは直接使わないが、参考実装として残す。 |
| `workspace/data/{maker}_{category}/products.jsonl` | 既存の製品データ。案件作成時に「製造パートナー」候補として流用可能（特に `tomys_*`）。 |
| セッション管理（Redis / file / memory） | 案件管理にも同じ層を使う。`projects/` はファイル永続化のみで開始、必要なら後で Redis 移行。 |

---

## 6. データモデル

### 6.1 ディレクトリ構造

```
pb-planner/
  projects/
    <project_id>/                   # 案件 ID は UUID or タイムスタンプ
      meta.json                     # 案件メタ情報
      sources.json                  # 登録された自社/パートナー/競合の URL・型番
      scraping_progress.json        # スクレイピング進捗・エラー
      scraped/
        asone/products.jsonl        # AS ONE/ナビス スクレイピング結果
        partner/products.jsonl      # 製造パートナー
        competitor/<maker>/products.jsonl  # 競合各社
      web_search_cache/
        <query_hash>.json           # Web 検索結果キャッシュ（24h TTL）
      reports/
        <timestamp>_3c.md           # 生成された 3C レポート Markdown
        <timestamp>_3c.pdf          # PDF エクスポート
        <timestamp>_3c.meta.json    # レポート生成時のパラメータ・所要時間等
```

### 6.2 主要 JSON スキーマ

**meta.json**
```json
{
  "id": "prj_20260513_142300",
  "name": "アズワン PB オートクレーブ第3弾",
  "category": "autoclave",
  "pb_concept": "女性研究員向け人間工学設計の100L大容量機",
  "base_model_candidates": [
    {"maker": "tomys", "model": "FLS-1000", "price": 1080000}
  ],
  "created_at": "2026-05-13T14:23:00+09:00",
  "updated_at": "2026-05-13T14:23:00+09:00"
}
```

**sources.json**
```json
{
  "asone": {
    "filter_urls": ["https://axel.as-1.co.jp/category/.../?maker=AS_ONE,NAVIS"]
  },
  "partner": [
    {"maker": "tomys", "url": "https://www.tomys.co.jp/products/autoclave/", "models": ["FLS-1000", "LPS-700"]}
  ],
  "competitor": [
    {"maker": "yamato", "url": "https://www.yamato-net.co.jp/...", "models": ["SX-700", "SX-300"]},
    {"maker": "hirayama", "url": "...", "models": ["HV-50", "HV-110"]},
    {"maker": "alp", "url": "...", "models": ["TR-XX"]}
  ]
}
```

**scraping_progress.json**
```json
{
  "status": "running",
  "started_at": "2026-05-13T14:30:00+09:00",
  "items": [
    {"source": "asone", "status": "completed", "count": 38},
    {"source": "partner:tomys", "status": "completed", "count": 12},
    {"source": "competitor:yamato", "status": "running", "count": 5},
    {"source": "competitor:hirayama", "status": "pending"},
    {"source": "competitor:alp", "status": "pending"}
  ],
  "errors": []
}
```

---

## 7. 主要 API エンドポイント

| メソッド | パス | 機能 |
|---|---|---|
| GET | `/projects` | 案件一覧（JSON） |
| POST | `/projects` | 案件新規作成（meta.json 生成） |
| GET | `/projects/<id>` | 案件詳細（meta + sources + progress） |
| POST | `/projects/<id>/sources` | sources.json の登録・更新 |
| POST | `/projects/<id>/scrape` | スクレイピング起動（バックグラウンドジョブ） |
| GET | `/projects/<id>/progress` | 進捗ポーリング用 |
| POST | `/projects/<id>/reports/3c` | 3C レポート生成（SSE ストリーミング） |
| GET | `/projects/<id>/reports/<rid>` | 生成済みレポート取得（Markdown） |
| GET | `/projects/<id>/reports/<rid>/pdf` | PDF ダウンロード |
| GET | `/projects-ui`, `/projects-ui/<id>` 等 | フロント HTML |

既存 `/api/chat` `/api/health` `/api/download/<filename>` 等はそのまま維持。

---

## 8. データフロー（3C 生成パイプライン）

```
[ユーザー: 機種選択 + 「3C 一発生成」クリック]
        │
        ▼
POST /projects/<id>/reports/3c  (body: {base_model: "FLS-1000"})
        │
        ▼
report_engine_3c.generate_3c_stream(project_id, base_model)
  │
  ├─ 1. 案件データ読み込み
  │     - meta.json, sources.json
  │     - scraped/asone/, scraped/partner/, scraped/competitor/<maker>/
  │
  ├─ 2. 実行時 Web 検索（並列）
  │     web_search.py で以下を並列実行:
  │     - 「<カテゴリ> 市場規模 日本」
  │     - 「<カテゴリ> 用途 セグメント 大学 製薬 食品」
  │     - 「<カテゴリ> 選定基準 ペインポイント」
  │     - 「<競合各社名> 評判 レビュー」
  │     - 「<カテゴリ> JTBD VOC」
  │     結果は web_search_cache/ にキャッシュ
  │
  ├─ 3. プロンプト構築
  │     - System: コンサル視点の 3C 分析担当
  │     - User content:
  │       * 案件 meta / PB コンセプト
  │       * ベース機種スペック（partner data）
  │       * 自社（AS ONE/ナビス）製品リスト
  │       * 競合各社の製品リスト・価格・スペック
  │       * Web 検索結果（市場・VOC・JTBD）
  │       * 出力フォーマット指示（Customer/Competitor/Company の章立て、最低文字数、表形式の指定）
  │
  ├─ 4. Claude Opus 4.7 ストリーミング呼び出し
  │     anthropic.messages.stream(model="claude-opus-4-7", ...)
  │
  └─ 5. SSE で逐次配信
        Server-Sent Events:
        - event: content_delta, data: {"text": "..."}
        - event: section_done, data: {"section": "Customer"}
        - event: complete, data: {"report_id": "..."}
        ↓
        ファイル保存: reports/<ts>_3c.md
        ↓
        ファイル保存: reports/<ts>_3c.meta.json
        ↓
[フロント: Markdown レンダリング、完了後 PDF ボタン活性化]
```

---

## 9. 3C プロンプト設計（要点）

LLM が「商品 DB だけの薄い結果」を出さないよう、プロンプトで以下を明示。

### 9.1 章立て指示
- **Customer**: 市場規模、セグメント別プロファイル、JTBD、ペルソナ、VOC、未充足ニーズ
- **Competitor**: 競合マッピング図記述、TOP 機種スペック比較表、各社訴求メッセージ、シェア推定、サポート密度、直近 12 ヶ月動向
- **Company**: アズワン PB の強み、既存ラインアップ整合（共食い検証）、製造パートナー側の強みは「補足」として軽く

### 9.2 ファクト引用ルール
- 数値・スペックは **スクレイピング結果から引用**（出典を機種型番で明示）
- VOC・市場動向は **Web 検索結果から引用**（出典 URL を脚注）
- データに無い情報は **「データに記載なし」と明記**、ハルシネーション禁止

### 9.3 出力フォーマット
- Markdown
- 表（パイプテーブル）を積極使用
- 各章の最低文字数を指定（Customer 800字以上、Competitor 1200字以上、Company 600字以上）
- 最終セクション「未充足ニーズ × 自社強みのクロス」だけは KSF/4P 完全版より軽く（次レポートへの橋渡し）

---

## 10. エラー処理

| ケース | 対応 |
|---|---|
| スクレイピング失敗（特定ソース） | 失敗を `scraping_progress.json` に記録、他ソースは続行。レポート生成時は欠損ソースを「データ未取得」明示。 |
| LLM 呼び出し失敗 | 3 回までリトライ（指数バックオフ）。最終失敗時は SSE で `event: error` 配信、案件詳細にエラーログ。 |
| Web 検索失敗 | 空結果として続行。プロンプト内で「市場データは取得失敗のため省略」を明示。 |
| 入力検証エラー | フォーム送信時に URL 形式・必須項目をチェック、フロントでエラーメッセージ。 |
| PDF 変換失敗 | Markdown は保存済みなので、再試行ボタンで PDF だけ再生成可能。 |

---

## 11. テスト計画

| 層 | テスト内容 |
|---|---|
| ユニット | `project_manager` の CRUD、`scraper_orchestrator` の進捗集計、`web_search` のフォールバック挙動 |
| スクレイパー | 既存スクレイパーはそのまま流用（既存テスト依存）。AS ONE/ナビス スクレイパーは新規実装のためモック HTML でテスト追加。 |
| LLM 出力構造 | プロンプトに対して、Claude 出力が「Customer/Competitor/Company」の章立てと最低文字数を満たすことを検証（実 API or 録画テスト） |
| E2E | 1 案件作成 → ソース登録 → スクレイピング → 3C レポート生成 → PDF エクスポート の通しシナリオ |
| 既存機能 | 既存チャット機能（PB カード設定・型番選定）に regressions が無いことを確認 |

---

## 12. リスク判定とロールバック

### 12.1 リスク判定
- **影響度**: 中（新規ルート・新規モジュール中心、既存チャットは触らない）
- **頻度**: 中（複数ファイル追加、Flask への新規ルート追加）
- **判定**: 🟠 **強化**（影響分析必須、テスト強化、Worktree までは不要）

### 12.2 ロールバック手順
- 新規ルートと新規モジュールは独立しているため、`git revert` で 1 コミット単位で戻せる構造でコミットする
- フロントは新規 URL（`/projects*`）のみ追加するため、既存 UI には影響しない
- スクレイピング結果ファイル（`projects/`）はゴミとして残るだけで実害なし

---

## 13. 段階リリース計画

| Phase | 内容 | 完了基準 |
|---|---|---|
| **P1** | 案件 CRUD + ソース登録 UI | `/projects/new` フォームから案件保存、`projects/<id>/meta.json` + `sources.json` 確認 |
| **P2** | スクレイピングオーケストレータ | 「スクレイピング開始」→ 既存 3 社スクレイパー実行 → `scraped/` に JSONL 保存、進捗 API 動作 |
| **P3** | AS ONE/ナビス スクレイパー新規実装 | AXEL カテゴリ × メーカーフィルタ URL から数十製品取得、JSONL 保存 |
| **P4** | 3C レポート生成パイプライン | 案件選択 → 機種選択 → Claude Opus 4.7 ストリーミング呼び出し → Markdown 保存。Web 検索なしでも動く状態。 |
| **P5** | 実行時 Web 検索統合 | Brave/Tavily/Claude WebSearch のいずれかでフォールバック付き検索、結果をプロンプト統合 |
| **P6** | PDF エクスポート + UI 仕上げ | Markdown → PDF、レポート画面 UI 完成、SSE 受信表示 |
| **P7** | E2E テスト + 本番デプロイ | Railway 反映後、実案件（オートクレーブ FLS-1000）で生成検証 |

---

## 14. オープン論点（実装計画フェーズで詰める）

- **Web 検索ツールの選定**: Brave Search MCP / Tavily / Claude WebSearch のどれを第一候補にするか（コスト・速度・精度）
- **AS ONE/ナビス スクレイパーのセレクタ設計**: AXEL の構造（一覧 → 詳細）を実物で確認してから実装
- **PDF 変換ライブラリ**: WeasyPrint / md2pdf / pandoc のいずれか（既存 docx 生成と整合）
- **案件 ID 形式**: UUID / タイムスタンプ / インクリメンタル
- **競合機種の自動同定**: ユーザーが型番を入力するが、スクレイパーが「正しい型番のページ」を特定するロジックの精度確認
- **ベース機種スペックと PB スペックの差分（spec_diff）の扱い**: 既存セッション機能との連携余地

---

## 15. 既存資産チェックリスト（実装着手前に再確認）

- [ ] `app.py` の `_load_all_products()` ロジックが `workspace/data/*/products.jsonl` 前提 → 新規 `projects/<id>/scraped/` をどう読むか（別ローダ作成）
- [ ] 既存 `analyze_framework("3c")` の `_gen_3c_visual()` 実装を確認（新版の品質目標として比較基準にする）
- [ ] `scripts/scraper_*.py` のインターフェースと出力フォーマットを確認
- [ ] `scripts/generate_full_proposal.py` の流用可否（既存提案書生成ロジックの一部が再利用できる可能性）
- [ ] Railway 環境変数（`ANTHROPIC_API_KEY` 等）の確認

---

## Appendix A: あるべき 3C 出力像（合意済み）

### Customer
- 市場規模・成長性、セグメント別プロファイル、JTBD、ペルソナ別ペイン、VOC 引用、未充足ニーズ

### Competitor
- 競合マッピング図、TOP10 機種スペック比較表、各社訴求メッセージと特許、シェア推定、チャネル・サポート密度、直近 12〜24 ヶ月動向

### Company（アズワン PB）
- アズワン PB ブランドの強み、既存 PB との整合（共食い検証）、販社チャネル適合性、製造パートナー（補足）

### 統合インサイト（軽め）
- 未充足ニーズ × 自社強みのクロス
- 次レポートへの橋渡し（KSF/STP/4P は別レポート）
