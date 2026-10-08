# -*- coding: utf-8 -*-
"""enrich: 投稿去重 + 解析。守卫渠道扩充与查重逻辑。"""
import sys, pathlib, os
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents"))
import pytest, enrich


def test_parse_openrouter_free_flag():
    snap = {"data": [{"id": "m", "name": "M", "context_length": 1,
                      "pricing": {"prompt": "0", "completion": "0"}}]}
    out = enrich.parse_source(snap, {"url": "u", "parser": "openrouter"})
    assert out[0]["free"] is True
    assert out[0]["id"] == "openrouter/m"


def test_parse_openai_compat_skips_missing_id():
    snap = {"data": [{"id": ""}, {"id": "ok", "name": "OK"}]}
    out = enrich.parse_source(snap, {"url": "u", "parser": "openai_compat"})
    assert len(out) == 1 and out[0]["id"] == "ok"


def test_dedupe_url_and_model_id(monkeypatch):
    # 隔离队列文件
    monkeypatch.setattr(enrich, "QUEUE", ROOT / "state.test.subs.json")
    if enrich.QUEUE.exists():
        enrich.QUEUE.unlink()
    eu, ei = enrich.existing_source_urls(), enrich.existing_model_ids()
    a1, _ = enrich.dedupe_submission({"url": "https://dup.example/v1"}, eu, ei)
    # 投一次进队列
    enrich.ingest_submission({"url": "https://dup.example/v1", "model_id": "zz"})
    a2, r2 = enrich.dedupe_submission({"url": "dup.example/v1"}, eu, ei)          # scheme变体 -> 拒
    a3, _ = enrich.dedupe_submission({"url": "https://nx.example/v1",
                                      "model_id": sorted(ei)[0]}, eu, ei)          # 已存在模型 -> 拒
    assert a1 and not a2 and not a3
    assert "queue" in r2
    if enrich.QUEUE.exists():
        enrich.QUEUE.unlink()