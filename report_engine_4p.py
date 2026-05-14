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
2. **Price**: 想定販売価格、原価仮説、粗利率、競合との位置取り
3. **Place**: 流通チャネル、販促パートナー、必要在庫
4. **Promotion**: 訴求コピーの軸（複数案）、販促媒体、初動キャンペーン
   - ※ コピー本文は次フェーズで詰めるので、ここでは「軸」のみ提示

ハルシネーション厳禁。前段に無い情報は「データに記載なし」と明記。
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
