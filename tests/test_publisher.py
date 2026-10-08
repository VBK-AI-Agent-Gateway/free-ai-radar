# -*- coding: utf-8 -*-
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "agents"))
import publisher

def test_flat_lists_models():
    rows = [{"provider": "p", "models": [{"id": "p/m", "status": "declared"}], "last_verified": "unknown", "pricing_url": "u"}]
    out = publisher.flat(rows)
    assert out[0]["id"] == "p/m"

def test_render_readme_has_table():
    text = publisher.render_readme([{"provider": "openai", "models": [], "last_verified": "unknown", "pricing_url": "u"}])
    assert "| openai |" in text

def test_site_escapes_html():
    text = publisher.render_site([{"provider": "<script>", "models": [], "last_verified": "unknown", "pricing_url": "u"}])
    assert "<script>" not in text.split("<h1>")[1]  # 卡片区已转义
