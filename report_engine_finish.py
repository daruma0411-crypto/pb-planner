"""キャッチ+マスタ レポート生成エンジン (Phase 5)"""
from report_helpers import (
    latest_report_md, save_stream_report, stream_with_anthropic, now_id,
)
import project_manager as _pm


def build_finish_prompt(meta: dict, three_c_md: str, ksf_md: str,
                        stp_md: str, fourp_md: str, sources: dict) -> str:
    return f"""あなたはコピーライター兼 PIM 担当です。前段の 4P を踏まえてキャッチコピーと商品マスタを完成させてください。

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

# 入力: 4P レポート
{fourp_md}

# 出力指示（Markdown、パイプテーブル積極利用）
1. **キャッチコピー 3-5 案**: ターゲットペルソナに刺さる訴求、長短バリエーション、各案の選定理由
2. **商品マスタ JSON**: アズワン PIM の必須フィールドを全て埋める。`json` コードブロックで出力
   - 必須フィールド: asone_part_no, jan_code, maker_part_no, name, catch_copy, price, spec_diff (ベース機種からの差分)
   - 各フィールドに **値 + 根拠**（前フェーズのどこから来たか）を併記
3. **アクションプラン**: 開発・調達・販促の 3 軸でマイルストーン（日付未確定なら相対 D+30 等）
4. **CSV エクスポート用テーブル**: 商品マスタの内容をパイプ表で再掲（CSV 化しやすい形）

ハルシネーション厳禁。前段に無い情報は「データに記載なし」と明記。
"""


def generate_finish_stream(pid: str, save_report: bool = True):
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
    fourp = latest_report_md(pid, "4p")
    if fourp is None:
        raise RuntimeError("4P レポート未完了。先に 4P を生成してください")
    prompt = build_finish_prompt(proj["meta"], three_c, ksf, stp, fourp, proj["sources"])

    report_id = now_id("finish")
    accumulated: list[str] = []

    def _save():
        if not save_report or not accumulated:
            return
        save_stream_report(pid, report_id, "".join(accumulated), {
            "based_on_3c_chars": len(three_c),
            "based_on_ksf_chars": len(ksf),
            "based_on_stp_chars": len(stp),
            "based_on_4p_chars": len(fourp),
        })

    try:
        yield f"[META] {report_id}\n"
        for chunk in stream_with_anthropic(prompt):
            accumulated.append(chunk)
            yield chunk
    finally:
        _save()
