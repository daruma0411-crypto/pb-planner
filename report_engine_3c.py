"""3C レポート生成エンジン"""
import json
import os
from anthropic import Anthropic

import project_manager as _pm
import web_search


MODEL_ID = "claude-opus-4-7"


def load_project_data(pid: str) -> dict:
    """案件の scraped データを集約"""
    pdir = _pm._project_dir(pid)
    out = {"asone": [], "partner": {}, "competitor": {}}

    def _read_jsonl(path):
        items = []
        if not os.path.exists(path):
            return items
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    items.append(json.loads(line))
        return items

    out["asone"] = _read_jsonl(os.path.join(pdir, "scraped", "asone", "products.jsonl"))
    partner_dir = os.path.join(pdir, "scraped", "partner")
    if os.path.exists(partner_dir):
        for fname in os.listdir(partner_dir):
            if fname.endswith(".jsonl"):
                key = fname[:-len(".jsonl")]
                out["partner"][key] = _read_jsonl(os.path.join(partner_dir, fname))
    comp_dir = os.path.join(pdir, "scraped", "competitor")
    if os.path.exists(comp_dir):
        for maker in os.listdir(comp_dir):
            jsonl_path = os.path.join(comp_dir, maker, "products.jsonl")
            if os.path.exists(jsonl_path):
                out["competitor"][maker] = _read_jsonl(jsonl_path)
    return out


def _format_products(items: list[dict]) -> str:
    if not items:
        return "(データなし)"
    lines = []
    for it in items[:40]:
        specs = it.get("specs") or {}
        spec_str = ", ".join(f"{k}={v}" for k, v in list(specs.items())[:8])
        lines.append(f"- {it.get('maker','?')} {it.get('model','?')} {it.get('name','')} "
                     f"価格={it.get('price','?')} | {spec_str}")
    return "\n".join(lines)


def build_prompt(meta: dict, base_model: dict, data: dict, web_results: list[dict]) -> str:
    """3C プロンプトを構築"""
    parts = []
    parts.append(f"""あなたはアズワンの PB企画コンサルタントです。以下の案件について、プロのマーケッター成果物相当の厚みを持つ **3C 分析レポート**を Markdown 形式で生成してください。

# 案件概要
- 案件名: {meta.get('name','')}
- 対象カテゴリ: {meta.get('category','')}
- PB コンセプト: {meta.get('pb_concept','')}
- ベース機種候補: {base_model.get('maker','?')} {base_model.get('model','?')}

# 出力指示
1. **Customer**（最低800字）: 市場規模・成長性、セグメント別プロファイル（大学/製薬/食品/医療/バイオ）、JTBD、ペルソナ別ペイン、VOC 引用、未充足ニーズ
2. **Competitor**（最低1200字）: 競合マッピング図記述、TOP 機種スペック比較表（パイプテーブル）、各社訴求メッセージ、シェア推定、サポート密度、直近 12-24 ヶ月動向
   - **各 NB の design_concept / features / description を構造化して列挙**（訴求軸・人間工学・データ可搬性・GMP/バリデーション・価格帯・サポート等のカテゴリで分類）
3. **Company（アズワン PB ブランド = AS ONE + ナビス）**（最低600字）: PB ブランドの強み、既存ラインアップとの整合（共食い検証）、販社チャネル適合性、製造パートナー（補足）
   - **アズワン PB 既存ラインアップ vs ベース機種 NB の訴求差分**を整理（何が同じで、何が違うか / PB として上書きすべき軸はどこか）
4. **最終セクション**: 未充足ニーズ × 自社強みのクロスを軽く（KSF/4P は別レポート扱い）

**ルール**:
- スペック・価格は提供データから引用。データに無い情報は「データに記載なし」と明記。
- VOC・市場動向は Web 検索結果から引用、出典 URL を脚注。
- ハルシネーション厳禁。表は Markdown パイプテーブルで作る。

# ★最重要：ハルシネーション防止と「空白の真贋」を見極めるルール

1. **ベース機種の design_concept / features / description を必ず読み込め**。提供データに具体的な訴求文（例：「女性ユーザーの使用率の高さに着目」「片手開閉アシスト」「ローテーブル設計」）が書かれている場合、それは **既に NB として訴求済みの軸** であり、「空白地帯」「未充足ニーズ」と書いてはならない。

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
""")

    parts.append("\n# 提供データ\n")
    parts.append("\n## 自社（AS ONE / ナビス）製品一覧\n")
    parts.append(_format_products(data.get("asone", [])))

    parts.append("\n\n## 製造パートナー製品（ベース機種候補周辺）\n")
    for maker, items in (data.get("partner") or {}).items():
        parts.append(f"\n### {maker}\n")
        parts.append(_format_products(items))

    parts.append("\n\n## 競合製品\n")
    for maker, items in (data.get("competitor") or {}).items():
        parts.append(f"\n### {maker}\n")
        parts.append(_format_products(items))

    # POS / SNS（次フェーズで実データ投入予定。現状は手入力サマリ or 空）
    sources = data.get("_sources", {})
    pos = sources.get("pos", {})
    sns = sources.get("sns", {})

    parts.append("\n\n## 顧客（アズワン）POS データ\n")
    if pos.get("summary_note") or pos.get("csv_text"):
        if pos.get("summary_note"):
            parts.append(f"- 手入力サマリ: {pos['summary_note']}")
        if pos.get("csv_text"):
            # CSV を最大 2000 字で要約
            parts.append(f"- CSV 抜粋:\n```\n{pos['csv_text'][:2000]}\n```")
    else:
        parts.append("（POS データ未投入 — Customer セクションの市場規模・販売動向はデータに記載なしと明記）")

    parts.append("\n\n## SNS の声\n")
    if sns.get("summary_note") or sns.get("queries") or sns.get("accounts"):
        if sns.get("summary_note"):
            parts.append(f"- 手入力サマリ: {sns['summary_note']}")
        if sns.get("queries"):
            parts.append(f"- 監視クエリ: {', '.join(sns['queries'])}")
        if sns.get("accounts"):
            parts.append(f"- 監視アカウント: {', '.join(sns['accounts'])}")
    else:
        parts.append("（SNS データ未投入 — VOC は一般傾向のみで構成）")

    if web_results:
        parts.append("\n\n## Web 検索結果（顧客・市場・VOC）\n")
        for r in web_results:
            parts.append(f"- [{r.get('title','')}]({r.get('url','')}): {r.get('content','')[:300]}")
    return "\n".join(parts)


def _collect_web_results(category: str, competitor_makers: list[str]) -> list[dict]:
    """市場・JTBD・VOC・競合評判 を Web 検索で取得"""
    queries = [
        f"{category} 市場規模 日本",
        f"{category} 用途 セグメント 大学 製薬 食品",
        f"{category} 選定基準 ペインポイント",
    ]
    for maker in competitor_makers[:3]:
        queries.append(f"{maker} {category} 評判 レビュー")

    results = []
    for q in queries:
        results.extend(web_search.search(q, num_results=3))
    return results


def generate_3c_stream(pid: str, base_model: dict, save_report: bool = True):
    """3C レポートをストリーミング生成。yield で文字列を返す。
    最初に '[META] <report_id>' を yield、以降は本文 chunk。
    """
    proj = _pm.get_project(pid)
    data = load_project_data(pid)
    data["_sources"] = proj["sources"]
    web_results = _collect_web_results(
        proj["meta"]["category"],
        [c["maker"] for c in proj["sources"].get("competitor", [])],
    )
    prompt = build_prompt(proj["meta"], base_model, data, web_results)

    from datetime import datetime, timezone, timedelta
    JST = timezone(timedelta(hours=9))
    ts = datetime.now(JST).strftime("%Y%m%d_%H%M%S")
    report_id = f"3c_{ts}"
    accumulated: list[str] = []

    def _save():
        if not save_report or not accumulated:
            return
        reports_dir = os.path.join(_pm._project_dir(pid), "reports")
        os.makedirs(reports_dir, exist_ok=True)
        md_text = "".join(accumulated)
        with open(os.path.join(reports_dir, f"{report_id}.md"), "w", encoding="utf-8") as f:
            f.write(md_text)
        meta = {
            "report_id": report_id,
            "base_model": base_model,
            "char_count": len(md_text),
            "web_results_count": len(web_results),
        }
        with open(os.path.join(reports_dir, f"{report_id}.meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

    client = Anthropic()
    try:
        yield f"[META] {report_id}\n"
        with client.messages.stream(
            model=MODEL_ID,
            max_tokens=8000,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                accumulated.append(text)
                yield text
    finally:
        # GeneratorExit / StopIteration / 例外いずれでも保存（クライアント切断対策）
        _save()
