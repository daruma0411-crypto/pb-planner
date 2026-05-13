"""AS ONE / ナビス AXEL スクレイパー"""
import json
import os
import re
from urllib.parse import urljoin
from bs4 import BeautifulSoup

from scripts.scraper_base import fetch, parse_spec_table


PB_BRAND_KEYWORDS = ("アズワン", "ナビス", "AS ONE", "NAVIS", "AS_ONE")


def parse_product_list(html: str, base_url: str = "https://axel.as-1.co.jp") -> list[dict]:
    """AXEL 商品一覧 HTML から商品リストを抽出。

    AXEL の商品詳細 URL パターン: /asone/d/<品番>/?from=<カテゴリID>
    """
    soup = BeautifulSoup(html, 'html.parser')
    items = []
    for a in soup.select('a[href*="/asone/d/"]'):
        name = a.get_text(strip=True)
        href = a.get('href', '')
        if not href:
            continue
        url = urljoin(base_url, href)
        # 親要素からメーカー名を推定
        parent = a.find_parent(['li', 'div', 'tr', 'article'])
        maker = ""
        if parent:
            text = parent.get_text(' ', strip=True)
            for kw in PB_BRAND_KEYWORDS:
                if kw in text:
                    maker = "アズワン" if kw in ("アズワン", "AS ONE", "AS_ONE") else "ナビス"
                    break
        # 名前が空の場合は alt や title 属性も試す
        if not name:
            img = a.find('img')
            if img:
                name = img.get('alt', '') or img.get('title', '')
        if not name:
            continue
        items.append({"name": name, "url": url, "maker": maker})
    # 重複除去
    seen = set()
    out = []
    for it in items:
        key = it["url"].split("?")[0]  # クエリ違いの重複も除外
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def filter_pb_brands(items: list[dict]) -> list[dict]:
    """AS ONE / ナビス ブランドのみ残す"""
    out = []
    for it in items:
        m = (it.get("maker") or "").strip()
        if any(kw in m for kw in ("アズワン", "ナビス", "AS ONE", "NAVIS")):
            out.append(it)
    return out


def parse_product_detail(html: str) -> dict:
    """商品詳細ページから名前・型番・価格・スペックを抽出"""
    soup = BeautifulSoup(html, 'html.parser')
    name = ""
    # h1.name が AXEL の標準
    h1 = soup.find('h1', class_='name')
    if h1:
        name = h1.get_text(strip=True)
    elif soup.h1:
        name = soup.h1.get_text(strip=True)
    price = None
    m = re.search(r'¥\s*([\d,]+)', soup.get_text(' '))
    if m:
        try:
            price = int(m.group(1).replace(",", ""))
        except ValueError:
            pass
    specs = parse_spec_table(html)
    return {"name": name, "price": price, "specs": specs}


def scrape_to_jsonl(filter_url: str, dest_path: str, max_items: int = 60) -> int:
    """AXEL カテゴリ絞り URL から商品を取得して JSONL に追記保存。

    呼び出し側は **AS ONE/ナビス でメーカー絞り込み済の URL** を渡す前提。
    例: https://axel.as-1.co.jp/asone/s/G0000000/?maker=AS_ONE,NAVIS
    """
    list_html = fetch(filter_url)
    if list_html is None:
        return 0
    items = parse_product_list(list_html)[:max_items]
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    count = 0
    with open(dest_path, "a", encoding="utf-8") as f:
        for it in items:
            detail_html = fetch(it["url"])
            if detail_html is None:
                continue
            detail = parse_product_detail(detail_html)
            row = {**it, **detail, "category": "autoclave"}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count
