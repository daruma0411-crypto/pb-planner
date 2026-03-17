"""
アルプ オートクレーブ スクレイパー
公式サイト: https://alpco.co.jp/auto/
出力: workspace/data/alp_autoclave/products.jsonl

注意: アルプ公式サイトはスペック表がPDF/画像のためHTML内に構造化データが少ない。
メイン一覧ページから基本情報（容量レンジ・温度レンジ）を取得し、
各シリーズページから型番バリエーション・特徴を抽出する。
"""
import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scraper_base import (
    fetch, load_existing_ids, save_entry,
    make_id, now_iso, parse_price, DATA_ROOT, BeautifulSoup,
)

JSONL_PATH = os.path.join(DATA_ROOT, 'alp_autoclave', 'products.jsonl')
BASE_URL = 'https://alpco.co.jp'

# シリーズ定義（WebFetch + 公式ページから取得済み情報）
SERIES_DEFS = [
    {
        'slug': 'clg-dvp',
        'series': 'CLG-DVPシリーズ',
        'description': '真空脱気滅菌・乾燥機能付き、液晶ディスプレイ、16パターン登録可能',
        'capacity_range': '62L～117L',
        'temp_range': '100℃～140℃',
        'models': [
            {'model': 'CLG-DVP32S', 'capacity': '62L', 'inner_dim': 'φ320mm'},
            {'model': 'CLG-DVP32L', 'capacity': '80L', 'inner_dim': 'φ320mm'},
            {'model': 'CLG-DVP40M', 'capacity': '97L', 'inner_dim': 'φ400mm'},
            {'model': 'CLG-DVP40L', 'capacity': '117L', 'inner_dim': 'φ400mm'},
        ],
    },
    {
        'slug': 'clg',
        'series': 'CLGシリーズ',
        'description': '液晶ディスプレイ、15パターン登録可能、パルス脱気',
        'capacity_range': '62L～117L',
        'temp_range': '100℃～140℃',
        'models': [
            {'model': 'CLG-32S', 'capacity': '62L', 'inner_dim': 'φ320mm'},
            {'model': 'CLG-32L', 'capacity': '80L', 'inner_dim': 'φ320mm'},
            {'model': 'CLG-40M', 'capacity': '97L', 'inner_dim': 'φ400mm'},
            {'model': 'CLG-40L', 'capacity': '117L', 'inner_dim': 'φ400mm'},
        ],
    },
    {
        'slug': 'cls',
        'series': 'CLSシリーズ',
        'description': 'ワンタッチロック・インターロック付、温風乾燥付(DPモデル)',
        'capacity_range': '62L～117L',
        'temp_range': '100℃～140℃',
        'models': [
            {'model': 'CLS-32L', 'capacity': '80L', 'inner_dim': 'φ320mm'},
            {'model': 'CLS-40M', 'capacity': '97L', 'inner_dim': 'φ400mm'},
            {'model': 'CLS-40L', 'capacity': '117L', 'inner_dim': 'φ400mm'},
        ],
    },
    {
        'slug': 'tr',
        'series': 'TR-24Lシリーズ',
        'description': 'シングルモーション、低価格、床置型',
        'capacity_range': '22L',
        'temp_range': '105℃～127℃',
        'models': [
            {'model': 'TR-24L', 'capacity': '22L'},
        ],
    },
    {
        'slug': 'mcs',
        'series': 'MCSシリーズ',
        'description': '廃棄物滅菌に最適、シンプル設計',
        'capacity_range': '96L～118L',
        'temp_range': '100℃～127℃',
        'models': [
            {'model': 'MCS-40', 'capacity': '96L', 'inner_dim': 'φ400mm'},
            {'model': 'MCS-40L', 'capacity': '118L', 'inner_dim': 'φ400mm'},
        ],
    },
    {
        'slug': 'mcs-3032',
        'series': 'MCS3032シリーズ',
        'description': '高耐性菌滅菌処理対応、高温型',
        'capacity_range': '37L～50L',
        'temp_range': '100℃～150℃',
        'models': [
            {'model': 'MCS-3032S', 'capacity': '37L', 'inner_dim': 'φ300mm'},
            {'model': 'MCS-3032L', 'capacity': '50L', 'inner_dim': 'φ300mm'},
        ],
    },
    {
        'slug': 'mcy',
        'series': 'MCYシリーズ',
        'description': '大容量横型、ローラー付引き出しトレー',
        'capacity_range': '118L',
        'temp_range': '100℃～124℃',
        'models': [
            {'model': 'MCY-40L', 'capacity': '118L', 'inner_dim': 'φ400mm×830mm 横型'},
        ],
    },
    {
        'slug': 'pktr',
        'series': 'KTRシリーズ（新型）',
        'description': 'パーソナルクレーブ、新世代デジタル制御',
        'capacity_range': '12L～50L',
        'temp_range': '110℃～125℃',
        'models': [
            {'model': 'KTR-2322', 'capacity': '12L', 'inner_dim': 'φ230mm'},
            {'model': 'KTR-2346A', 'capacity': '22L', 'inner_dim': 'φ230mm'},
            {'model': 'KTR-3045A', 'capacity': '35L', 'inner_dim': 'φ300mm'},
            {'model': 'KTR-3065A', 'capacity': '50L', 'inner_dim': 'φ300mm'},
        ],
    },
    {
        'slug': 'kyr',
        'series': 'KYRシリーズ',
        'description': 'シンプルな横型モデル、デジタル制御',
        'capacity_range': '20L',
        'temp_range': '110℃～125℃',
        'models': [
            {'model': 'KYR-2346', 'capacity': '20L', 'inner_dim': 'φ230mm 横型',
             'price': '348,000円（税抜）'},
            {'model': 'KYR-2346D', 'capacity': '20L', 'inner_dim': 'φ230mm 横型',
             'price': '428,000円（税抜）', 'note': '乾燥機能付'},
        ],
    },
]


def scrape_series_description(slug: str) -> str:
    """シリーズページから追加の特徴テキストを取得"""
    url = f'{BASE_URL}/auto/{slug}/'
    html = fetch(url)
    if not html:
        return ''
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text(separator=' ')
    # 特徴的な文を抽出（最初の200文字）
    clean = re.sub(r'\s+', ' ', text).strip()
    # 製品名以降の説明を取得
    for keyword in ('シリーズ', 'オートクレーブ'):
        idx = clean.find(keyword)
        if idx > 0:
            snippet = clean[idx:idx+300]
            return snippet
    return ''


def main():
    print('=' * 60)
    print('アルプ オートクレーブ スクレイパー')
    print('=' * 60)

    existing_ids = load_existing_ids(JSONL_PATH)
    print(f'既存ID数: {len(existing_ids)}')

    added = 0
    skipped = 0
    all_products = []

    for series_def in SERIES_DEFS:
        slug = series_def['slug']
        series_name = series_def['series']
        print(f'\n--- {series_name} ---')

        # ページから追加情報取得
        extra_desc = scrape_series_description(slug)

        for m in series_def['models']:
            model = m['model']
            entry_id = make_id('alp', model)

            if entry_id in existing_ids:
                skipped += 1
                continue

            specs = {
                '有効容量': m.get('capacity', ''),
                '使用温度範囲': series_def['temp_range'],
            }
            if m.get('inner_dim'):
                specs['缶体内寸法'] = m['inner_dim']
            if m.get('note'):
                specs['備考'] = m['note']

            entry = {
                'id': entry_id,
                'name': f'高圧蒸気滅菌器 {model}',
                'model': model,
                'maker': 'アルプ',
                'category': 'autoclave',
                'usage': 'ラボ',
                'description': series_def['description'],
                'specs': specs,
                'source_url': f'{BASE_URL}/auto/{slug}/',
                'scraped_at': now_iso(),
            }
            if m.get('price'):
                entry['price'] = m['price']
                price_val = parse_price(m['price'])
                if price_val:
                    entry['price_numeric'] = price_val

            save_entry(JSONL_PATH, entry)
            existing_ids.add(entry_id)
            added += 1
            all_products.append(entry)
            print(f'  + {model} ({m.get("capacity", "?")}) {m.get("price", "")}')

    print(f'\n{"=" * 60}')
    print(f'完了: 追加={added} スキップ={skipped}')
    print(f'出力: {JSONL_PATH}')

    if all_products:
        print(f'\n追加された製品:')
        for p in all_products:
            caps = p.get('specs', {}).get('有効容量', '?')
            price = p.get('price', '価格不明')
            print(f'  {p["model"]}: {caps} / {price}')


if __name__ == '__main__':
    main()
