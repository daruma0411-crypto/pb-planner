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
3. **Company（アズワン PB ブランド = AS ONE + ナビス）**（最低600字）: PB ブランドの強み、既存ラインアップとの整合（共食い検証）、販社チャネル適合性、製造パートナー（補足）
4. **最終セクション**: 未充足ニーズ × 自社強みのクロスを軽く（KSF/4P は別レポート扱い）

**ルール**:
- スペック・価格は提供データから引用。データに無い情報は「データに記載なし」と明記。
- VOC・市場動向は Web 検索結果から引用、出典 URL を脚注。
- ハルシネーション厳禁。表は Markdown パイプテーブルで作る。
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
    web_results = _collect_web_results(
        proj["meta"]["category"],
        [c["maker"] for c in proj["sources"].get("competitor", [])],
    )
    prompt = build_prompt(proj["meta"], base_model, data, web_results)

    client = Anthropic()
    accumulated = []
    with client.messages.stream(
        model=MODEL_ID,
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        from datetime import datetime, timezone, timedelta
        JST = timezone(timedelta(hours=9))
        ts = datetime.now(JST).strftime("%Y%m%d_%H%M%S")
        report_id = f"3c_{ts}"
        yield f"[META] {report_id}\n"
        for text in stream.text_stream:
            accumulated.append(text)
            yield text

    if save_report:
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
