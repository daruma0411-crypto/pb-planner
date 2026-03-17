"""
PB企画支援チャットボット — Flask Webサーバー
=============================================
GET  /            → static/index.html
POST /api/chat    → PB企画チャット（Claude Sonnet + Function Calling）
GET  /api/health  → ヘルスチェック
GET  /api/download/<filename> → 生成ファイルダウンロード
"""
import glob as glob_module
import json
import os
import re
import time
import sys
import tempfile
import traceback

from dotenv import load_dotenv
from flask import (Flask, Response, abort, jsonify, request,
                   send_from_directory, send_file)

load_dotenv()

CLAUDE_API_KEY = (os.environ.get('ANTHROPIC_API_KEY')
                  or os.environ.get('CLAUDE_API_KEY')
                  or os.environ.get('API_KEY')
                  or '')

app = Flask(__name__, static_folder='static')

# workspace/data/ のルートパス
_WORKSPACE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'workspace')

# ダウンロード用一時ディレクトリ
_DOWNLOADS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'downloads')
os.makedirs(_DOWNLOADS_DIR, exist_ok=True)

# テンプレートディレクトリ
_TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')

# ================================================================
# セッションストレージ（ファイル永続化 / Redis / フォールバック: メモリ内）
# ================================================================
_SESSION_TTL = 3600  # 1時間

_redis_client = None
_REDIS_URL = os.environ.get('REDIS_URL', '')
if _REDIS_URL:
    try:
        import redis
        _redis_client = redis.from_url(_REDIS_URL, decode_responses=True)
        _redis_client.ping()
        print("[SESSION] Redis connected", flush=True, file=sys.stderr)
    except Exception as _e:
        print(f"[SESSION] Redis connect failed: {_e}, falling back to file",
              flush=True, file=sys.stderr)
        _redis_client = None
else:
    print("[SESSION] No REDIS_URL, using file-based sessions",
          flush=True, file=sys.stderr)

# ファイルベースセッション用ディレクトリ
_SESSION_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.sessions')
os.makedirs(_SESSION_DIR, exist_ok=True)

_SESSIONS = {}  # メモリキャッシュ（高速アクセス用）


# ================================================================
# セッション管理
# ================================================================

def _new_session_dict():
    """空のセッション辞書を返す"""
    return {
        'history': [],
        'pb_card': {
            'asone_part_no': None,
            'price': None,
            'jan_code': None,
            'maker_part_no': None,
            'quantity': None,
            'catchcopy': None,
            'spec_diff': None,
        },
        'base_product': None,
        'framework_results': {},
        'last_search_results': [],
        'confirmed_specs': [],  # 確定済み仕様諸元リスト [{no, name, value}, ...]
    }


def _session_filepath(session_id):
    """セッションIDからファイルパスを生成（安全なファイル名に変換）"""
    safe_id = re.sub(r'[^a-zA-Z0-9_-]', '_', session_id)[:100]
    return os.path.join(_SESSION_DIR, f'{safe_id}.json')


def get_or_create_session(session_id):
    """セッション取得 or 新規作成"""
    # 1. Redis
    if _redis_client:
        try:
            raw = _redis_client.get(f'pb:{session_id}')
            if raw:
                return json.loads(raw)
        except Exception:
            pass

    # 2. メモリキャッシュ
    if session_id in _SESSIONS:
        return _SESSIONS[session_id]

    # 3. ファイル（再デプロイ後の復元）
    fpath = _session_filepath(session_id)
    if os.path.exists(fpath):
        try:
            with open(fpath, 'r', encoding='utf-8') as f:
                session = json.loads(f.read())
            _SESSIONS[session_id] = session  # メモリキャッシュに戻す
            print(f"[SESSION] Restored from file: {session_id}", flush=True, file=sys.stderr)
            return session
        except Exception as e:
            print(f"[SESSION] File read error: {e}", flush=True, file=sys.stderr)

    return _new_session_dict()


def save_session(session_id, session):
    """セッション保存（Redis + ファイル + メモリ）"""
    # Redis
    if _redis_client:
        try:
            _redis_client.setex(f'pb:{session_id}', _SESSION_TTL,
                                json.dumps(session, ensure_ascii=False))
        except Exception:
            pass

    # メモリキャッシュ
    _SESSIONS[session_id] = session

    # ファイル永続化（再デプロイ対策）
    try:
        fpath = _session_filepath(session_id)
        with open(fpath, 'w', encoding='utf-8') as f:
            f.write(json.dumps(session, ensure_ascii=False))
    except Exception as e:
        print(f"[SESSION] File save error: {e}", flush=True, file=sys.stderr)

    # 古いセッションファイルの掃除（100件超で古い順に削除）
    try:
        files = sorted(
            [os.path.join(_SESSION_DIR, f) for f in os.listdir(_SESSION_DIR) if f.endswith('.json')],
            key=os.path.getmtime
        )
        while len(files) > 100:
            os.remove(files.pop(0))
    except Exception:
        pass


# ================================================================
# 製品データロード
# ================================================================

def _load_all_products():
    """workspace/data/*/products.jsonl から全製品を読み込む"""
    products = []
    jsonl_paths = glob_module.glob(
        os.path.join(_WORKSPACE_DIR, 'data', '*', 'products.jsonl')
    )
    for path in jsonl_paths:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        products.append(json.loads(line))
        except Exception:
            pass
    return products


def _search_products(query=None, category=None, maker=None, usage=None):
    """製品DB検索"""
    all_products = _load_all_products()
    results = []
    for p in all_products:
        # カテゴリフィルタ
        if category and p.get('category', '').lower() != category.lower():
            continue
        # メーカーフィルタ
        if maker and maker.lower() not in p.get('maker', '').lower():
            continue
        # 用途フィルタ
        if usage and usage.lower() not in (p.get('usage') or '').lower():
            continue
        # テキスト検索
        if query:
            q_lower = query.lower()
            searchable = ' '.join([
                p.get('name', ''),
                p.get('model', ''),
                p.get('maker', ''),
                p.get('category', ''),
                p.get('description', ''),
                json.dumps(p.get('specs', {}), ensure_ascii=False),
            ]).lower()
            if q_lower not in searchable:
                continue
        results.append(p)
    return results


# ================================================================
# Function Calling ツール定義
# ================================================================

FC_TOOLS = [
    {
        "name": "search_products",
        "description": "仕入れ先製品データベースを検索する。カテゴリ、メーカー、テキスト検索、用途で絞り込み可能。",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "検索キーワード（製品名、型番、スペックなど）"
                },
                "category": {
                    "type": "string",
                    "description": "製品カテゴリ（autoclave, accessory, consumable等）"
                },
                "maker": {
                    "type": "string",
                    "description": "メーカー名"
                },
                "usage": {
                    "type": "string",
                    "description": "用途（ラボ, メディカル, 調理等）"
                }
            }
        }
    },
    {
        "name": "set_pb_field",
        "description": "PB企画カードの項目を確定する。field_nameとvalueを指定。",
        "input_schema": {
            "type": "object",
            "properties": {
                "field_name": {
                    "type": "string",
                    "enum": ["asone_part_no", "price", "jan_code",
                             "maker_part_no", "quantity", "catchcopy", "spec_diff"],
                    "description": "確定する項目名"
                },
                "value": {
                    "type": "string",
                    "description": "確定する値"
                }
            },
            "required": ["field_name", "value"]
        }
    },
    {
        "name": "get_pb_card",
        "description": "現在のPB企画カードの状態を取得する。",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "analyze_framework",
        "description": "フレームワーク分析を実行する。3C分析、SWOT分析、ポジショニングマップ、5Forces分析、価格帯マップから選択。",
        "input_schema": {
            "type": "object",
            "properties": {
                "framework": {
                    "type": "string",
                    "enum": ["3c", "swot", "positioning", "5forces", "price_map"],
                    "description": "実行するフレームワーク"
                }
            },
            "required": ["framework"]
        }
    },
    {
        "name": "generate_pim_excel",
        "description": "PIMデータExcelファイルを生成する。PBカードの全項目が確定済みである必要がある。",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "generate_proposal_word",
        "description": "企画書Wordファイルを生成する。PBカードとフレームワーク分析結果を含む。",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "translate_to_english",
        "description": "PIMデータを英訳してExcelファイルを生成する。",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "generate_catalog_html",
        "description": "カタログHTMLファイルを生成する。ベース製品情報とPBカード情報を含む。",
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "save_spec_list",
        "description": "仕様諸元リストを保存する。連番つき仕様一覧をユーザーに提示した後、そのリストをセッションに保存する。企画書Word最終ページの仕様諸元表に使われる。",
        "input_schema": {
            "type": "object",
            "properties": {
                "specs": {
                    "type": "array",
                    "description": "仕様リスト。各要素は {no: 番号, name: 項目名, value: 値} の形式",
                    "items": {
                        "type": "object",
                        "properties": {
                            "no": {"type": "integer", "description": "連番"},
                            "name": {"type": "string", "description": "項目名"},
                            "value": {"type": "string", "description": "値"}
                        },
                        "required": ["no", "name", "value"]
                    }
                }
            },
            "required": ["specs"]
        }
    },
    {
        "name": "update_spec_item",
        "description": "仕様諸元リストの特定の番号の項目を更新する。「8番を300に変更」のような指示に対応。",
        "input_schema": {
            "type": "object",
            "properties": {
                "no": {
                    "type": "integer",
                    "description": "更新する項目の連番"
                },
                "value": {
                    "type": "string",
                    "description": "新しい値。項目名を変更する場合はname引数も指定。"
                },
                "name": {
                    "type": "string",
                    "description": "新しい項目名（省略時は項目名は変更しない）"
                }
            },
            "required": ["no", "value"]
        }
    },
]


# ================================================================
# システムプロンプト
# ================================================================

_PB_CONSULTANT_SYSTEM_PROMPT = """\
あなたはアズワンPB企画の専門コンサルタントです。仕入れ先の製品データを元に、PB化の壁打ちパートナーとしてユーザーと進めます。

## 最重要ルール：会話の文脈を読め

あなたの最大の仕事は「ユーザーの話を聞くこと」。以下を絶対に守れ：

1. **聞き返すな、動け。** ユーザーの意図が文脈から分かるなら即座にツールを呼べ。「確定しますか？」「よろしいですか？」は禁止。
2. **前の会話を忘れるな。** 会話で出た製品名・型番・価格・分析結果はすべて覚えていること。「先に製品を確定してください」と言い返すのは最悪の対応。
3. **一度に処理しろ。** ユーザーが「品番：200003003、JAN：9000021、入数：1」と言ったら、3つとも一度にset_pb_fieldで確定。1つだけ確定して残りを聞き返すのは禁止。
4. **既に確定した値を忘れるな。** PBカードに既に入っている値は触るな。新しく指示された値だけ追加・更新しろ。
5. **ユーザーの指示した書式に従え。** 「連番ふって」→ 1,2,3...の通し番号を全項目に振れ（カテゴリで途切れさせるな）。「表にして」→ テーブル形式。「一覧」→ 全項目を漏れなく。ユーザーが後から「8番を変更」と言えるように番号は必ず振ること。

## 具体的なNG/OK例

NG: 「3C分析を実行するには、まずベース製品を確定する必要があります」
OK: （会話で出ている型番でsearch_products→analyze_framework即実行）

NG: 「FLS-1000をベースにしますか？確定していただければ分析を実行します」
OK: （FLS-1000の話をしているのだからsearch_productsしてそのまま分析実行）

NG: 「価格を90万円で確定しますか？」
OK: （「90万円で」と言われたらset_pb_field即実行）

NG: 品番設定後に「残り4項目を決めましょう！」と言って既に設定済みの項目を未確定表示
OK: 既に確定済みの項目はそのまま維持し、新しく設定した項目だけ報告

NG: 「連番ふって」と言われてカテゴリ見出し+箇条書きで返す（番号なし）
OK: 1. ○○ / 2. △△ / 3. □□ ... と全項目に通し番号を振る。ユーザーが「8番を変更して」と言えるようにする

NG: ユーザーが「①と②に加えて別項目で後２つ」と言ったのに全部で6つ出した後、番号をリセットして1から振り直す
OK: 既に出した①②③④に続けて⑤⑥として追加。番号体系を維持する

## データルール
- search_productsの結果のみ使用（ハルシネーション厳禁）
- DBに無い情報は「データベースに登録がありません」
- PBカード値の確定は必ずset_pb_fieldツールを使用

## PB企画カードの7項目
- asone_part_no: アズワン品番
- price: 販売価格（税抜）
- jan_code: JANコード
- maker_part_no: メーカー型番
- quantity: 入数
- catchcopy: キャッチコピー
- spec_diff: 仕様差分

## ベース製品の扱い
- ユーザーが型番名を出した時点でsearch_productsで検索し、ベース製品として扱え
- 「FLS-1000の特徴を教えて」→ search_productsしてFLS-1000の情報で回答。これがベース製品。
- 以後「比較して」「3C分析して」→ そのベース製品で即実行。「確定しますか？」不要。
- maker_part_noは最初の検索時にset_pb_fieldで自動設定してよい

## 製品紹介のルール
製品の特徴を聞かれたら、以下の順で紹介：
1. **設計思想** (design_concept): 誰のために、なぜ作られたか
2. **製品特長** (features): 使いやすさ、独自技術、特許機能
3. **運転コース** (operation_courses): 使い方のバリエーション
4. **安全機能** (safety): 概要のみ
5. **オプション** (options): 拡張性
6. **収納量** (storage_capacity): 実用データ
7. **スペック表** (specs): 数値は最後

スペック表の羅列だけは不可。製品の「ストーリー」として語れ。

## 仕様諸元リスト（企画書最終ページ用）
- ユーザーが「仕様を連番で並べて」等と言ったら、全仕様に通し番号をつけて表示
- 表示した直後に **save_spec_list** ツールで同じリストをセッションに保存すること（ユーザーに確認不要）
- ユーザーが「8番を○○に変更」と言ったら **update_spec_item** で即更新
- 保存された仕様諸元リストは、企画書Word生成時に最終ページの「仕様諸元表」として挿入される
- 仕様諸元リストが未保存のまま企画書を生成すると、仕様諸元表は含まれない

## 壁打ちの進め方
- ユーザーが迷ったら、データで選択肢を絞る
- 価格設定は原価率・競合観点でアドバイス
- キャッチコピーは差別化ポイントから案を提示
- フレームワーク分析はいつでも実行可能（会話中に製品が特定されていれば）
"""


def _build_system_prompt(session):
    """セッション状態に応じてシステムプロンプトを動的構築"""
    parts = [_PB_CONSULTANT_SYSTEM_PROMPT]

    # PBカード状態
    pb = session.get('pb_card', {})
    filled = sum(1 for v in pb.values() if v is not None)
    total = len(pb)
    parts.append(f"\n## 現在のPBカード状態 ({filled}/{total}項目確定)")
    for k, v in pb.items():
        status = f"✅ {v}" if v else "⏳ 未確定"
        parts.append(f"- {k}: {status}")

    # ベース製品情報
    base = session.get('base_product')
    if base:
        parts.append(f"\n## ベース製品")
        parts.append(f"- 製品名: {base.get('name', '不明')}")
        parts.append(f"- メーカー: {base.get('maker', '不明')}")
        parts.append(f"- 型番: {base.get('model', '不明')}")
        if base.get('price'):
            parts.append(f"- 価格: {base.get('price')}")
        if base.get('description'):
            parts.append(f"- 概要: {base.get('description')}")
        if base.get('design_concept'):
            parts.append(f"- 設計思想: {base.get('design_concept')}")
        if base.get('features'):
            parts.append(f"- 製品特長: {json.dumps(base['features'], ensure_ascii=False)}")
        if base.get('operation_courses'):
            parts.append(f"- 運転コース: {json.dumps(base['operation_courses'], ensure_ascii=False)}")
        if base.get('options'):
            parts.append(f"- オプション: {json.dumps(base['options'], ensure_ascii=False)}")
        if base.get('storage_capacity'):
            parts.append(f"- 収納量: {json.dumps(base['storage_capacity'], ensure_ascii=False)}")
        if base.get('specs'):
            parts.append(f"- スペック: {json.dumps(base['specs'], ensure_ascii=False)}")

    # 分析済みフレームワーク
    fw = session.get('framework_results', {})
    if fw:
        parts.append(f"\n## 分析済みフレームワーク: {', '.join(fw.keys())}")

    return '\n'.join(parts)


# ================================================================
# ツールハンドラ
# ================================================================

def handle_search_products(args, session):
    """製品DB検索"""
    results = _search_products(
        query=args.get('query'),
        category=args.get('category'),
        maker=args.get('maker'),
        usage=args.get('usage'),
    )
    session['last_search_results'] = results[:20]

    if not results:
        return {"found": 0, "message": "該当する製品が見つかりませんでした。"}

    # 結果フォーマット
    items = []
    for p in results[:20]:
        item = {
            "id": p.get('id', ''),
            "name": p.get('name', ''),
            "model": p.get('model', ''),
            "maker": p.get('maker', ''),
            "category": p.get('category', ''),
            "price": p.get('price', ''),
            "usage": p.get('usage', ''),
        }
        if p.get('specs'):
            item['specs'] = p['specs']
        if p.get('description'):
            item['description'] = p['description']
        # リッチ製品データ（特長・オプション等）
        for rich_key in ('design_concept', 'features', 'operation_courses',
                         'safety', 'options', 'storage_capacity', 'maintenance',
                         'regulatory_note'):
            if p.get(rich_key):
                item[rich_key] = p[rich_key]
        items.append(item)

    return {"found": len(results), "showing": len(items), "products": items}


def handle_set_pb_field(args, session):
    """PBカード項目確定"""
    field = args.get('field_name')
    value = args.get('value')

    valid_fields = ['asone_part_no', 'price', 'jan_code',
                    'maker_part_no', 'quantity', 'catchcopy', 'spec_diff']
    if field not in valid_fields:
        return {"error": f"無効な項目名: {field}", "valid_fields": valid_fields}

    session['pb_card'][field] = value

    # maker_part_noが設定されたらベース製品を自動リンク
    if field == 'maker_part_no' and value:
        found = False
        # まずlast_search_resultsから探す
        for p in session.get('last_search_results', []):
            if p.get('model') == value:
                session['base_product'] = p
                found = True
                break
        # 見つからなければDBを直接検索
        if not found:
            db_results = _search_products(query=value)
            for p in db_results:
                if p.get('model') == value:
                    session['base_product'] = p
                    found = True
                    break
            if not found and db_results:
                session['base_product'] = db_results[0]

    filled = sum(1 for v in session['pb_card'].values() if v is not None)
    total = len(session['pb_card'])
    return {
        "success": True,
        "field": field,
        "value": value,
        "progress": f"{filled}/{total}",
        "all_filled": filled == total,
    }


def handle_get_pb_card(args, session):
    """PBカード状態取得"""
    pb = session.get('pb_card', {})
    filled = sum(1 for v in pb.values() if v is not None)
    total = len(pb)
    return {
        "pb_card": pb,
        "progress": f"{filled}/{total}",
        "all_filled": filled == total,
        "base_product": session.get('base_product'),
    }


def handle_analyze_framework(args, session):
    """フレームワーク分析"""
    framework = args.get('framework')
    valid = ['3c', 'swot', 'positioning', '5forces', 'price_map']
    if framework not in valid:
        return {"error": f"無効なフレームワーク: {framework}", "valid": valid}

    # キャッシュチェック
    cached = session.get('framework_results', {}).get(framework)
    if cached:
        return {"framework": framework, "result": cached, "cached": True}

    # 分析コンテキスト構築
    base = session.get('base_product')
    if not base:
        # PBカードのmaker_part_noからベース製品を自動復元
        maker_pn = session.get('pb_card', {}).get('maker_part_no')
        if maker_pn:
            db_results = _search_products(query=maker_pn)
            for p in db_results:
                if p.get('model') == maker_pn:
                    base = p
                    session['base_product'] = p
                    break
            if not base and db_results:
                base = db_results[0]
                session['base_product'] = base
    if not base:
        return {"error": "ベース製品が未選択です。先に製品を検索・選択してください。"}

    # 同カテゴリの製品を取得
    category_products = _search_products(category=base.get('category'))
    pb_card = session.get('pb_card', {})

    framework_names = {
        '3c': '3C分析（Customer/Competitor/Company）',
        'swot': 'SWOT分析（Strengths/Weaknesses/Opportunities/Threats）',
        'positioning': 'ポジショニングマップ分析',
        '5forces': '5Forces分析（業界構造分析）',
        'price_map': '価格帯マップ分析',
    }

    prompt = f"""以下の情報を元に「{framework_names[framework]}」を実施してください。

## ベース製品
{json.dumps(base, ensure_ascii=False, indent=2)}

## PBカード状態
{json.dumps(pb_card, ensure_ascii=False, indent=2)}

## 同カテゴリ製品（競合参考）
{json.dumps(category_products[:10], ensure_ascii=False, indent=2)}

分析結果を構造化して、PB企画に活かせる具体的なインサイトを含めてください。"""

    # Claude APIで分析実行
    import urllib.request
    analysis_result = _call_claude_simple(prompt)

    # キャッシュ保存
    if 'framework_results' not in session:
        session['framework_results'] = {}
    session['framework_results'][framework] = analysis_result

    return {"framework": framework, "result": analysis_result, "cached": False}


def handle_generate_pim_excel(args, session):
    """PIMデータExcel生成"""
    pb = session.get('pb_card', {})
    unfilled = [k for k, v in pb.items() if v is None]
    if unfilled:
        return {"error": f"未確定項目があります: {', '.join(unfilled)}"}

    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

        wb = Workbook()
        ws = wb.active
        ws.title = "PIMデータ"

        # ヘッダースタイル
        header_fill = PatternFill(start_color="E60012", end_color="E60012", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF", size=11)
        thin_border = Border(
            left=Side(style='thin'), right=Side(style='thin'),
            top=Side(style='thin'), bottom=Side(style='thin')
        )

        # ヘッダー
        headers = ["項目", "値"]
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=h)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center')
            cell.border = thin_border

        # データ
        field_labels = {
            'asone_part_no': 'アズワン品番',
            'price': '販売価格（税抜）',
            'jan_code': 'JANコード',
            'maker_part_no': 'メーカー型番',
            'quantity': '入数',
            'catchcopy': 'キャッチコピー',
            'spec_diff': '仕様差分',
        }

        for row_idx, (key, label) in enumerate(field_labels.items(), 2):
            ws.cell(row=row_idx, column=1, value=label).border = thin_border
            ws.cell(row=row_idx, column=2, value=pb.get(key, '')).border = thin_border

        # ベース製品情報
        base = session.get('base_product')
        if base:
            row = len(field_labels) + 3
            ws.cell(row=row, column=1, value="【ベース製品情報】").font = Font(bold=True)
            row += 1
            base_labels = {
                'name': '製品名', 'maker': 'メーカー', 'model': '型番',
                'category': 'カテゴリ', 'usage': '用途', 'price': '仕入れ先価格',
                'description': '概要',
            }
            for key, label in base_labels.items():
                if base.get(key):
                    ws.cell(row=row, column=1, value=label).border = thin_border
                    ws.cell(row=row, column=2, value=base[key]).border = thin_border
                    row += 1
            if base.get('specs'):
                for sk, sv in base['specs'].items():
                    ws.cell(row=row, column=1, value=sk).border = thin_border
                    ws.cell(row=row, column=2, value=str(sv)).border = thin_border
                    row += 1

        ws.column_dimensions['A'].width = 25
        ws.column_dimensions['B'].width = 50

        filename = f"PIM_{pb.get('maker_part_no', 'unknown')}_{int(time.time())}.xlsx"
        filepath = os.path.join(_DOWNLOADS_DIR, filename)
        wb.save(filepath)
        return {"success": True, "filename": filename, "download_url": f"/api/download/{filename}"}

    except ImportError:
        return {"error": "openpyxlがインストールされていません"}
    except Exception as e:
        return {"error": f"Excel生成エラー: {str(e)}"}


def handle_generate_proposal_word(args, session):
    """企画書Word生成"""
    pb = session.get('pb_card', {})
    base = session.get('base_product')

    # ベース製品の自動復元
    if not base:
        maker_pn = pb.get('maker_part_no')
        if maker_pn:
            db_results = _search_products(query=maker_pn)
            for p in db_results:
                if p.get('model') == maker_pn:
                    base = p
                    session['base_product'] = p
                    break
            if not base and db_results:
                base = db_results[0]
                session['base_product'] = base

    fw = session.get('framework_results', {})

    try:
        from docx import Document
        from docx.shared import Inches, Pt, RGBColor
        from docx.enum.text import WD_ALIGN_PARAGRAPH

        doc = Document()

        # タイトル
        title = doc.add_heading('PB企画書', level=0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER

        # 企画概要
        doc.add_heading('1. 企画概要', level=1)
        if base:
            doc.add_paragraph(f"ベース製品: {base.get('name', '')} ({base.get('maker', '')})")
            doc.add_paragraph(f"メーカー型番: {base.get('model', '')}")
            if base.get('price'):
                doc.add_paragraph(f"仕入れ先価格: {base.get('price')}")
            if base.get('usage'):
                doc.add_paragraph(f"用途: {base.get('usage')}")
            if base.get('description'):
                doc.add_paragraph(f"概要: {base.get('description')}")

        # PBカード
        doc.add_heading('2. PB製品仕様', level=1)
        field_labels = {
            'asone_part_no': 'アズワン品番',
            'price': '販売価格（税抜）',
            'jan_code': 'JANコード',
            'maker_part_no': 'メーカー型番',
            'quantity': '入数',
            'catchcopy': 'キャッチコピー',
            'spec_diff': '仕様差分',
        }
        table = doc.add_table(rows=1, cols=2)
        table.style = 'Table Grid'
        hdr_cells = table.rows[0].cells
        hdr_cells[0].text = '項目'
        hdr_cells[1].text = '値'
        for key, label in field_labels.items():
            row = table.add_row().cells
            row[0].text = label
            row[1].text = str(pb.get(key) or '—')

        # ベース製品スペック
        if base and base.get('specs'):
            doc.add_heading('3. ベース製品 詳細スペック', level=1)
            spec_table = doc.add_table(rows=1, cols=2)
            spec_table.style = 'Table Grid'
            spec_hdr = spec_table.rows[0].cells
            spec_hdr[0].text = '項目'
            spec_hdr[1].text = '値'
            for sk, sv in base['specs'].items():
                row = spec_table.add_row().cells
                row[0].text = str(sk)
                row[1].text = str(sv)

        # フレームワーク分析
        section_num = 4 if (base and base.get('specs')) else 3
        if fw:
            doc.add_heading(f'{section_num}. フレームワーク分析', level=1)
            fw_names = {
                '3c': '3C分析', 'swot': 'SWOT分析',
                'positioning': 'ポジショニング', '5forces': '5Forces',
                'price_map': '価格帯マップ'
            }
            for fw_key, fw_result in fw.items():
                doc.add_heading(fw_names.get(fw_key, fw_key), level=2)
                doc.add_paragraph(fw_result)
            section_num += 1

        # 仕様諸元表（最終ページ）
        confirmed_specs = session.get('confirmed_specs', [])
        if confirmed_specs:
            # 改ページ
            from docx.oxml.ns import qn
            from docx.oxml import OxmlElement
            p = doc.add_paragraph()
            run = p.add_run()
            br = OxmlElement('w:br')
            br.set(qn('w:type'), 'page')
            run._element.append(br)

            doc.add_heading(f'{section_num}. 仕様諸元表', level=1)
            doc.add_paragraph(
                f"製品名: {base.get('name', '')}　型番: {base.get('model', '')}"
            )

            spec_tbl = doc.add_table(rows=1, cols=3)
            spec_tbl.style = 'Table Grid'
            hdr = spec_tbl.rows[0].cells
            hdr[0].text = 'No.'
            hdr[1].text = '項目'
            hdr[2].text = '仕様'
            # ヘッダー太字
            for cell in hdr:
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        run.bold = True

            for item in confirmed_specs:
                row = spec_tbl.add_row().cells
                row[0].text = str(item.get('no', ''))
                row[1].text = str(item.get('name', ''))
                row[2].text = str(item.get('value', ''))

            # 列幅調整
            from docx.shared import Cm
            for row in spec_tbl.rows:
                row.cells[0].width = Cm(1.5)
                row.cells[1].width = Cm(6)
                row.cells[2].width = Cm(10)

        filename = f"企画書_{pb.get('maker_part_no', 'unknown')}_{int(time.time())}.docx"
        filepath = os.path.join(_DOWNLOADS_DIR, filename)
        doc.save(filepath)
        return {"success": True, "filename": filename, "download_url": f"/api/download/{filename}"}

    except ImportError:
        return {"error": "python-docxがインストールされていません"}
    except Exception as e:
        return {"error": f"Word生成エラー: {str(e)}"}


def handle_translate_to_english(args, session):
    """PIMデータ英訳Excel生成"""
    pb = session.get('pb_card', {})
    unfilled = [k for k, v in pb.items() if v is None]
    if unfilled:
        return {"error": f"未確定項目があります: {', '.join(unfilled)}"}

    base = session.get('base_product')

    # Claude APIで翻訳
    translate_prompt = f"""以下のPB製品情報を英訳してください。JSON形式で返してください。

PBカード:
{json.dumps(pb, ensure_ascii=False, indent=2)}

ベース製品:
{json.dumps(base, ensure_ascii=False, indent=2) if base else 'なし'}

出力形式（JSON）:
{{
  "asone_part_no": "...",
  "price": "...",
  "jan_code": "...",
  "maker_part_no": "...",
  "quantity": "...",
  "catchcopy": "...(英訳)",
  "spec_diff": "...(英訳)",
  "product_name": "...(英訳)",
  "description": "...(英訳)"
}}"""

    translated_text = _call_claude_simple(translate_prompt)

    # JSONパース試行
    try:
        # JSON部分を抽出
        json_match = re.search(r'\{[^{}]*\}', translated_text, re.DOTALL)
        if json_match:
            translated = json.loads(json_match.group())
        else:
            translated = {"raw_translation": translated_text}
    except json.JSONDecodeError:
        translated = {"raw_translation": translated_text}

    # Excel生成
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Border, Side, Alignment

        wb = Workbook()
        ws = wb.active
        ws.title = "PIM Data (English)"

        header_fill = PatternFill(start_color="E60012", end_color="E60012", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF", size=11)
        thin_border = Border(
            left=Side(style='thin'), right=Side(style='thin'),
            top=Side(style='thin'), bottom=Side(style='thin')
        )

        headers = ["Field", "Japanese", "English"]
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=h)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center')
            cell.border = thin_border

        field_labels = {
            'asone_part_no': 'AS ONE Part No.',
            'price': 'Price (excl. tax)',
            'jan_code': 'JAN Code',
            'maker_part_no': 'Maker Part No.',
            'quantity': 'Quantity',
            'catchcopy': 'Catchcopy',
            'spec_diff': 'Spec Difference',
        }

        for row_idx, (key, label) in enumerate(field_labels.items(), 2):
            ws.cell(row=row_idx, column=1, value=label).border = thin_border
            ws.cell(row=row_idx, column=2, value=str(pb.get(key, ''))).border = thin_border
            ws.cell(row=row_idx, column=3, value=str(translated.get(key, ''))).border = thin_border

        ws.column_dimensions['A'].width = 20
        ws.column_dimensions['B'].width = 40
        ws.column_dimensions['C'].width = 40

        filename = f"PIM_EN_{pb.get('maker_part_no', 'unknown')}_{int(time.time())}.xlsx"
        filepath = os.path.join(_DOWNLOADS_DIR, filename)
        wb.save(filepath)
        return {"success": True, "filename": filename, "download_url": f"/api/download/{filename}"}

    except Exception as e:
        return {"error": f"英訳Excel生成エラー: {str(e)}"}


def handle_generate_catalog_html(args, session):
    """カタログHTML生成"""
    pb = session.get('pb_card', {})
    base = session.get('base_product')

    # ベース製品の自動復元
    if not base:
        maker_pn = pb.get('maker_part_no')
        if maker_pn:
            db_results = _search_products(query=maker_pn)
            for p in db_results:
                if p.get('model') == maker_pn:
                    base = p
                    session['base_product'] = p
                    break
            if not base and db_results:
                base = db_results[0]
                session['base_product'] = base
    if not base:
        return {"error": "ベース製品が未選択です"}

    specs_html = ""
    if base.get('specs'):
        specs_rows = ""
        for k, v in base['specs'].items():
            specs_rows += f"<tr><td>{k}</td><td>{v}</td></tr>\n"
        specs_html = f"""
        <h2>仕様</h2>
        <table class="spec-table">
            <thead><tr><th>項目</th><th>値</th></tr></thead>
            <tbody>{specs_rows}</tbody>
        </table>"""

    diff_section = ""
    if pb.get('spec_diff'):
        diff_section = f"""
        <div class="diff-section">
            <h3>PB仕様差分</h3>
            <p>{pb['spec_diff']}</p>
        </div>"""

    html_content = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{base.get('name', 'PB製品')} - カタログ</title>
<style>
body {{ font-family: 'Helvetica Neue', Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; color: #333; }}
h1 {{ color: #E60012; border-bottom: 3px solid #E60012; padding-bottom: 10px; }}
h2 {{ color: #E60012; margin-top: 30px; }}
.product-info {{ background: #F5F5F5; padding: 20px; border-radius: 8px; margin: 20px 0; }}
.product-info p {{ margin: 8px 0; }}
.spec-table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
.spec-table th, .spec-table td {{ border: 1px solid #E0E0E0; padding: 10px; text-align: left; }}
.spec-table th {{ background: #E60012; color: white; }}
.spec-table tr:nth-child(even) {{ background: #F9F9F9; }}
.catchcopy {{ font-size: 1.3em; color: #E60012; font-weight: bold; margin: 20px 0; padding: 15px; border-left: 4px solid #E60012; background: #FFF5F5; }}
.diff-section {{ background: #FFF8E1; padding: 15px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #FFA000; }}
.pb-badge {{ display: inline-block; background: #E60012; color: white; padding: 4px 12px; border-radius: 4px; font-size: 12px; font-weight: bold; }}
.footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #E0E0E0; color: #666; font-size: 12px; }}
</style>
</head>
<body>
<h1><span class="pb-badge">PB</span> {base.get('name', '')}</h1>

{f'<div class="catchcopy">{pb["catchcopy"]}</div>' if pb.get('catchcopy') else ''}

<div class="product-info">
    <p><strong>アズワン品番:</strong> {pb.get('asone_part_no', '—')}</p>
    <p><strong>販売価格:</strong> {pb.get('price', '—')}</p>
    <p><strong>JANコード:</strong> {pb.get('jan_code', '—')}</p>
    <p><strong>メーカー型番:</strong> {pb.get('maker_part_no', '—')}</p>
    <p><strong>入数:</strong> {pb.get('quantity', '—')}</p>
    <p><strong>メーカー:</strong> {base.get('maker', '—')}</p>
    <p><strong>用途:</strong> {base.get('usage', '—')}</p>
</div>

{diff_section}
{specs_html}

<div class="footer">
    <p>Generated by PB Planner | AS ONE Corporation</p>
</div>
</body>
</html>"""

    filename = f"catalog_{pb.get('maker_part_no', 'unknown')}_{int(time.time())}.html"
    filepath = os.path.join(_DOWNLOADS_DIR, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(html_content)

    return {"success": True, "filename": filename, "download_url": f"/api/download/{filename}"}


def handle_save_spec_list(args, session):
    """仕様諸元リストを保存"""
    specs = args.get('specs', [])
    if not specs:
        return {"error": "仕様リストが空です"}

    # 連番を正規化して保存
    confirmed = []
    for i, item in enumerate(specs):
        confirmed.append({
            "no": item.get('no', i + 1),
            "name": str(item.get('name', '')),
            "value": str(item.get('value', '')),
        })
    session['confirmed_specs'] = confirmed
    return {
        "success": True,
        "count": len(confirmed),
        "message": f"仕様諸元リスト {len(confirmed)}項目を保存しました。企画書Wordの最終ページに仕様諸元表として挿入されます。"
    }


def handle_update_spec_item(args, session):
    """仕様諸元リストの特定番号の項目を更新"""
    no = args.get('no')
    new_value = args.get('value')
    new_name = args.get('name')

    specs = session.get('confirmed_specs', [])
    if not specs:
        return {"error": "仕様諸元リストが未保存です。先にsave_spec_listで保存してください。"}

    # 番号で検索
    found = False
    for item in specs:
        if item['no'] == no:
            item['value'] = new_value
            if new_name:
                item['name'] = new_name
            found = True
            break

    if not found:
        return {"error": f"番号 {no} の項目が見つかりません（範囲: 1〜{len(specs)}）"}

    session['confirmed_specs'] = specs
    return {
        "success": True,
        "updated": {"no": no, "name": new_name or "(変更なし)", "value": new_value},
        "message": f"{no}番の値を「{new_value}」に更新しました。"
    }


# ================================================================
# Claude API 呼び出し
# ================================================================

def _call_claude_simple(prompt, max_tokens=2000):
    """シンプルなClaude API呼び出し（ツールなし）"""
    import urllib.request

    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }

    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        'https://api.anthropic.com/v1/messages',
        data=data,
        headers={
            'Content-Type': 'application/json',
            'x-api-key': CLAUDE_API_KEY,
            'anthropic-version': '2023-06-01',
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            for block in result.get('content', []):
                if block.get('type') == 'text':
                    return block['text']
            return ''
    except Exception as e:
        return f"[API Error: {str(e)}]"


def _call_claude_with_tools(messages, system_prompt, session):
    """Claude API呼び出し（Function Calling付き）。download_urlを含む結果はリストで返す。"""
    import urllib.request

    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 4096,
        "system": system_prompt,
        "messages": messages,
        "tools": FC_TOOLS,
    }

    all_text_parts = []
    download_urls = []

    max_iterations = 10
    for iteration in range(max_iterations):
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            'https://api.anthropic.com/v1/messages',
            data=data,
            headers={
                'Content-Type': 'application/json',
                'x-api-key': CLAUDE_API_KEY,
                'anthropic-version': '2023-06-01',
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            return f"API呼び出しエラー: {str(e)}", download_urls

        # レスポンス解析
        text_parts = []
        tool_calls = []

        for block in result.get('content', []):
            if block.get('type') == 'text':
                text_parts.append(block['text'])
            elif block.get('type') == 'tool_use':
                tool_calls.append(block)

        # ツール呼び出しがなければ完了
        if not tool_calls:
            all_text_parts.extend(text_parts)
            return '\n'.join(all_text_parts), download_urls

        # 中間テキストも保持
        all_text_parts.extend(text_parts)

        # ツール実行
        tool_use_blocks = result.get('content', [])
        messages.append({"role": "assistant", "content": tool_use_blocks})

        tool_results = []
        for tc in tool_calls:
            tool_name = tc['name']
            tool_input = tc.get('input', {})
            tool_id = tc['id']

            handler = _TOOL_HANDLERS.get(tool_name)
            if handler:
                try:
                    result_data = handler(tool_input, session)
                except Exception as e:
                    result_data = {"error": str(e)}
            else:
                result_data = {"error": f"Unknown tool: {tool_name}"}

            # download_url を収集
            if isinstance(result_data, dict) and result_data.get('download_url'):
                download_urls.append({
                    "tool": tool_name,
                    "filename": result_data.get('filename', ''),
                    "download_url": result_data['download_url'],
                })

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": json.dumps(result_data, ensure_ascii=False),
            })

        messages.append({"role": "user", "content": tool_results})
        payload["messages"] = messages

    return "最大反復回数に達しました。" + '\n'.join(all_text_parts), download_urls


# ツールハンドラマッピング
_TOOL_HANDLERS = {
    'search_products': handle_search_products,
    'set_pb_field': handle_set_pb_field,
    'get_pb_card': handle_get_pb_card,
    'analyze_framework': handle_analyze_framework,
    'generate_pim_excel': handle_generate_pim_excel,
    'generate_proposal_word': handle_generate_proposal_word,
    'translate_to_english': handle_translate_to_english,
    'generate_catalog_html': handle_generate_catalog_html,
    'save_spec_list': handle_save_spec_list,
    'update_spec_item': handle_update_spec_item,
}


# ================================================================
# ルート定義
# ================================================================

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


@app.route('/api/health')
def health():
    return jsonify({
        "status": "ok",
        "service": "pb-planner",
        "api_key_set": bool(CLAUDE_API_KEY),
        "api_key_prefix": CLAUDE_API_KEY[:10] + '...' if CLAUDE_API_KEY else 'NOT SET',
    })


@app.route('/api/chat', methods=['POST'])
def chat():
    """PB企画チャットエンドポイント"""
    body = request.get_json(silent=True) or {}
    user_msg = (body.get('message') or '').strip()
    session_id = body.get('session_id') or f'web_{int(time.time())}_{os.urandom(4).hex()}'

    if not user_msg:
        return jsonify({"error": "メッセージが空です"}), 400

    if not CLAUDE_API_KEY:
        return jsonify({"error": "APIキーが設定されていません"}), 500

    session = get_or_create_session(session_id)

    # base_product自動復元（ワーカー切替・セッション消失対策）
    if not session.get('base_product'):
        maker_pn = session.get('pb_card', {}).get('maker_part_no')
        if maker_pn:
            db_results = _search_products(query=maker_pn)
            for p in db_results:
                if p.get('model') == maker_pn:
                    session['base_product'] = p
                    break
            if not session.get('base_product') and db_results:
                session['base_product'] = db_results[0]

    # 会話履歴にユーザーメッセージ追加
    session['history'].append({"role": "user", "content": user_msg})

    # 履歴を最新20ターンに制限
    if len(session['history']) > 40:
        session['history'] = session['history'][-40:]

    # システムプロンプト構築
    system_prompt = _build_system_prompt(session)

    # Claude API呼び出し
    reply_text, download_urls = _call_claude_with_tools(
        list(session['history']),  # コピーを渡す
        system_prompt,
        session,
    )

    # AIの返答を履歴に追加
    session['history'].append({"role": "assistant", "content": reply_text})

    # セッション保存
    save_session(session_id, session)

    # レスポンス構築
    response = {
        "reply": reply_text,
        "session_id": session_id,
        "pb_card": session.get('pb_card', {}),
        "base_product": session.get('base_product'),
        "framework_results": list(session.get('framework_results', {}).keys()),
        "download_urls": download_urls,
        "confirmed_specs_count": len(session.get('confirmed_specs', [])),
    }

    return jsonify(response)


@app.route('/api/reset', methods=['POST'])
def api_reset():
    """セッションリセット"""
    body = request.get_json(silent=True) or {}
    session_id = body.get('session_id', '')
    if session_id:
        if _redis_client:
            try:
                _redis_client.delete(f'pb:{session_id}')
            except Exception:
                pass
        elif session_id in _SESSIONS:
            del _SESSIONS[session_id]
    return jsonify({"success": True})


@app.route('/api/download/<filename>')
def download_file(filename):
    """生成ファイルダウンロード"""
    # パストラバーサル防止
    safe_name = os.path.basename(filename)
    filepath = os.path.join(_DOWNLOADS_DIR, safe_name)
    if not os.path.exists(filepath):
        abort(404)
    return send_file(filepath, as_attachment=True, download_name=safe_name)


@app.route('/<path:filename>')
def static_files(filename):
    """静的ファイル配信"""
    return send_from_directory('static', filename)


# ================================================================
# エントリポイント
# ================================================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
