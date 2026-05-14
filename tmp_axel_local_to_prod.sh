#!/bin/bash
# ローカルで AXEL を取得して本番に手動投入
PID=${1:?PID required}
BASE=${2:-https://web-production-1c92b.up.railway.app}
OUT=/c/Users/iwashita.AKGNET/pb-planner/tmp_axel_local.jsonl

cd /c/Users/iwashita.AKGNET/pb-planner

# ローカルで AXEL 取得
python -c "
import sys
sys.path.insert(0, '.')
from scripts.scraper_axel import scrape_to_jsonl
import os
os.makedirs('/tmp/axel', exist_ok=True)
n = scrape_to_jsonl('https://axel.as-1.co.jp/asone/s/G0000000/', '$OUT', max_items=20)
print(f'取得: {n} 件')
"

# 本番にアップロード
echo '===upload==='
curl -sSL --ssl-no-revoke -X POST -H "Content-Type: text/plain" --data-binary "@$OUT" "$BASE/api/projects/$PID/scraped/asone"
echo
