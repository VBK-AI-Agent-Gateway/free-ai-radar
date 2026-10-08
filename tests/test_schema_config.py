# -*- coding: utf-8 -*-
import pathlib, yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]

def test_budgets_limits():
    b = yaml.safe_load((ROOT / "config/budgets.yaml").read_text(encoding="utf-8"))
    assert b["ai"]["daily_call_limit"] == 100
    assert b["probe"]["daily_runs_per_provider"] == 2

def test_phase0_min_providers():
    files = sorted(p.name for p in (ROOT / "providers").glob("*.yaml"))
    assert len(files) >= 5, files  # 阶段0门槛=5家;渠道扩充后只增不减

def test_provider_yaml_schema():
    import sys
    sys.path.insert(0, str(ROOT / "agents"))
    import guard
    for fp in (ROOT / "providers").glob("*.yaml"):
        data = yaml.safe_load(fp.read_text(encoding="utf-8"))
        assert guard.guard_provider(data) == [], fp
        assert data["provider"] == fp.stem

def test_sources_have_evidence_type():
    srcs = yaml.safe_load((ROOT / "config/sources.yaml").read_text(encoding="utf-8"))["sources"]
    assert all(s["type"] in ("official_api", "official_page") for s in srcs)
