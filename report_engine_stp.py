"""STP レポート生成エンジン (Phase 3)"""
from report_helpers import (
    latest_report_md, save_stream_report, stream_with_anthropic, now_id,
)
import project_manager as _pm


def build_stp_prompt(meta: dict, three_c_md: str, ksf_md: str, sources: dict) -> str:
    return f"""あなたはブランドコンサルです。前段の 3C と KSF レポートを踏まえ、自社製品ラインナップが満たせていない「空白地帯」を発見してください。

# 案件概要
- 案件名: {meta.get('name','')}
- 対象カテゴリ: {meta.get('category','')}
- PB コンセプト: {meta.get('pb_concept','')}

# 入力: 3C レポート
{three_c_md}

# 入力: KSF レポート
{ksf_md}

# 出力指示（Markdown、パイプテーブル積極利用）
1. **Segmentation**: 軸 2 つ提示 → 4-9 セグメントのマトリクス（パイプ表）
2. **Targeting**: 各セグメントを「狙いやすさ × 戦略適合性」で評価、優先ターゲット **3 パターン** を定義
3. **Positioning**: 各ターゲットに対する独自ポジションのステートメント（「誰に / 何を / なぜ独自か」）
4. **空白地帯マップ**: KSF の充足度 × ターゲットセグメント のクロスで「ここは誰もやっていない」を 3 パターン提示

ハルシネーション厳禁。3C / KSF に無い情報は「データに記載なし」と明記。
"""


def generate_stp_stream(pid: str, save_report: bool = True):
    proj = _pm.get_project(pid)
    three_c = latest_report_md(pid, "3c")
    if three_c is None:
        raise RuntimeError("3C レポート未完了。先に 3C を生成してください")
    ksf = latest_report_md(pid, "ksf")
    if ksf is None:
        raise RuntimeError("KSF レポート未完了。先に KSF を生成してください")
    prompt = build_stp_prompt(proj["meta"], three_c, ksf, proj["sources"])

    report_id = now_id("stp")
    accumulated: list[str] = []

    def _save():
        if not save_report or not accumulated:
            return
        save_stream_report(pid, report_id, "".join(accumulated), {
            "based_on_3c_chars": len(three_c),
            "based_on_ksf_chars": len(ksf),
        })

    try:
        yield f"[META] {report_id}\n"
        for chunk in stream_with_anthropic(prompt):
            accumulated.append(chunk)
            yield chunk
    finally:
        _save()
