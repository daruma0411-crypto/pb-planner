"""
オートクレーブ競合スクレイパー 共通ベース
各メーカースクレイパーからimportして使う
"""
import json
import os
import re
import sys
import time
import random
from datetime import datetime

import urllib3
import requests
from bs4 import BeautifulSoup

# Windows環境でのSSL証明書エラー回避
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

DATA_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         'workspace', 'data')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/120.0.0.0 Safari/537.36',
    'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
}


def fetch(url: str, retries: int = 3, delay_range=(0.5, 1.5),
          encoding: str = 'utf-8') -> str | None:
    """HTTPリクエスト with リトライ・指数バックオフ"""
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=20, verify=False)
            resp.encoding = encoding
            resp.raise_for_status()
            time.sleep(random.uniform(*delay_range))
            return resp.text
        except requests.exceptions.HTTPError as e:
            code = e.response.status_code if e.response else 0
            if code in (404, 410):
                print(f'  [SKIP] {url} → {code}')
                return None
            if code == 429:
                wait = int(e.response.headers.get('Retry-After', 2 ** (attempt + 2)))
                print(f'  [429] Rate limit → wait {wait}s')
                time.sleep(wait)
                continue
            wait = 2 ** attempt
            print(f'  [WARN] {url} attempt={attempt+1} status={code} → wait {wait}s')
            time.sleep(wait)
        except Exception as e:
            wait = 2 ** attempt
            print(f'  [WARN] {url} attempt={attempt+1} error={e} → wait {wait}s')
            time.sleep(wait)
    return None


def parse_spec_table(html: str, table_selector: str = 'table') -> dict:
    """HTMLからスペック表(th/td)をパースしてdictで返す"""
    soup = BeautifulSoup(html, 'html.parser')
    specs = {}
    for table in soup.select(table_selector):
        rows = table.find_all('tr')
        for row in rows:
            th = row.find('th')
            td = row.find('td')
            if th and td:
                key = th.get_text(strip=True)
                val = td.get_text(strip=True)
                if key and val and val not in ('-', '—', ''):
                    specs[key] = val
    return specs


def parse_comparison_table(html: str, table_selector: str = 'table') -> list[dict]:
    """横並び比較テーブル（1行目=ヘッダー列）をパースして製品リストで返す"""
    soup = BeautifulSoup(html, 'html.parser')
    results = []
    for table in soup.select(table_selector):
        rows = table.find_all('tr')
        if not rows:
            continue
        # ヘッダー行（製品名）
        header_cells = rows[0].find_all(['th', 'td'])
        num_products = len(header_cells) - 1  # 最初のセルはラベル
        if num_products <= 0:
            continue
        products = [{'_header': c.get_text(strip=True)} for c in header_cells[1:]]
        # データ行
        for row in rows[1:]:
            cells = row.find_all(['th', 'td'])
            if len(cells) < 2:
                continue
            key = cells[0].get_text(strip=True)
            for i, cell in enumerate(cells[1:]):
                if i < num_products and key:
                    val = cell.get_text(strip=True)
                    if val and val not in ('-', '—', ''):
                        products[i][key] = val
        results.extend(products)
    return results


def load_existing_ids(jsonl_path: str) -> set:
    """既存JSONLファイルからIDセットを読み込む"""
    ids = set()
    if os.path.exists(jsonl_path):
        with open(jsonl_path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        ids.add(json.loads(line).get('id', ''))
                    except Exception:
                        pass
    return ids


def save_entry(jsonl_path: str, entry: dict):
    """1件をJSONLファイルに追記"""
    os.makedirs(os.path.dirname(jsonl_path), exist_ok=True)
    with open(jsonl_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')


def make_id(maker_slug: str, model: str) -> str:
    """メーカースラグ + 型番からIDを生成"""
    safe_model = re.sub(r'[^a-zA-Z0-9-]', '-', model.lower()).strip('-')
    safe_model = re.sub(r'-+', '-', safe_model)
    return f'{maker_slug}-{safe_model}'


def now_iso() -> str:
    return datetime.now().strftime('%Y-%m-%dT%H:%M:%S')


def parse_price(text: str) -> int | None:
    """価格文字列から数値を抽出（円、税込/税抜は無視）"""
    if not text:
        return None
    # カンマ除去、数字抽出
    nums = re.findall(r'[\d,]+', text.replace('¥', '').replace('￥', ''))
    for n in nums:
        try:
            val = int(n.replace(',', ''))
            if val >= 10000:  # 1万円以上のみ
                return val
        except ValueError:
            pass
    return None
