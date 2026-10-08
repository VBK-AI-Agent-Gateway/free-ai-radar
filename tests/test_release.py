# -*- coding: utf-8 -*-
"""release: 新增免费模型 diff 逻辑。"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "agents"))
import json, pathlib
import release


def test_diff_new_detects_added(tmp_path):
    """基线少一个 -> 能 diff 出新增。"""
    base = tmp_path / "base.json"
    cur = tmp_path / "cur.json"
    base.write_text(json.dumps({"models": [
        {"id": "a/x", "free": True}, {"id": "a/y", "free": True}]}), encoding="utf-8")
    cur.write_text(json.dumps({"models": [
        {"id": "a/x", "free": True}, {"id": "a/y", "free": True},
        {"id": "b/new", "free": True}]}), encoding="utf-8")
    _, new, skip = release.diff_new(base, cur)
    assert not skip
    assert new == ["b/new"], "must detect the added free model"


def test_diff_new_paid_not_counted(tmp_path):
    """付费模型新增不算免费新增。"""
    base = tmp_path / "base.json"; cur = tmp_path / "cur.json"
    base.write_text(json.dumps({"models": [{"id": "a/x", "free": True}]}), encoding="utf-8")
    cur.write_text(json.dumps({"models": [
        {"id": "a/x", "free": True}, {"id": "p/paid", "free": False}]}), encoding="utf-8")
    _, new, skip = release.diff_new(base, cur)
    assert not skip and new == [], "paid model must not count as new free"


def test_diff_new_no_baseline_skips(tmp_path):
    """首轮无基线 -> 跳过(不为存量发 Release)。"""
    cur = tmp_path / "cur.json"
    cur.write_text(json.dumps({"models": [{"id": "a/x", "free": True}]}), encoding="utf-8")
    _, new, skip = release.diff_new(tmp_path / "missing.json", cur)
    assert skip, "missing baseline must skip"


def test_diff_new_no_change_skips(tmp_path):
    """无变化 -> new 为空(主函数据此跳过)。"""
    base = tmp_path / "base.json"; cur = tmp_path / "cur.json"
    same = json.dumps({"models": [{"id": "a/x", "free": True}]})
    base.write_text(same, encoding="utf-8"); cur.write_text(same, encoding="utf-8")
    _, new, skip = release.diff_new(base, cur)
    assert not skip and new == []
