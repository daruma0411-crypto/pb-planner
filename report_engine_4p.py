"""4P レポート生成エンジン (Phase 4)"""
from report_helpers import (
    latest_report_md, save_stream_report, stream_with_anthropic, now_id,
)
import project_manager as _pm


def build_4p_prompt(meta: dict, three_c_md: str, ksf_md: str, stp_md: str, sources: dict) -> str:
    return f"""あなたはプロダクトマーケターです。前段の STP で選定した優先ターゲット 1 つを軸に、4P を具体仕様まで落としてください。

# 案件概要
- 案件名: {meta.get('name','')}
- 対象カテゴリ: {meta.get('category','')}
- PB コンセプト: {meta.get('pb_concept','')}

# 入力: 3C レポート
{three_c_md}

# 入力: KSF レポート
{ksf_md}

# 入力: STP レポート
{stp_md}

# 出力指示（Markdown 表形式、パイプテーブル積極利用）
STP の優先ターゲット 3 パターンから 1 つを選定（選定理由を冒頭で 1 段落明記）し、以下を埋める。

1. **Product**: 機能仕様、スペック差分（ベース機種 vs PB 仕様）、開発リスク
   - **必ず以下のパイプ表で構造化**：
     - 列：機能項目 / NB（ベース機種）の features / PB の追加機能（NB 弱点を補強する独自軸） / 開発難易度
     - 「NB の features を継承する項目」と「PB ならではの追加機能（弱点補強）」を明確に分けて記載。NB が既訴求済みの軸（例：woman-friendly, 片手開閉）を PB の独自機能として書かない。
2. **Price**: 想定販売価格、原価仮説、粗利率、競合との位置取り
   - **NB（ベース機種）比 ±%** を必ず明示（例：「NB 価格 ¥250,000 比 -18%（¥205,000）」）。
3. **Place**: 流通チャネル、販促パートナー、必要在庫
4. **Promotion**: 訴求コピーの軸（複数案）、販促媒体、初動キャンペーン
   - ※ コピー本文は次フェーズで詰めるので、ここでは「軸」のみ提示

# ★最重要：ハルシネーション防止と「空白の真贋」を見極めるルール

1. **ベース機種の design_concept / features / description を必ず読み込め**。前段（3C）に具体的な訴求文（例：「女性ユーザーの使用率の高さに着目」「片手開閉アシスト」「ローテーブル設計」）が書かれている場合、それは **既に NB として訴求済みの軸** であり、「PB の差別化機能」「空白地帯」と書いてはならない。

2. **ベース機種が既に satisfy している軸（例：woman-friendly, 人間工学, 片手開閉, 低設計）は、PB の独自差別化軸にしない**。それは「PB として再パッケージ可能な NB の強み」であり、別軸の追加価値が必要。

3. **真の差別化軸は「ベース機種が現状 satisfy していない弱点」から探せ**：
   - バリデーション / GMP / IQ-OQ 対応の弱さ
   - データ可搬性（USB / LAN / クラウド / スマホ通知）の欠如
   - 多言語 / 海外展開対応の不在
   - 価格（PB ならではの量販価格、機能限定版で -15〜25%）
   - 横置き / 前扉 / サニタリ仕様の対応
   - サブスク / 消耗品同梱モデル
   - NB の強み軸（woman-friendly 等）× 上記弱点補強の組み合わせ拡張

4. **複数の Product 仕様候補がある場合は 3 案以上を比較**してから 1 案に絞る。比較表で「狙いやすさ × 戦略適合性 × NB 弱点補強度」を評価。

5. ハルシネーション厳禁。前段に無い情報は「データに記載なし」と明記。引用時はフェーズ番号や出典セクションを明示。

# データ前提（再掲・必須遵守）
- POS データ・SNS の声が手入力サマリ（summary_note）の場合は **「デモ用サンプル」「PoC 投入前」**の前提として扱い、レポート内で引用する数値・VOC には必ず「（サンプル）」「（ダミー値）」を併記すること。
- 出典明記時は「POS（サンプル）」「SNS（サンプル観測）」のように書き、実データと誤読されないようにすること。
- スクレイピング結果（asone/partner/competitor 配下の products.jsonl）は **実 EC データ** なので、こちらは「サンプル」注記不要。
- メーカー社名は日本語表記で統一（トミー精工 / ヤマト科学 / 平山 / アルプ / アズワン / ナビス）。英語表記（tomys / yamato / hirayama / alp）は使わない。
"""


def generate_4p_stream(pid: str, save_report: bool = True):
    proj = _pm.get_project(pid)
    three_c = latest_report_md(pid, "3c")
    if three_c is None:
        raise RuntimeError("3C レポート未完了。先に 3C を生成してください")
    ksf = latest_report_md(pid, "ksf")
    if ksf is None:
        raise RuntimeError("KSF レポート未完了。先に KSF を生成してください")
    stp = latest_report_md(pid, "stp")
    if stp is None:
        raise RuntimeError("STP レポート未完了。先に STP を生成してください")
    prompt = build_4p_prompt(proj["meta"], three_c, ksf, stp, proj["sources"])

    report_id = now_id("4p")
    accumulated: list[str] = []

    def _save():
        if not save_report or not accumulated:
            return
        save_stream_report(pid, report_id, "".join(accumulated), {
            "based_on_3c_chars": len(three_c),
            "based_on_ksf_chars": len(ksf),
            "based_on_stp_chars": len(stp),
        })

    try:
        yield f"[META] {report_id}\n"
        for chunk in stream_with_anthropic(prompt):
            accumulated.append(chunk)
            yield chunk
    finally:
        _save()
