# -*- coding: utf-8 -*-
"""审核入口(OpenRouter 式): 状态机 pending->approved/rejected + 查重拦截。"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "agents"))
import enrich


def test_review_state_machine(tmp_path, monkeypatch):
    monkeypatch.setattr(enrich, "QUEUE", tmp_path / "subs.json")
    enrich.save_queue([{"url": "https://a/v1/models", "model_id": "m", "note": "",
                        "at": "t", "status": "pending", "review": None}])
    s = enrich.queue_summary()
    assert s["pending"] == 1 and s["approved"] == 0
    item = enrich.review_submission(0, "approve", "ok")
    assert item["status"] == "approved" and item["review"]["decision"] == "approve"
    assert enrich.queue_summary()["approved"] == 1
    # 可改判
    item = enrich.review_submission(0, "reject", "paid")
    assert item["status"] == "rejected"
    # 越界 -> None
    assert enrich.review_submission(9, "approve") is None


def test_dedupe_blocks_duplicate_submission(tmp_path, monkeypatch):
    """重复 -> 无法提交(dedupe 返回 False)。"""
    monkeypatch.setattr(enrich, "QUEUE", tmp_path / "subs.json")
    acc, reason = enrich.ingest_submission({"url": "https://b/v1/models", "model_id": "x", "note": "n"})
    assert acc, "first submission accepted"
    # 同 URL 再投 -> 拒绝(队列查重)
    acc2, reason2 = enrich.ingest_submission({"url": "https://b/v1/models", "model_id": "y", "note": ""})
    assert not acc2 and "duplicate" in reason2, "duplicate url must be blocked"
    assert enrich.queue_summary()["total"] == 1, "duplicate must not be queued"


def test_page_has_submit_entry_and_issue_redirect():
    """页面: 顶部投稿入口 + 表单常显 + 重复时转 GitHub Issue 审核。"""
    import publisher
    html = publisher.render_site([{"provider": "p", "model_id": "m", "name": "M",
        "free": True, "source": "official_api", "evidence": {"url": "https://x"},
        "last_verified": "2026"}])
    assert 'class="submitbar"' in html, "top submit entry visible"
    assert 'id="subform"' in html, "submit form present"
    assert "issues/new" in html, "submission must route to GitHub Issues (review queue)"
    assert "无法提交" in html, "duplicate must show cannot-submit message"
    assert "function openSubmit" in html
