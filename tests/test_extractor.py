# -*- coding: utf-8 -*-
"""抽取员(HTML)测试: 去标签、定价证据抽取、deepseek 免费判定。"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "agents"))
import extractor


def test_visible_text_strips_tags():
    raw = "<html><script>var x=1;</script><style>p{}</style><p>Hi <b>there</b></p></html>"
    t = extractor.visible_text(raw)
    assert "Hi there" in t
    assert "<p>" not in t and "var x" not in t and "p{}" not in t


def test_price_evidence_finds_pricing():
    text = "Some page. The prices listed below are in units of per 1M tokens. Model A input $0.15 output $0.66"
    ev = extractor.price_evidence(text)
    assert ev, "should extract a pricing excerpt"
    assert "per 1M" in ev[0]


def test_extract_deepseek_no_free():
    """deepseek 页无免费层 -> free=False, 且带 official_page 证据 URL。"""
    raw = "<div>The prices listed below are in units of per 1M tokens. input $0.15 output $0.66</div>"
    models = extractor.extract_deepseek(raw, "https://api-docs.deepseek.com/quick_start/pricing")
    assert len(models) == 1
    m = models[0]
    assert m["free"] is False, "no proof of free -> must not claim free"
    assert m["evidence"][0]["kind"] == "official_page"
    assert m["evidence"][0]["url"].startswith("https://")


def test_extractors_registered_deepseek():
    assert "deepseek" in extractor.EXTRACTORS, "deepseek template must be registered"
