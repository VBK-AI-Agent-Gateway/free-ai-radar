# -*- coding: utf-8 -*-
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "agents"))
import collector

def test_digest_stable_and_order_insensitive():
    a = collector.digest({"x": 1, "y": 2})
    b = collector.digest({"y": 2, "x": 1})
    assert a == b

def test_digest_changes_on_content():
    assert collector.digest({"x": 1}) != collector.digest({"x": 2})

def test_dry_run_lists_sources(capsys):
    rc = collector.main(["--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0 and "openai" in out
