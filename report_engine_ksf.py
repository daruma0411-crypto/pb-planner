"""KSF レポート生成エンジン (Phase 2)"""
from report_helpers import (
    latest_report_md, save_stream_report, stream_with_anthropic, now_id,
)
import project_manager as _pm


def build_ksf_prompt(meta: dict, three_c_md: str, sources: dict) -> str:
    pos = sources.get("pos", {}) or {}
    sns = sources.get("sns", {}) or {}
    pos_text = pos.get("summary_note", "") or "(未投入)"
    sns_text = sns.get("summary_note", "") or "(未投入)"
    return f"""あなたはシニアマーケターです。直前の 3C レポート、自社（アズワン）POS データ、SNS の声を踏まえて以下を抽出してください。

# 案件概要
- 案件名: {meta.get('name','')}
- 対象カテゴリ: {meta.get('category','')}
- PB コンセプト: {meta.get('pb_concept','')}

# 入力: 3C レポート
{three_c_md}

# 入力: 自社 POS データ
{pos_text}

# 入力: SNS の声
{sns_text}

# 出力指示（Markdown、パイプテーブル積極利用）
1. **既存 NB（ナショナルブランド）に対する顧客ペイン 10 個**
   - 各ペインに「強度（高/中/低）」と「データ出典（3C/POS/SNS/競合）」を明記
   - ハルシネーション厳禁。データに無い場合は「データに記載なし」と明記
   - **NB が既に解決しているペインは KSF として弱い**（例：ベース機種が「片手開閉アシスト」「ローテーブル設計」で woman-friendly を訴求済みなら、それは PB の差別化ペインではない）。NB の design_concept / features を踏まえ、「NB が未解決のペイン」を優先列挙すること。
2. **業界 KSF（Key Success Factor）3-5 個**
   - ペインを解消する条件として帰納
   - 各 KSF に「自社充足度（◎/○/△/×）」と「**ベース機種の充足度（◎/○/△/×）**」の 2 列を併記。根拠も明記。
   - ベース機種が ◎ で充足している KSF は PB の独自軸として弱いので、その旨を注記。
3. **次フェーズ STP で意思決定すべき論点 5-7 個**

# ★最重要：ハルシネーション防止と「空白の真贋」を見極めるルール

1. **ベース機種の design_concept / features / description を必ず読み込め**。提供データ（3C レポート）に具体的な訴求文（例：「女性ユーザーの使用率の高さに着目」「片手開閉アシスト」「ローテーブル設計」）が書かれている場合、それは **既に NB として訴求済みの軸** であり、「空白地帯」「未充足ニーズ」と書いてはならない。

2. **ベース機種が既に satisfy している軸（例：woman-friendly, 人間工学, 片手開閉, 低設計）は、PB の独自差別化軸にしない**。それは「PB として再パッケージ可能な NB の強み」であり、別軸の追加価値が必要。

3. **真の差別化軸は「ベース機種が現状 satisfy していない弱点」から探せ**：
   - バリデーション / GMP / IQ-OQ 対応の弱さ
   - データ可搬性（USB / LAN / クラウド / スマホ通知）の欠如
   - 多言語 / 海外展開対応の不在
   - 価格（PB ならではの量販価格、機能限定版で -15〜25%）
   - 横置き / 前扉 / サニタリ仕様の対応
   - サブスク / 消耗品同梱モデル
   - NB の強み軸（woman-friendly 等）× 上記弱点補強の組み合わせ拡張

4. **STP の空白地帯マップは、上記弱点から導かれる「真の未開拓セグメント」のみ記載**。NB 訴求軸の言い換えは禁止。

5. **複数の差別化軸候補がある場合は 3 案以上を比較**してから 1 案に絞る。比較表で「狙いやすさ × 戦略適合性 × NB 弱点補強度」を評価。

6. ハルシネーション厳禁。データに無い場合は「データに記載なし」と明記。引用時はフェーズ番号や出典セクションを明示。

# データ前提（再掲・必須遵守）
- POS データ・SNS の声が手入力サマリ（summary_note）の場合は **「デモ用サンプル」「PoC 投入前」**の前提として扱い、レポート内で引用する数値・VOC には必ず「（サンプル）」「（ダミー値）」を併記すること。
- 出典明記時は「POS（サンプル）」「SNS（サンプル観測）」のように書き、実データと誤読されないようにすること。
- スクレイピング結果（asone/partner/competitor 配下の products.jsonl）は **実 EC データ** なので、こちらは「サンプル」注記不要。
- メーカー社名は日本語表記で統一（トミー精工 / ヤマト科学 / 平山 / アルプ / アズワン / ナビス）。英語表記（tomys / yamato / hirayama / alp）は使わない。
"""


def generate_ksf_stream(pid: str, save_report: bool = True):
    proj = _pm.get_project(pid)
    three_c = latest_report_md(pid, "3c")
    if three_c is None:
        raise RuntimeError("3C レポート未完了。先に 3C を生成してください")
    prompt = build_ksf_prompt(proj["meta"], three_c, proj["sources"])

    report_id = now_id("ksf")
    accumulated: list[str] = []

    def _save():
        if not save_report or not accumulated:
            return
        save_stream_report(pid, report_id, "".join(accumulated),
                           {"based_on_3c_chars": len(three_c)})

    try:
        yield f"[META] {report_id}\n"
        for chunk in stream_with_anthropic(prompt):
            accumulated.append(chunk)
            yield chunk
    finally:
        _save()
