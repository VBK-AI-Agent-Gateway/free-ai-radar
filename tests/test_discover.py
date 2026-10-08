# -*- coding: utf-8 -*-
"""发现员测试: mock 外部目录,验证免费判定 + 候选 diff + 覆盖率。"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "agents"))
import discover


def test_ref_free_providers_marks_free(monkeypatch):
    """models.dev 的 cost:{input:0,output:0} 判免费,非 0 不判。"""
    fake = {
        "provA": {"models": {"m1": {"cost": {"input": 0, "output": 0}},
                             "m2": {"cost": {"input": 1, "output": 2}}}},
        "provB": {"models": {"m3": {"cost": {"input": 0.5, "output": 0}}}},
        "provC": {"models": {"m4": {}}},  # 无 cost -> 不判
    }
    monkeypatch.setattr(discover, "_get", lambda url, timeout=25: fake)
    ref = discover.ref_free_providers()
    assert "provA" in ref and ref["provA"]["free_models"] == ["m1"]
    assert "provB" not in ref  # output 非 0
    assert "provC" not in ref  # 无 cost


def test_build_candidates_excludes_canonical(monkeypatch, tmp_path):
    """已在正本的厂商不进候选;未知厂商进候选。"""
    fake = {"openrouter": {"models": {"m": {"cost": {"input": 0, "output": 0}}}},
            "newprov": {"models": {"n": {"cost": {"input": 0, "output": 0}}}}}
    monkeypatch.setattr(discover, "_get", lambda url, timeout=25: fake)
    monkeypatch.setattr(discover, "load_canonical_providers", lambda: {"openrouter"})
    monkeypatch.setattr(discover, "canonical_free_ids", lambda: set())
    monkeypatch.setattr(discover, "CAND", tmp_path)
    cands = discover.build_candidates()
    assert "openrouter" not in cands, "canonical provider must not be a candidate"
    assert "newprov" in cands, "unknown provider must be a candidate"
    assert cands["newprov"]["status"] == "candidate"


def test_coverage_rate(monkeypatch):
    """覆盖率 = 正本已收录 / 外部目录总数。"""
    free_m = {"m": {"cost": {"input": 0, "output": 0}}}
    fake = {"p1": {"models": free_m}, "p2": {"models": free_m}, "p3": {"models": free_m}}
    monkeypatch.setattr(discover, "_get", lambda url, timeout=25: fake)
    monkeypatch.setattr(discover, "load_canonical_providers", lambda: {"p1"})
    cov = discover.coverage({})
    assert cov["ref_providers"] == 3
    assert cov["covered"] == 1
    assert cov["candidate"] == 2
    # coverage() 返回 round(rate,3),比对放宽到该精度
    assert abs(cov["coverage_rate"] - 1/3) < 5e-4
