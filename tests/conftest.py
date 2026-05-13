"""pytest 共通フィクスチャ"""
import os
import shutil
import tempfile
import pytest


@pytest.fixture
def tmp_projects_dir(monkeypatch):
    """テスト用に projects/ を一時ディレクトリに切り替える"""
    tmp = tempfile.mkdtemp(prefix='pb_test_')
    monkeypatch.setenv('PB_PROJECTS_DIR', tmp)
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)
