# -*- coding: utf-8 -*-
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "agents"))
import updater

def test_openrouter_parses_free():
    payload = {"data": [
        {"id": "a/m1", "name": "M1", "context_length": 8192,
         "pricing": {"prompt": "0", "completion": "0"}},
        {"id": "a/m2", "name": "M2", "context_length": 4096,
         "pricing": {"prompt": "0.001", "completion": "0.002"}},
    ]}
    out = updater.parse_openrouter(payload)
    assert out[0]["free"] is True
    assert out[1]["free"] is False
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
