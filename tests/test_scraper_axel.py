"""AXEL スクレイパーのテスト"""
import json
import os
import pytest
from scripts.scraper_axel import (
    parse_product_list,
    parse_product_detail,
    filter_pb_brands,
)


FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _read(name):
    with open(os.path.join(FIXTURE_DIR, name), encoding="utf-8") as f:
        return f.read()


def test_parse_product_list_extracts_items():
    html = _read("axel_list_sample.html")
    items = parse_product_list(html, base_url="https://axel.as-1.co.jp")
    assert len(items) >= 1
    sample = items[0]
    assert "name" in sample
    assert "url" in sample
    assert sample["url"].startswith("https://")


def test_filter_pb_brands_keeps_as_one_and_navis():
    items = [
        {"name": "x", "url": "/x", "maker": "アズワン"},
        {"name": "y", "url": "/y", "maker": "ナビス"},
        {"name": "z", "url": "/z", "maker": "ヤマト科学"},
        {"name": "w", "url": "/w", "maker": ""},
    ]
    out = filter_pb_brands(items)
    makers = {it["maker"] for it in out}
    assert "アズワン" in makers
    assert "ナビス" in makers
    assert "ヤマト科学" not in makers


def test_parse_product_detail_returns_specs():
    html = _read("axel_detail_sample.html")
    detail = parse_product_detail(html)
    assert isinstance(detail.get("specs"), dict)
    assert len(detail["specs"]) >= 1 or detail.get("name")
