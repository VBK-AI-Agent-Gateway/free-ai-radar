# -*- coding: utf-8 -*-
import json, pathlib, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "agents"))
import prober

def test_dry_run_lists_sources(capsys, monkeypatch, tmp_path):
    # 指到临时目录,别污染仓库 state
    monkeypatch.setattr(prober, "RUNS", tmp_path)
    monkeypatch.setattr(prober, "STATE", tmp_path)
    rc = prober.main(["--dry-run"])
    assert rc == 0 and "openrouter" in capsys.readouterr().out

def test_needs_key_without_secret(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("PROBE_API_KEY", raising=False)
    r = prober.probe_one({"provider": "groq", "url": "https://api.groq.com/openai/v1/models", "needs_key": True}, 5)
    assert r["status"] == "needs_key"

def test_budget_cap(tmp_path, monkeypatch):
    (tmp_path / "probe-count.json").write_text(json.dumps({"date": time.strftime("%Y-%m-%d", time.gmtime()),
                                                           "providers": {"groq": 2}}), encoding="utf-8")
    monkeypatch.setattr(prober, "RUNS", tmp_path)
    monkeypatch.setattr(prober, "count_path", lambda: tmp_path / "probe-count.json")
    c = prober.read_counts()
    assert c["providers"]["groq"] >= 2  # 已达每日 2 次上限
