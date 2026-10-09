# -*- coding: utf-8 -*-
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "agents"))
import updater

def test_openrouter_parses_free():
    # 新口径(docs/CALIBER.md): 价格=0 但无免费证据 -> price_zero_unverified/None(待核验), 不再直接判 True;
    # 只有明确付费 -> False; 带 :free 或显式 free 才 free_variant/free_tier/True。
    payload = {"data": [
        {"id": "a/m1", "name": "M1", "context_length": 8192,
         "pricing": {"prompt": "0", "completion": "0"}},          # 价格0, 无证据 -> None
        {"id": "a/m2", "name": "M2", "context_length": 4096,
         "pricing": {"prompt": "0.001", "completion": "0.002"}},   # 明确付费 -> False
        {"id": "a/free", "name": "M3", "free": True,
         "pricing": {"prompt": "0", "completion": "0"}},          # 显式 free -> True
    ]}
    out = updater.parse_openrouter(payload)
    assert out[0]["free"] is None and out[0]["free_type"] == "price_zero_unverified"
    assert out[1]["free"] is False and out[1]["free_type"] == "paid"
    assert out[2]["free"] is True and out[2]["free_type"] == "free_tier"
    assert out[0]["id"] == "openrouter/a/m1"

def test_google_free_on_generate_content():
    payload = {"models": [
        {"name": "models/gemini-2", "displayName": "Gemini 2",
         "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/embed", "displayName": "Embed",
         "supportedGenerationMethods": ["embedContent"]},
    ]}
    out = updater.parse_google(payload)
    assert out[0]["free"] is True
    assert out[1]["free"] is False

def test_openai_does_not_guess_price():
    payload = {"data": [{"id": "gpt-x"}]}
    out = updater.parse_openai(payload)
    assert out[0]["free"] is None  # 无证据不猜

def test_dry_run_runs(capsys):
    rc = updater.main(["--dry-run"])
    assert rc == 0
