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
# セッションストレージ（Redis / フォールバック: メモリ内）
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
        print(f"[SESSION] Redis connect failed: {_e}, falling back to memory",
              flush=True, file=sys.stderr)
        _redis_client = None
else:
    print("[SESSION] No REDIS_URL, using in-memory sessions",
          flush=True, file=sys.stderr)

_SESSIONS = {}


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
    }


def get_or_create_session(session_id):
    """セッション取得 or 新規作成"""
    if _redis_client:
        try:
            raw = _redis_client.get(f'pb:{session_id}')
            if raw:
                return json.loads(raw)
        except Exception:
            pass
    elif session_id in _SESSIONS:
        return _SESSIONS[session_id]
    return _new_session_dict()


def save_session(session_id, session):
    """セッション保存"""
    if _redis_client:
        try:
            _redis_client.setex(f'pb:{session_id}', _SESSION_TTL,
                                json.dumps(session, ensure_ascii=False))
            return
        except Exception:
            pass
    _SESSIONS[session_id] = session


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
]


# ================================================================
# システムプロンプト
# ================================================================

_PB_CONSULTANT_SYSTEM_PROMPT = """\
あなたはアズワンPB（プライベートブランド）企画の専門コンサルタントです。

## あなたの役割
仕入れ先の製品データを元に、PB化の企画を壁打ちしながらユーザーと一緒に進めます。

## 強み
1. **データドリブン**: search_productsで取得した実データのみを使用（ハルシネーション厳禁）
2. **構造化思考**: フレームワーク分析（3C/SWOT/ポジショニング/5Forces/価格帯マップ）で企画を深掘り
3. **実務直結**: PIMデータ・企画書・カタログまで一気通貫で生成支援

## 守るルール（厳守）
1. search_productsの結果に含まれる情報のみ使用すること。DBに無い情報は「データベースに登録がありません」と回答
2. PBカード項目の確定は必ず set_pb_field ツールを使用すること（口頭確認だけではNG）
3. ユーザーが値を決めたら即座にset_pb_fieldで確定すること
4. ベース製品が決まっていない段階でPBカードの項目を埋めようとしないこと
5. 1ターンに1つの質問のみ（複数質問を一度にしない）
6. 日本語で回答すること

## PB企画カードの7項目
- asone_part_no: アズワン品番（例: 0-1234-01）
- price: 販売価格（税抜）
- jan_code: JANコード（13桁）
- maker_part_no: メーカー型番（ベース製品の型番）
- quantity: 入数
- catchcopy: キャッチコピー（製品の訴求ポイント）
- spec_diff: 仕様差分（ベース製品との違い）

## 会話の進め方
1. まずユーザーの目的を聞く（どのメーカーの何をPB化したいか）
2. search_productsでベース候補を検索・提示
3. ベース製品が決まったら、PBカード7項目を順に確定
4. 必要に応じてフレームワーク分析を提案
5. 全項目確定後、アウトプット生成（Excel/Word/英訳/HTML）を提案

## 壁打ちの極意
- ユーザーが迷っていたら、データに基づいて選択肢を絞る
- 「この型番をベースにしましょうか？」と具体的に確認
- 価格設定は競合データや原価率の観点からアドバイス
- キャッチコピーは製品の差別化ポイントを強調する案を複数提示

## 製品紹介のルール（重要）
製品の特徴を聞かれたら、**スペック表の数値だけでなく、以下の順序で紹介すること**:
1. **設計思想・コンセプト** (design_concept): なぜこの製品が作られたか、ターゲットユーザー
2. **主要な製品特長** (features): 使いやすさ、独自技術、特許機能など
3. **運転コース** (operation_courses): 使い方のバリエーション
4. **安全機能** (safety): ユーザーを守る機能の概要
5. **オプション** (options): 拡張性・カスタマイズ性
6. **収納量・実用データ** (storage_capacity): 実際の使用イメージ
7. **スペック表** (specs): 数値データは最後にまとめて

製品データに features, design_concept, options 等のフィールドがある場合は必ず活用すること。
スペック表の羅列だけの回答は不可。ユーザーがPB企画の判断材料にできる「ストーリー」として紹介すること。
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
