---
date: 2026-05-14
project: pb-planner
title: 5 フェーズパイプライン (3C → KSF → STP → 4P → キャッチ+マスタ) 設計書
status: draft
risk: 🟠 強化
---

# 5 フェーズパイプライン設計書

## 1. 完成形

| Phase | フレームワーク | エージェントペルソナ | アウトプット |
|---|---|---|---|
| 1 | **3C** | シニア戦略コンサル | Customer/Competitor/Company 現状整理（既実装） |
| 2 | **KSF** | シニアマーケター | 既存 NB ペイン 10 個 + 業界 KSF 3-5 個 + 自社充足度 |
| 3 | **STP** | ブランドコンサル | セグメンテーション/ターゲット 3 パターン/ポジショニング |
| 4 | **4P** | プロダクトマーケター | Product/Price/Place/Promotion の具体戦術 |
| 5 | **キャッチ+マスタ** | コピーライター + PIM 担当 | キャッチ 3-5 案 + 商品マスタ JSON/CSV |

## 2. プロンプト雛形

### Phase 2: KSF（シニアマーケター）

```
あなたはシニアマーケターです。直前の 3C レポート、競合製品データ、自社（アズワン）POS データ、SNS の声を踏まえて以下を抽出してください。

## 入力データ
{3C レポート (md 全文)}
{POS データ}
{SNS データ}
{競合・自社製品リスト}

## 出力指示
1. **既存 NB（ナショナルブランド）に対する顧客ペイン 10 個**
   - 各ペインの強度（高/中/低）、データ出典（3C/POS/SNS/競合データ）を必ず明記
   - ハルシネーション禁止：データに無い場合は「データに記載なし」と書く
2. **業界 KSF（Key Success Factor）3-5 個**
   - ペインを解消する条件として帰納
   - 各 KSF への「自社充足度」(◎/○/△/×) 評価と根拠
3. **PB 企画上の論点リスト**
   - 次フェーズ STP で意思決定すべき問い 5-7 個

出力は Markdown、各セクションは見出し + パイプテーブル積極利用。
```

### Phase 3: STP（ブランドコンサル）

```
あなたはブランドコンサルです。前段の 3C と KSF レポートを踏まえ、自社製品ラインナップが満たせていない「空白地帯」を発見してください。

## 入力データ
{3C レポート md}
{KSF レポート md}
{自社既存ラインアップ}

## 出力指示
1. **Segmentation**: 軸 2 つ提示 → 4-9 セグメントのマトリクス
2. **Targeting**: 各セグメントを「狙いやすさ × 戦略適合性」評価、優先ターゲット **3 パターン** 定義
3. **Positioning**: 各ターゲットに対する独自ポジションのステートメント（「誰に / 何を / なぜ独自か」）
4. **空白地帯マップ**: KSF の充足度 × ターゲットセグメント のクロスで「ここは誰もやっていない」を 3 パターン提示
```

### Phase 4: 4P（プロダクトマーケター）

```
あなたはプロダクトマーケターです。前段の STP で選定した優先ターゲット 1 つを軸に、4P を具体仕様まで落としてください。

## 入力データ
{3C/KSF/STP レポート md}
{ベース機種スペック}
{競合機種スペック}

## 出力指示（ターゲット 1 つを user 指定 or 自動選択して以下を埋める）
1. **Product**: 機能仕様、スペック差分（ベース機種 vs PB 仕様）、開発リスク
2. **Price**: 想定販売価格、原価仮説、粗利率、競合との位置取り
3. **Place**: 流通チャネル、販促パートナー、必要在庫
4. **Promotion**: 訴求コピー（複数案）、販促媒体、初動キャンペーン

出力は Markdown 表形式。Promotion のコピー案は次フェーズで詰めるので軸提示のみ。
```

### Phase 5: キャッチ + マスタ（コピーライター + PIM 担当）

```
あなたはコピーライター兼 PIM 担当です。前段の 4P を踏まえて以下を完成させてください。

## 入力データ
{3C/KSF/STP/4P レポート md}
{ベース機種スペック}
{アズワン PIM フィールド定義}

## 出力指示
1. **キャッチコピー 3-5 案**: ターゲットペルソナに刺さる訴求、長短バリエーション、選定理由
2. **商品マスタ JSON**: アズワン PIM の必須フィールド全て埋める
   - asone_part_no, jan_code, maker_part_no, name, catch_copy, price, spec_diff（ベース機種からの差分）
   - 各フィールドに値 + 根拠（前フェーズのどこから来たか）
3. **アクションプラン**: 開発・調達・販促の 3 軸でマイルストーン（日付未確定なら相対 D+30 等）

出力末尾に CSV エクスポート用テーブル（パイプ表）も併記。
```

## 3. ファイル構成

### 新規
- `report_engine_ksf.py` — Phase 2
- `report_engine_stp.py` — Phase 3
- `report_engine_4p.py` — Phase 4
- `report_engine_finish.py` — Phase 5（キャッチ+マスタ）
- `report_helpers.py` — 共通: `_latest_report(pid, prefix)`, `_save_stream_report(...)`, `_stream_with_anthropic(prompt, max_tokens)`
- `templates/report_phase.html` — 共通レポート画面（クエリパラメータ `?phase=ksf|stp|4p|finish` で切替）
- `templates/project_steps.html` — 案件詳細にステップガイド追加（既存 project_detail.html を改修）
- `tests/test_report_engine_ksf.py` 〜 `_finish.py`
- `tests/test_report_helpers.py`

### 修正
- `report_engine_3c.py` — 共通ヘルパーへ寄せる（必要箇所のみ）
- `app.py` — 各フェーズの SSE エンドポイント追加、ステップ進捗 API 追加、WeasyPrint 撤退
- `templates/project_detail.html` — ステップガイドセクション追加
- `templates/report_3c.html` — `report_phase.html` 共通化 or 並存
- `requirements.txt` — `weasyprint`/`markdown` 削除（任意）
- `nixpacks.toml` — WeasyPrint 用 apt/nix 行削除

### 撤退
- `pdf_exporter.py` 削除（または stub 化）
- `tests/test_pdf_exporter.py` 削除

## 4. API エンドポイント

| メソッド | パス | 機能 |
|---|---|---|
| POST | `/api/projects/<pid>/reports/ksf` | KSF 生成 SSE |
| POST | `/api/projects/<pid>/reports/stp` | STP 生成 SSE |
| POST | `/api/projects/<pid>/reports/4p` | 4P 生成 SSE |
| POST | `/api/projects/<pid>/reports/finish` | キャッチ+マスタ生成 SSE |
| GET | `/api/projects/<pid>/reports/<rid>/html` | レポート HTML 化 + ダウンロード（PDF 代替） |
| GET | `/api/projects/<pid>/phases` | 各フェーズの完了状況一覧（JSON） |

既存 `/api/projects/<pid>/reports/3c` /`/<rid>/md` /`/<rid>/pdf` は維持。`/pdf` は WeasyPrint 撤退に伴い、本文を HTML レンダリング + ブラウザ印刷案内へ。

## 5. データフロー

```
案件作成 → ソース登録 → スクレイピング
  ↓
[Phase 1] /reports/3c → reports/3c_YYYY..md
  ↓
[Phase 2] /reports/ksf  (3C md を input に読み込み) → reports/ksf_YYYY..md
  ↓
[Phase 3] /reports/stp  (3C + KSF md) → reports/stp_YYYY..md
  ↓
[Phase 4] /reports/4p   (3C + KSF + STP md) → reports/4p_YYYY..md
  ↓
[Phase 5] /reports/finish (全 md) → reports/finish_YYYY..md
                                  → reports/master_YYYY..csv (任意エクスポート)
```

各フェーズ：前段の最新レポート（`reports/<prefix>_*.md` を mtime 降順で先頭）を自動取得。前段未完了なら 409 を返す。

## 6. UI 改修

### 案件詳細ページ（`/projects/<pid>`）

既存ソース登録セクションの後に追加：

```
┌─ フェーズ進捗 ─────────────────────────────┐
│  ① 案件設定        ✓                       │
│  ② スクレイピング   ✓ (45件取得)            │
│  ③ 3C 分析          ✓  [レポートを開く →]  │
│  ④ KSF 抽出         [実行] (3C 完了で活性)  │
│  ⑤ STP 設計         (KSF 完了で活性)        │
│  ⑥ 4P 設計          (STP 完了で活性)        │
│  ⑦ キャッチ + マスタ (4P 完了で活性)        │
└────────────────────────────────────────┘
```

各「実行」押下で `/projects/<pid>/report?phase=ksf` 等へ遷移、SSE 受信で生成。

### レポート画面共通化（`templates/report_phase.html`）

`?phase=ksf|stp|4p|finish` でタイトル・API パス・次フェーズリンクを切替。マークダウンレンダ・MD ダウンロード・「印刷で PDF 化」ボタンは共通。

## 7. 実装順序（並列タスク）

### Track A（report engines + API）
1. `report_helpers.py` 共通基盤（`_latest_report`, `_stream_with_anthropic`, `_save_stream_report`）
2. `report_engine_ksf.py` + tests + `/reports/ksf` SSE
3. `report_engine_stp.py` + tests + `/reports/stp` SSE
4. `report_engine_4p.py` + tests + `/reports/4p` SSE
5. `report_engine_finish.py` + tests + `/reports/finish` SSE
6. `/api/projects/<pid>/phases` 進捗集計 API

### Track B（UI + HTML 出力 + PDF 撤退）
1. `templates/project_detail.html` にステップガイドセクション追加 + フェーズ進捗 fetch
2. `templates/report_phase.html` 共通テンプレ（既存 report_3c.html 改造 or 新規）
3. `/api/projects/<pid>/reports/<rid>/html` エンドポイント追加（CSS インライン込み）
4. `templates/report_phase.html` に `@media print` CSS 充実（A4 余白、改ページ、フォント、ヘッダ）
5. WeasyPrint 関連削除: `pdf_exporter.py`, `tests/test_pdf_exporter.py`, `requirements.txt`, `nixpacks.toml`, `/pdf` ルート

### Track C（AXEL 修正）
1. background `bx590kb8e` の debug fetch 結果で原因確定
2. パターン別対応（β: scraper 修正、γ: セレクタ修正、δ: Playwright 化）

## 8. 共通ヘルパー仕様（`report_helpers.py`）

```python
def latest_report_md(pid: str, prefix: str) -> str | None:
    """reports/<prefix>_*.md の中で最新を読んで返す。なければ None"""

def list_phase_reports(pid: str) -> dict:
    """{'3c': [...], 'ksf': [...], 'stp': [...], '4p': [...], 'finish': [...]} を返す"""

def save_stream_report(pid: str, report_id: str, md_text: str, meta: dict) -> None:
    """reports/<rid>.md と .meta.json を保存（_atomic_write_json 経由）"""

def stream_with_anthropic(prompt: str, max_tokens: int = 8000):
    """Anthropic stream を generator として yield、accumulated を返す。
    try/finally で必ず保存できる構造。
    """
```

## 9. 各 report_engine_*.py の共通テンプレート

```python
def generate_<phase>_stream(pid: str, **kwargs):
    proj = _pm.get_project(pid)
    # 前段レポートを必須として読み込み
    three_c = latest_report_md(pid, "3c")
    if three_c is None:
        raise RuntimeError("3C レポート未完了。先に 3C を生成してください")
    # 同様に ksf, stp, 4p ...

    prompt = build_<phase>_prompt(proj, three_c, ksf, stp, 4p, data, kwargs)

    report_id = f"<phase>_{ts}"
    accumulated = []
    try:
        yield f"[META] {report_id}\n"
        for chunk in stream_with_anthropic(prompt):
            accumulated.append(chunk)
            yield chunk
    finally:
        save_stream_report(pid, report_id, "".join(accumulated), {...})
```

## 10. リスク・既知課題

- **Anthropic API コスト**: フェーズあたり 8000 token x ($15 in + $75 out / 1M) ≈ ¥80-100 円。5 フェーズで ¥400-500 円/案件
- **前段未完了の制御**: API 側で 409 返却 + UI のステップガイドで非活性化
- **Railway ephemeral fs**: 全レポートが再デプロイで消失。明日デモまでには Volume 設定 or 一時的にデモ用案件を再生成可能にする
- **デモ当日リスク**: 1 ユーザー（プレゼンター）が触る範囲は限定的、全 5 フェーズを実演する想定

## 11. デモシナリオ（明日 2026-05-15）

1. 案件「アズワン PB 100L オートクレーブ」を作成
2. ソース登録（事前準備済 URL リスト）→ スクレイピング起動
3. 3C 一発生成 → 完了
4. KSF 一発生成 → ペイン 10 個 + KSF 4 個出力
5. STP 一発生成 → 空白地帯 3 パターン提示
6. 4P 一発生成 → 具体戦術
7. キャッチ+マスタ 一発生成 → 提出可能な商品マスタ JSON/CSV
8. 全レポートをブラウザ印刷で PDF 化、提案書一式として出力
