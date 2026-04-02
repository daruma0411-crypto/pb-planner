"""ヤマト科学・アルプのオートクレーブDB名寄せ＋スペック拡充"""
import json, os, sys

sys.stdout.reconfigure(encoding='utf-8')

# === ヤマト科学 ===
YAMATO_PATH = os.path.join(os.path.dirname(__file__), '..', 'workspace', 'data', 'yamato_autoclave', 'products.jsonl')

# 既存データを読み込み
yamato_products = []
with open(YAMATO_PATH, 'r', encoding='utf-8') as fp:
    for line in fp:
        if line.strip():
            yamato_products.append(json.loads(line.strip()))

# スペック名寄せマッピング（ヤマト科学特有の表記→統一表記）
YAMATO_RENAME = {
    '缶体有効内容積': '缶体容量',
    '有効（総）内容積': '缶体容量',
    '内寸法（径×高さ）': '缶体内寸法',
    '内寸法（径×奥行）': '缶体内寸法',
    '外寸法（幅×奥行×高さ）': '本体寸法',
    '備考（寸法）': '寸法備考',
    '電源容量': '必要な電源',
    '重さ': '本体質量',
    '滅菌温度範囲': '使用温度範囲（滅菌）',
}

# 型番→シリーズ共通情報
YAMATO_SERIES = {
    'SN': {
        'description_base': 'ヤマト科学SNシリーズ。ラボ向けスタンダードオートクレーブ。',
        'extra_specs': {
            '使用温度範囲（滅菌）': '105〜126℃',
            '最高使用圧力': '0.157MPa',
            '缶体材質': 'SUS304',
            '圧力容器の種類': '小型圧力容器',
            'コース数': '3コース（滅菌・溶解・保温）',
            'ドアタイプ': '上蓋式（ハンドル開閉）',
            '安全装置': '安全弁、空焚き防止、過温防止、過圧防止',
        },
    },
    'SQ': {
        'description_base': 'ヤマト科学SQシリーズ。前面開き扉タイプの高性能オートクレーブ。',
        'extra_specs': {
            '使用温度範囲（滅菌）': '105〜126℃',
            '最高使用圧力': '0.157MPa',
            '缶体材質': 'SUS304',
            '圧力容器の種類': '小型圧力容器',
            'コース数': '3コース（滅菌・溶解・保温）',
            'ドアタイプ': '前面扉式',
            '安全装置': '安全弁、空焚き防止、過温防止、過圧防止、ドアインターロック',
        },
    },
    'ST': {
        'description_base': 'ヤマト科学STシリーズ。エコノミータイプのオートクレーブ。',
        'extra_specs': {
            '使用温度範囲（滅菌）': '121℃（固定）',
            '最高使用圧力': '0.118MPa',
            '缶体材質': 'SUS304',
            '圧力容器の種類': '簡易圧力容器',
            'コース数': '1コース（滅菌）',
            'ドアタイプ': '上蓋式（ハンドル開閉）',
            '安全装置': '安全弁、空焚き防止',
        },
    },
    'HVA': {
        'description_base': 'ヤマト科学HVA-LBシリーズ。高性能オートクレーブ。前面扉・大容量。',
        'extra_specs': {
            '缶体材質': 'SUS304',
            '圧力容器の種類': '小型圧力容器',
            'ドアタイプ': '前面扉式（横開き）',
            '安全装置': '安全弁、空焚き防止、過温防止、過圧防止、ドアインターロック、センサー故障検知',
            'コース数': '5コース以上',
        },
    },
}

for p in yamato_products:
    # 名寄せ
    new_specs = {}
    for k, v in p.get('specs', {}).items():
        new_key = YAMATO_RENAME.get(k, k)
        new_specs[new_key] = v

    # シリーズ共通情報追加
    model = p.get('model', '')
    series_key = None
    for sk in YAMATO_SERIES:
        if model.startswith(sk):
            series_key = sk
            break

    if series_key:
        info = YAMATO_SERIES[series_key]
        if not p.get('description') or len(p['description']) < 20:
            p['description'] = info['description_base']
        for ek, ev in info['extra_specs'].items():
            if ek not in new_specs:
                new_specs[ek] = ev

    p['specs'] = new_specs

# 書き戻し
with open(YAMATO_PATH, 'w', encoding='utf-8') as fp:
    for p in yamato_products:
        fp.write(json.dumps(p, ensure_ascii=False) + '\n')

print(f"ヤマト科学: {len(yamato_products)}製品更新")
for p in yamato_products:
    print(f"  {p['model']}: {len(p.get('specs',{}))}項目")

# === アルプ ===
ALP_PATH = os.path.join(os.path.dirname(__file__), '..', 'workspace', 'data', 'alp_autoclave', 'products.jsonl')

alp_products = []
with open(ALP_PATH, 'r', encoding='utf-8') as fp:
    for line in fp:
        if line.strip():
            alp_products.append(json.loads(line.strip()))

# アルプ名寄せ
ALP_RENAME = {
    '有効容量': '缶体容量',
    '使用温度範囲': '使用温度範囲（滅菌）',
    '缶体内寸法': '缶体内寸法',
}

ALP_SERIES = {
    'CLG-DVP': {
        'description_base': 'アルプCLG-DVPシリーズ。真空脱気機能付き高性能オートクレーブ。',
        'extra_specs': {
            '最高使用圧力': '0.22MPa',
            '缶体材質': 'SUS316L',
            '圧力容器の種類': '小型圧力容器',
            'ドアタイプ': '前面扉式（横開き）',
            '安全装置': '安全弁、空焚き防止、過温防止、過圧防止、ドアインターロック',
            '真空脱気': 'あり（DVP）',
        },
    },
    'CLG': {
        'description_base': 'アルプCLGシリーズ。汎用高圧蒸気滅菌器。',
        'extra_specs': {
            '最高使用圧力': '0.22MPa',
            '缶体材質': 'SUS316L',
            '圧力容器の種類': '小型圧力容器',
            'ドアタイプ': '前面扉式（横開き）',
            '安全装置': '安全弁、空焚き防止、過温防止、過圧防止、ドアインターロック',
        },
    },
    'CLS': {
        'description_base': 'アルプCLSシリーズ。スタンダード高圧蒸気滅菌器。',
        'extra_specs': {
            '最高使用圧力': '0.22MPa',
            '缶体材質': 'SUS316L',
            '圧力容器の種類': '小型圧力容器',
            'ドアタイプ': '前面扉式（横開き）',
            '安全装置': '安全弁、空焚き防止、過温防止、ドアインターロック',
        },
    },
    'TR': {
        'description_base': 'アルプTRシリーズ。卓上型小型オートクレーブ。',
        'extra_specs': {
            '最高使用圧力': '0.157MPa',
            '缶体材質': 'SUS304',
            '圧力容器の種類': '簡易圧力容器',
            'ドアタイプ': '上蓋式',
            '安全装置': '安全弁、空焚き防止',
        },
    },
    'MCS': {
        'description_base': 'アルプMCSシリーズ。メディカル向け小型蒸気滅菌器。',
        'extra_specs': {
            '最高使用圧力': '0.22MPa',
            '缶体材質': 'SUS304',
            '圧力容器の種類': '小型圧力容器',
            'ドアタイプ': '前面扉式',
            '安全装置': '安全弁、空焚き防止、過温防止、ドアインターロック',
        },
    },
    'MCY': {
        'description_base': 'アルプMCYシリーズ。メディカル向けコンパクト滅菌器。',
        'extra_specs': {
            '最高使用圧力': '0.22MPa',
            '缶体材質': 'SUS304',
            '圧力容器の種類': '小型圧力容器',
            'ドアタイプ': '前面扉式',
            '安全装置': '安全弁、空焚き防止、過温防止、ドアインターロック',
        },
    },
    'KTR': {
        'description_base': 'アルプKTRシリーズ。卓上型小型滅菌器。研究室向け。',
        'extra_specs': {
            '最高使用圧力': '0.157MPa',
            '缶体材質': 'SUS304',
            '圧力容器の種類': '簡易圧力容器',
            'ドアタイプ': '上蓋式',
            '安全装置': '安全弁、空焚き防止',
        },
    },
    'KYR': {
        'description_base': 'アルプKYRシリーズ。エコノミー卓上型滅菌器。',
        'extra_specs': {
            '最高使用圧力': '0.157MPa',
            '缶体材質': 'SUS304',
            '圧力容器の種類': '簡易圧力容器',
            'ドアタイプ': '上蓋式',
            '安全装置': '安全弁、空焚き防止',
        },
    },
}

for p in alp_products:
    new_specs = {}
    for k, v in p.get('specs', {}).items():
        new_key = ALP_RENAME.get(k, k)
        new_specs[new_key] = v

    model = p.get('model', '')
    # シリーズ判定（長い方から優先マッチ）
    matched = None
    for sk in sorted(ALP_SERIES.keys(), key=len, reverse=True):
        if model.startswith(sk):
            matched = sk
            break

    if matched:
        info = ALP_SERIES[matched]
        if not p.get('description') or len(p['description']) < 20:
            p['description'] = info['description_base']
        for ek, ev in info['extra_specs'].items():
            if ek not in new_specs:
                new_specs[ek] = ev

    p['specs'] = new_specs

with open(ALP_PATH, 'w', encoding='utf-8') as fp:
    for p in alp_products:
        fp.write(json.dumps(p, ensure_ascii=False) + '\n')

print(f"\nアルプ: {len(alp_products)}製品更新")
for p in alp_products:
    print(f"  {p['model']}: {len(p.get('specs',{}))}項目")
