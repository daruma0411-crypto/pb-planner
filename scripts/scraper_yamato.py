"""
ヤマト科学 オートクレーブ スクレイパー
公式サイト: https://www.yamato-net.co.jp/
出力: workspace/data/yamato_autoclave/products.jsonl

テーブル構造:
  - Row 0: 全th（ヘッダー: 商品コード/型式/容積/内寸法/外寸法/電源/重さ/価格）
  - Row 1+: 全td（各モデルのデータ行）
"""
import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scraper_base import (
    fetch, load_existing_ids, save_entry,
    make_id, now_iso, parse_price, DATA_ROOT, BeautifulSoup,
)

BASE_URL = 'http://www.yamato-net.co.jp'
JSONL_PATH = os.path.join(DATA_ROOT, 'yamato_autoclave', 'products.jsonl')

# シリーズページ（リダイレクト後のURL）
SERIES_PAGES = [
    ('/product/category/science/sterilizer/autoclave/sn/', 'SNシリーズ 標準型'),
    ('/product/category/science/sterilizer/autoclave/sq/', 'SQシリーズ 大口径型'),
    ('/product/category/science/sterilizer/autoclave/st/', 'STシリーズ エコノミー'),
    ('/product/category/science/sterilizer/autoclave/hva-lb/', 'HVA-LBシリーズ 大容量'),
]


def scrape_series_page(url: str, series_desc: str) -> list[dict]:
    """シリーズページのテーブルをパースして製品リストを返す"""
    html = fetch(url)
    if not html:
        print(f'  [SKIP] 取得失敗: {url}')
        return []

    soup = BeautifulSoup(html, 'html.parser')
    products = []

    for table in soup.find_all('table'):
        rows = table.find_all('tr')
        if len(rows) < 2:
            continue

        # ヘッダー行（全th）を探す
        header_row = rows[0]
        headers_ths = header_row.find_all('th')
        if len(headers_ths) < 3:
            continue

        headers = [th.get_text(strip=True) for th in headers_ths]

        # 型式列のインデックスを特定
        model_idx = -1
        for i, h in enumerate(headers):
            if '型式' in h or '型番' in h:
                model_idx = i
                break
        if model_idx < 0:
            continue

        # データ行をパース
        for row in rows[1:]:
            tds = row.find_all('td')
            if len(tds) < len(headers):
                continue

            values = [td.get_text(strip=True) for td in tds]
            model = values[model_idx] if model_idx < len(values) else ''
            if not model:
                continue

            # スペックをheaderとvalueのペアで構成
            specs = {}
            price_text = None
            for i, (h, v) in enumerate(zip(headers, values)):
                if not v:
                    continue
                if '価格' in h:
                    price_text = v
                elif '型式' not in h and '商品コード' not in h:
                    specs[h] = v

            entry = {
                'id': make_id('yamato', model),
                'name': f'オートクレーブ {model}',
                'model': model,
                'maker': 'ヤマト科学',
                'category': 'autoclave',
                'usage': 'ラボ',
                'description': series_desc,
                'specs': specs,
                'source_url': url,
                'scraped_at': now_iso(),
            }
            if price_text:
                entry['price'] = price_text
                price_val = parse_price(price_text)
                if price_val:
                    entry['price_numeric'] = price_val
            products.append(entry)

    return products


def main():
    print('=' * 60)
    print('ヤマト科学 オートクレーブ スクレイパー')
    print('=' * 60)

    existing_ids = load_existing_ids(JSONL_PATH)
    print(f'既存ID数: {len(existing_ids)}')

    added = 0
    skipped = 0
    failed = 0
    all_products = []

    for path, desc in SERIES_PAGES:
        url = f'{BASE_URL}{path}'
        print(f'\n--- {desc} ({url}) ---')

        try:
            products = scrape_series_page(url, desc)
            print(f'  取得: {len(products)}件')

            for p in products:
                if p['id'] in existing_ids:
                    skipped += 1
                    continue
                save_entry(JSONL_PATH, p)
                existing_ids.add(p['id'])
                added += 1
                all_products.append(p)
                print(f'  + {p["model"]} ({p.get("price", "価格不明")})')

        except Exception as e:
            print(f'  [ERROR] {e}')
            import traceback; traceback.print_exc()
            failed += 1

    print(f'\n{"=" * 60}')
    print(f'完了: 追加={added} スキップ={skipped} 失敗={failed}')
    print(f'出力: {JSONL_PATH}')

    if all_products:
        print(f'\n追加された製品:')
        for p in all_products:
            price = p.get('price', '?')
            caps = p.get('specs', {}).get('缶体有効内容積', '?')
            print(f'  {p["model"]}: {caps} / {price}')


if __name__ == '__main__':
    main()
