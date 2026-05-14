"""5 フェーズパイプライン 共通ヘルパー"""
import json
import os
import glob
from datetime import datetime, timezone, timedelta

import project_manager as _pm


JST = timezone(timedelta(hours=9))


def now_id(prefix: str) -> str:
    ts = datetime.now(JST).strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{ts}"


def latest_report_md(pid: str, prefix: str) -> str | None:
    """reports/<prefix>_*.md の中で最新を読んで返す。なければ None"""
    pdir = _pm._project_dir(pid)
    pattern = os.path.join(pdir, "reports", f"{prefix}_*.md")
    files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    if not files:
        return None
    with open(files[0], encoding="utf-8") as f:
        return f.read()


def list_phase_reports(pid: str) -> dict:
    """全 phase の レポート一覧を返す"""
    out = {p: [] for p in ("3c", "ksf", "stp", "4p", "finish")}
    pdir = _pm._project_dir(pid)
    reports_dir = os.path.join(pdir, "reports")
    if not os.path.exists(reports_dir):
        return out
    for f in sorted(os.listdir(reports_dir)):
        if not f.endswith(".md"):
            continue
        for prefix in out.keys():
            if f.startswith(f"{prefix}_"):
                rid = f[:-len(".md")]
                out[prefix].append(rid)
                break
    return out


def save_stream_report(pid: str, report_id: str, md_text: str, meta_extra: dict | None = None) -> None:
    """reports/<rid>.md と .meta.json を保存"""
    pdir = _pm._project_dir(pid)
    reports_dir = os.path.join(pdir, "reports")
    os.makedirs(reports_dir, exist_ok=True)
    with open(os.path.join(reports_dir, f"{report_id}.md"), "w", encoding="utf-8") as f:
        f.write(md_text)
    meta = {
        "report_id": report_id,
        "char_count": len(md_text),
        "saved_at": datetime.now(JST).isoformat(),
    }
    if meta_extra:
        meta.update(meta_extra)
    with open(os.path.join(reports_dir, f"{report_id}.meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def stream_with_anthropic(prompt: str, max_tokens: int = 8000):
    """Anthropic stream を yield しつつ accumulated を内部蓄積。
    使い方:
        accumulated = []
        for chunk in stream_with_anthropic(prompt):
            accumulated.append(chunk)
            yield chunk
    """
    from anthropic import Anthropic
    client = Anthropic()
    with client.messages.stream(
        model="claude-opus-4-7",
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for text in stream.text_stream:
            yield text
