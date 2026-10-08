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
    evil = '<img src=x onerror=alert(1)>'
    text = publisher.render_site([{"provider": "p", "models": [{"id": "p/" + evil, "status": "declared", "description": evil}], "last_verified": "unknown", "pricing_url": "u"}])
    # 数据进 JSON,载荷不得以裸 HTML 出现在 JS 上下文之外,也不得裸露 onerror 载荷
    body = text.split("</style>", 1)[-1]
    assert evil not in body            # 载荷不裸露(被 JSON 转义/放在 script 数据里)
    assert "<h1>" in text              # 结构完好
    assert "render();" in text         # 客户端渲染存在
