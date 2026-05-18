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
   - **NB（ベース機種）の訴求軸を踏襲しすぎないこと**。例：NB が既に「女性に優しい」「片手で開閉」を訴求済みなら、PB のキャッチコピーで同じ軸を繰り返しても差別化にならない。PB ならではの追加軸（弱点補強：GMP / データ可搬性 / 価格 / サブスク / 横置き等）を必ず 1 つ以上組み込む。
2. **商品マスタ JSON**: アズワン PIM の必須フィールドを全て埋める。`json` コードブロックで出力
   - 必須フィールド: asone_part_no, jan_code, maker_part_no, name, catch_copy, price, spec_diff (ベース機種からの差分)
   - **spec_diff（ベース機種からの差分）は最重要フィールドとして強調**。NB と同じ仕様の項目ではなく、PB として「追加した・削った・変えた」項目のみを列挙。NB と同一なら "NB 同等" と明記。
   - 各フィールドに **値 + 根拠**（前フェーズのどこから来たか）を併記
3. **アクションプラン**: 開発・調達・販促の 3 軸でマイルストーン（日付未確定なら相対 D+30 等）
4. **CSV エクスポート用テーブル**: 商品マスタの内容をパイプ表で再掲（CSV 化しやすい形）

# ★最重要：ハルシネーション防止と「空白の真贋」を見極めるルール

1. **ベース機種の design_concept / features / description を必ず読み込め**。前段（3C）に具体的な訴求文（例：「女性ユーザーの使用率の高さに着目」「片手開閉アシスト」「ローテーブル設計」）が書かれている場合、それは **既に NB として訴求済みの軸** であり、「PB の独自訴求」「空白地帯」と書いてはならない。

2. **ベース機種が既に satisfy している軸（例：woman-friendly, 人間工学, 片手開閉, 低設計）は、PB の独自差別化軸にしない**。それは「PB として再パッケージ可能な NB の強み」であり、別軸の追加価値が必要。キャッチコピーでも NB 訴求軸を単純コピペしない。

3. **真の差別化軸は「ベース機種が現状 satisfy していない弱点」から探せ**：
   - バリデーション / GMP / IQ-OQ 対応の弱さ
   - データ可搬性（USB / LAN / クラウド / スマホ通知）の欠如
   - 多言語 / 海外展開対応の不在
   - 価格（PB ならではの量販価格、機能限定版で -15〜25%）
   - 横置き / 前扉 / サニタリ仕様の対応
   - サブスク / 消耗品同梱モデル
   - NB の強み軸（woman-friendly 等）× 上記弱点補強の組み合わせ拡張

4. **キャッチコピー候補は 3 案以上を比較**してから 1 案を推奨に絞る。比較表で「ターゲット適合度 × NB との差分明確度 × NB 弱点補強度」を評価。

5. ハルシネーション厳禁。前段に無い情報は「データに記載なし」と明記。引用時はフェーズ番号や出典セクションを明示。

# データ前提（再掲・必須遵守）
- POS データ・SNS の声が手入力サマリ（summary_note）の場合は **「デモ用サンプル」「PoC 投入前」**の前提として扱い、レポート内で引用する数値・VOC には必ず「（サンプル）」「（ダミー値）」を併記すること。
- 出典明記時は「POS（サンプル）」「SNS（サンプル観測）」のように書き、実データと誤読されないようにすること。
- スクレイピング結果（asone/partner/competitor 配下の products.jsonl）は **実 EC データ** なので、こちらは「サンプル」注記不要。
- メーカー社名は日本語表記で統一（トミー精工 / ヤマト科学 / 平山 / アルプ / アズワン / ナビス）。英語表記（tomys / yamato / hirayama / alp）は使わない。
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
