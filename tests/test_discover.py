# -*- coding: utf-8 -*-
import json
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


def test_community_and_regional(monkeypatch, tmp_path):
    """社区发现 + 地区归类: 写出对应 json。"""
    monkeypatch.setattr(discover, "CAND", tmp_path)
    # mock HN 返回
    hn = {"hits": [{"title": "Free LLM API for students", "objectID": "123",
                    "points": 50, "created_at": "2026-01-01"}]}
    monkeypatch.setattr(discover, "_get", lambda url, timeout=25: hn)
    comm = discover.community_mentions()
    assert len(comm) == 1 and "Free LLM API" in comm[0]["title"]
    assert (tmp_path / "community.json").exists()
    # 地区归类: 造一个候选
    (tmp_path / "discover.json").write_text(json.dumps({"candidates": [
        {"provider": "alibaba-token-plan"}, {"provider": "mysteryprov"}]}), encoding="utf-8")
    reg = discover.regional_candidates()
    assert "alibaba-token-plan" in reg.get("cn", []), "cn vendor must group to cn"
    assert "mysteryprov" in reg.get("other", []), "unknown must go to other"
    assert (tmp_path / "regional.json").exists()


def test_free_catalog_build(tmp_path, monkeypatch):
    """免费模型目录: build 出 vendors,每个有 apply_url 或 live。"""
    import free_catalog
    monkeypatch.setattr(free_catalog, "DOCS", tmp_path)
    cat = free_catalog.build_catalog()
    assert cat["vendors"], "catalog must have vendors"
    for v in cat["vendors"]:
        assert v["free_count"] > 0
        assert v["status"] in ("live", "apply_key")
        # 每家都该有申请链接(models.dev doc 或正本 signup)
        assert v.get("apply_url"), f"{v['provider']} must have apply_url"
        # 链接必须诚实分类 + 按钮不冒充注册口
        assert v.get("link_kind") in ("signup", "console", "doc", "pricing", "homepage")
        assert v.get("btn"), f"{v['provider']} must have honest button label"
        # 文档链接的按钮不能叫去注册(不冒充注册口)
        if v["link_kind"] == "doc":
            assert v["btn"] != "去注册", "doc link must not claim signup"
    assert (tmp_path / "free-catalog.json").exists()


def test_verified_signup_urls_used():
    """已验证注册口必须被用上且标为 signup/去注册(方案A: 只升级curl验证过的)。"""
    import json as _json
    from pathlib import Path
    import free_catalog
    verified = free_catalog._verified_signups()
    assert verified, "config/signup_urls.json must exist with verified signups"
    cat = free_catalog.build_catalog()
    by = {v["provider"]: v for v in cat["vendors"]}
    for pid, url in verified.items():
        if pid not in by:
            continue  # 可能被正本收录(live)或不在候选
        v = by[pid]
        assert v["apply_url"] == url, f"{pid} must use verified signup {url}"
        assert v["link_kind"] == "signup", f"{pid} verified signup must classify as signup"
        assert v["btn"] == "去注册", f"{pid} verified signup must label 去注册"
