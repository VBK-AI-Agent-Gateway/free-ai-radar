# -*- coding: utf-8 -*-
"""免费类型分类(free_type) + 三态能力 + 安全 — 对应 docs/CALIBER.md, 修"价格0=免费"判定 bug。"""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "agents"))
import enrich, publisher


def test_classify_free_signals():
    # 订阅套餐 -> 不算免费
    assert enrich.classify_free(None, None, "GPT Coding Plan", "included in plan")[:1] == ("subscription",)
    # 本地软件 -> 不算免费
    assert enrich.classify_free(None, None, "LM Studio Chat", "runs locally")[:1] == ("local",)
    # 按次/按秒计费(非按token, 价格缺失) -> price_zero_unverified 待核验
    ft, free = enrich.classify_free(None, None, "Lyria", "priced per song")
    assert ft == "price_zero_unverified" and free is None
    # 显式 free -> free_tier
    assert enrich.classify_free(0, 0, "M", "", explicit_free=True) == ("free_tier", True)
    # 只有价格0、无证据 -> price_zero_unverified(不直接算免费, 避免假免费)
    assert enrich.classify_free(0, 0, "M", "") == ("price_zero_unverified", None)
    # 明确付费
    assert enrich.classify_free(0.5, 1.5, "M", "") == ("paid", False)
    # 什么都没有 -> unknown
    assert enrich.classify_free(None, None, "M", "") == ("unknown", None)


def test_paid_never_misclassified_by_description():
    # 评审第2条回归: 价格>0 无条件 paid, 不被描述里的 "per" 等文字信号误判成待核验
    assert enrich.classify_free(5.0, 25.0, "Claude Opus 5", "best model per benchmark", None, "anthropic/claude-opus-5")[0] == "paid"
    assert enrich.classify_free(10.0, 50.0, "GPT-6 Astra", "per token pricing", None, "openai/gpt-6-astra")[0] == "paid"
    assert enrich.classify_free(30.0, 0.0, "tts-1-hd", "speech per second", None, "openai/tts-1-hd")[0] == "paid"
    # :free / -free 后缀(价格0) -> free_variant
    assert enrich.classify_free(0, 0, "M", "", None, "openrouter/llama:free")[0] == "free_variant"
    assert enrich.classify_free(0, 0, "M", "", None, "poolside/laguna-s-2.1-free")[0] == "free_variant"


def test_derive_free_countable():
    assert enrich.derive_free("free_tier") is True
    assert enrich.derive_free("free_variant") is True
    assert enrich.derive_free("trial") is True
    assert enrich.derive_free("promo") is True
    assert enrich.derive_free("subscription") is False
    assert enrich.derive_free("local") is False
    assert enrich.derive_free("paid") is False
    assert enrich.derive_free("price_zero_unverified") is None   # 待核验, 不武断判
    assert enrich.derive_free("unknown") is None


def test_caps_tristate_keeps_none():
    # 接口不给 supported_parameters -> tools/reasoning/json 是 None(unknown), 不是 False
    caps = enrich._caps({"architecture": {"input_modalities": ["text", "image"]}})
    assert caps["image_input"] is True
    assert caps["tools"] is None and caps["reasoning"] is None and caps["json_mode"] is None
    # 接口明确给了 supported_parameters 但不含 tools -> False(明确不支持)
    caps2 = enrich._caps({"supported_parameters": ["temperature"], "architecture": {}})
    assert caps2["tools"] is False
    # 含 tools -> True
    caps3 = enrich._caps({"supported_parameters": ["tools", "reasoning"], "architecture": {"input_modalities": ["image"]}})
    assert caps3["tools"] is True and caps3["reasoning"] is True


def test_is_countable_free_gate():
    # publisher 免费总闸: 只有免费层/免费变体/试用/促销算免费; 待核验/订阅/本地不进
    assert publisher._is_countable_free({"free_type": "free_tier"}) is True
    assert publisher._is_countable_free({"free_type": "free_variant"}) is True
    assert publisher._is_countable_free({"free_type": "price_zero_unverified"}) is False
    assert publisher._is_countable_free({"free_type": "subscription"}) is False
    assert publisher._is_countable_free({"free_type": "local"}) is False
    # 没 free_type 时回落 free 布尔
    assert publisher._is_countable_free({"free": True}) is True
    assert publisher._is_countable_free({"free": False}) is False


def test_flat_keeps_capability_tristate():
    # 能力三态: None(unknown) 经 flat 后仍是 None, 不被压成 False
    rows = [{
        "provider": "p", "homepage": "https://x", "pricing_url": "https://x/p",
        "last_verified": "2026-01-01",
        "models": [{
            "id": "m", "name": "M", "free": True, "free_type": "free_variant",
            "status": "declared",
            "capabilities": {"image_input": True, "tools": None, "reasoning": None, "json_mode": None,
                             "context_length": 8192},
            "terms": {"input_per_million": 0, "output_per_million": 0},
        }],
    }]
    out = publisher.flat(rows)
    assert len(out) == 1
    m = out[0]
    assert m["image_input"] is True
    assert m["tools"] is None        # unknown 保留
    assert m["reasoning"] is None
    assert m["free_type"] == "free_variant"
    assert m["context_length"] == 8192


def test_flat_shows_zero_price_as_pending():
    # price_zero_unverified(价格0但待核验) 现在进页面(诚实待核验), 但 free_type 保留供 badge 标"待核验"
    rows = [{
        "provider": "p", "homepage": "https://x",
        "models": [{"id": "z", "name": "Z", "free": None, "free_type": "price_zero_unverified", "capabilities": {}, "terms": {}}],
    }]
    out = publisher.flat(rows)
    assert len(out) == 1 and out[0]["free_type"] == "price_zero_unverified" and out[0]["free"] is None
    # 付费/订阅/本地 仍不进免费页
    rows2 = [{"provider": "p", "models": [
        {"id": "a", "free": False, "free_type": "paid", "capabilities": {}, "terms": {}},
        {"id": "b", "free": False, "free_type": "subscription", "capabilities": {}, "terms": {}},
        {"id": "c", "free": False, "free_type": "local", "capabilities": {}, "terms": {}},
    ]}]
    assert publisher.flat(rows2) == []


def test_site_has_security_and_tri_state():
    rows = [{
        "provider": "p", "homepage": "https://x", "pricing_url": "https://x/p",
        "signup": {"url": "https://x/s"}, "last_verified": "2026-01-01",
        "models": [{
            "id": "m", "name": "M", "free": True, "free_type": "free_variant",
            "status": "declared", "capabilities": {"tools": None}, "terms": {},
        }],
    }]
    html = publisher.render_site(rows)
    # 安全: https 白名单 + 去内联 onclick 注入(data-reg/数据属性) + esc 补单引号
    assert "safeUrl" in html
    assert "data-reg" in html
    assert "esc = s =>" in html and "&#39;" in html          # esc 转义单引号
    assert 'onclick="regClick(' not in html                  # 不再内联拼 provider
    assert "REPORT_KINDS.map(k=>" not in html                 # 上报按钮也走 data-attr
    # 三态: 未知标签 + 筛选 capPass + 待核验区分
    assert "未知" in html and "capPass" in html          # zh 字典(切换后可见)
    # 时间拆分: 实测/抓取
    assert "实测" in html and "抓取" in html
    # 首页数字统一
    assert "已收录" in html and "目录发现" in html and "已实测" in html
    # 降频 5 分钟
    assert "300000" in html


def test_english_default_and_lang_switch():
    # 英文界面为默认, 且提供 i18n 字典 + 语言切换器(评审 #7: 英文界面)
    rows = [{"provider": "p", "homepage": "https://x", "pricing_url": "https://x/p",
             "signup": {"url": "https://x/s"}, "models": [
             {"id": "m", "name": "M", "free": True, "free_type": "free_variant", "capabilities": {}, "terms": {}}]}]
    html = publisher.render_site(rows)
    assert 'let LANG = "en"' in html                 # 英文默认
    assert '<html lang="en">' in html
    assert "I18N" in html and 'zh:' in html           # 中文字典存在(可切换)
    assert 'id="langsel"' in html                    # 语言切换器
    assert "applyLang" in html                        # 应用函数
    # 英文默认可见文案(在 body, 不只在字典里)
    assert "Free only" in html and "Sort: free first" in html
    assert "data-i18n=" in html                      # 静态元素挂了 i18n 键