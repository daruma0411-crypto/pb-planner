"""
ヒラヤマ製作所 オートクレーブ スクレイパー
公式サイト: https://www.hirayama-hmc.co.jp/
出力: workspace/data/hirayama_autoclave/products.jsonl

テーブル構造:
  - ヘッダー部（型式・容量等）: 全th（th[0]=ラベル, th[1:]=各モデル値）
  - データ部（スペック）: 全td（td[0]=ラベル, td[1:]=各モデル値 or 共通値）
  - 価格行: td[0]='価格', td[1:]=各モデルの価格
"""
import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scraper_base import (
    fetch, load_existing_ids, save_entry,
    make_id, now_iso, parse_price, DATA_ROOT, BeautifulSoup,
)

BASE_URL = 'https://www.hirayama-hmc.co.jp'
JSONL_PATH = os.path.join(DATA_ROOT, 'hirayama_autoclave', 'products.jsonl')

SERIES_PAGES = [
    ('hv2series.html', 'ラボ', 'HV-IIシリーズ ベーシックモデル'),
    ('hvn2series.html', 'ラボ', 'HVN-IIシリーズ 消臭機能付'),
    ('hvseries.html', 'ラボ', 'HV-35LB'),
    ('hveseries.html', 'ラボ', 'HVEシリーズ エコノミー'),
    ('hvaseries.html', 'ラボ', 'HVAシリーズ エコノミー強制冷却'),
    ('hvpseries.html', 'ラボ', 'HVPシリーズ'),
    ('hgseries-1.html', 'ラボ', 'HG-IIシリーズ フタ自動開閉'),
    ('hgseries-2.html', 'ラボ', 'HGシリーズ 大容量'),
    ('hgdseries.html', 'ラボ', 'HGDシリーズ'),
    ('hlm-elb.html', 'ラボ', 'HLM-36ELB'),
    ('haseries.html', 'ラボ', 'HAシリーズ'),
    ('hb.html', 'ラボ', 'HBシリーズ'),
    ('hfseries.html', 'メディカル', 'HFシリーズ 卓上小型'),
    ('hv2series-med.html', 'メディカル', 'HV-IIシリーズ 医療機器'),
    ('hvn2series-med.html', 'メディカル', 'HVN-IIシリーズ 医療機器'),
    ('hgseries-1-med.html', 'メディカル', 'HG-IIシリーズ 医療機器'),
    ('hvpseries-med.html', 'メディカル', 'HVPシリーズ 医療機器'),
    ('sgseries-med.html', 'メディカル', 'SGシリーズ 医療機器'),
]

# 全角スペース等を正規化してキーワードマッチ
def _normalize(text: str) -> str:
    return re.sub(r'[\s\u3000]+', '', text)


def _find_spec_table(soup: BeautifulSoup):
    """スペック比較テーブルを特定する（型式行を含むテーブル）"""
    for table in soup.find_all('table'):
        rows = table.find_all('tr')
        if len(rows) < 5:
            continue
        for row in rows:
            ths = row.find_all('th')
            if len(ths) >= 2:
                label = _normalize(ths[0].get_text(strip=True))
                if '型式' in label or '型番' in label:
                    return table
    return None


def scrape_series_page(url: str, usage: str, series_desc: str) -> list[dict]:
    """シリーズページからスペック比較テーブルをパースして製品リストを返す"""
    html = fetch(url)
    if not html:
        print(f'  [SKIP] 取得失敗: {url}')
        return []

    soup = BeautifulSoup(html, 'html.parser')
    table = _find_spec_table(soup)
    if not table:
        print(f'  [SKIP] スペックテーブル未検出: {url}')
        return []

    rows = table.find_all('tr')
    model_names = []
    num_models = 0
    model_specs = []
    model_prices = []

    for row in rows:
        ths = row.find_all('th')
        tds = row.find_all('td')

        # th行（ヘッダー部: 型式、容量等）
        if len(ths) >= 2:
            label = _normalize(ths[0].get_text(strip=True))
            vals = [th.get_text(strip=True) for th in ths[1:]]

            if '型式' in label or '型番' in label:
                model_names = vals
                num_models = len(vals)
                model_specs = [{} for _ in range(num_models)]
                model_prices = [None] * num_models
            elif num_models > 0 and '価格' in label:
                for i, v in enumerate(vals):
                    if i < num_models and v:
                        model_prices[i] = v
            elif num_models > 0:
                key = ths[0].get_text(strip=True).replace('\u3000', ' ').strip()
                for i, v in enumerate(vals):
                    if i < num_models and v and v not in ('-', '—'):
                        model_specs[i][key] = v

        # td行（データ部: スペック値）
        elif len(tds) >= 2 and num_models > 0:
            label_text = tds[0].get_text(strip=True).replace('\u3000', ' ').strip()
            if not label_text:
                continue
            vals = [td.get_text(strip=True) for td in tds[1:]]

            if '価格' in _normalize(label_text):
                for i, v in enumerate(vals):
                    if i < num_models and v:
                        model_prices[i] = v
                # 共通価格（1値のみ）→ 全モデルに適用しない（型番別に違うため）
            else:
                if len(vals) == 1:
                    # 共通値: 全モデルに適用
                    for i in range(num_models):
                        if vals[0] and vals[0] not in ('-', '—'):
                            model_specs[i][label_text] = vals[0]
                else:
                    for i, v in enumerate(vals):
                        if i < num_models and v and v not in ('-', '—'):
                            model_specs[i][label_text] = v

    # エントリ生成
    products = []
    for i, model in enumerate(model_names):
        if not model or model in ('-', '—'):
            continue
        entry = {
            'id': make_id('hirayama', model),
            'name': f'高圧蒸気滅菌器 {model}',
            'model': model,
            'maker': 'ヒラヤマ',
            'category': 'autoclave',
            'usage': usage,
            'description': series_desc,
            'specs': model_specs[i] if i < len(model_specs) else {},
            'source_url': url,
            'scraped_at': now_iso(),
        }
        if i < len(model_prices) and model_prices[i]:
            entry['price'] = model_prices[i]
            price_val = parse_price(model_prices[i])
            if price_val:
                entry['price_numeric'] = price_val
        products.append(entry)

    return products


def main():
    print('=' * 60)
    print('ヒラヤマ製作所 オートクレーブ スクレイパー')
    print('=' * 60)

    existing_ids = load_existing_ids(JSONL_PATH)
    print(f'既存ID数: {len(existing_ids)}')

    added = 0
    skipped = 0
    failed = 0
    all_products = []

    for path, usage, desc in SERIES_PAGES:
        url = f'{BASE_URL}/{path}'
        print(f'\n--- {desc} ({url}) ---')

        try:
            products = scrape_series_page(url, usage, desc)
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
            caps = p.get('specs', {}).get('有効容量', p.get('specs', {}).get('缶体容量', '?'))
            print(f'  {p["model"]}: {caps} / {price} / {p["usage"]}')


if __name__ == '__main__':
    main()
