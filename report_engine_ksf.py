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
2. **業界 KSF（Key Success Factor）3-5 個**
   - ペインを解消する条件として帰納
   - 各 KSF に「自社充足度（◎/○/△/×）」と根拠を明記
3. **次フェーズ STP で意思決定すべき論点 5-7 個**
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
