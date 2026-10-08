# -*- coding: utf-8 -*-
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "agents"))
import publisher

def test_flat_lists_models():
    rows = [{"provider": "p", "models": [{"id": "p/m", "status": "declared", "free": True}], "last_verified": "unknown", "pricing_url": "u"}]
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


def test_site_js_regurl_quoted():
    """回归: REG_URL 占位符在 JS 中必须带引号,否则整页 JS 语法错误 -> 空白页。"""
    import re, subprocess, tempfile, os
    import publisher
    html = publisher.render_site([])
    # 找 JS 里的 REG_URL 赋值行
    m = re.search(r'const REG_URL = (.*?);', html)
    assert m, "REG_URL not found in site"
    val = m.group(1).strip()
    assert val.startswith('"') and val.endswith('"'), f"REG_URL unquoted: {val}"


def test_site_js_parses():
    """回归: 把内联 <script> 抽出来用 node --check 验语法,防占位符破坏 JS。"""
    import re, shutil, subprocess, tempfile, os
    import publisher
    html = publisher.render_site([])
    scripts = re.findall(r'<script>(.*?)</script>', html, re.S)
    assert scripts, "no script block"
    node = shutil.which("node")
    if not node:
        import pytest; pytest.skip("node not available")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(scripts[0]); path = f.name
    try:
        r = subprocess.run([node, "--check", path], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
    finally:
        os.unlink(path)


def test_only_free_gate():
    """免费总闸: 默认 flat 只出免费模型;--include-paid 才带付费。"""
    rows = [{"provider": "p", "models": [
        {"id": "p/free", "free": True},
        {"id": "p/paid", "free": False},
    ], "last_verified": "unknown"}]
    publisher.ONLY_FREE = True
    out = publisher.flat(rows)
    assert [m["id"] for m in out] == ["p/free"], "default must show only free"
    publisher.ONLY_FREE = False
    out2 = publisher.flat(rows)
    assert len(out2) == 2, "--include-paid must include paid"
    publisher.ONLY_FREE = True  # restore


def test_register_url_per_provider():
    """每模型注册跳转到该厂商自己的 signup,不是统一 openrouter。"""
    rows = [
        {"provider": "openrouter", "signup": {"url": "https://openrouter.ai/sign-up"},
         "models": [{"id": "a/b", "free": True}]},
        {"provider": "groq", "signup": {"url": "https://console.groq.com/keys"},
         "models": [{"id": "c/d", "free": True}]},
    ]
    publisher.ONLY_FREE = True
    out = publisher.flat(rows)
    by = {m["provider"]: m["register_url"] for m in out}
    assert by["openrouter"] == "https://openrouter.ai/sign-up"
    assert by["groq"] == "https://console.groq.com/keys"
    assert by["openrouter"] != by["groq"], "must differ per provider"
