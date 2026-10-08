# -*- coding: utf-8 -*-
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "agents"))
from verdict import judge

def test_verified():
    st, _ = judge("readable", True, "2026-10-07")
    assert st == "verified"

def test_disputed():
    st, _ = judge("readable", False, "2026-10-07")
    assert st == "disputed"

def test_declared():
    st, _ = judge("needs_key", True, "2026-10-07")
    assert st == "declared"

def test_stale_after_ttl():
    st, _ = judge("needs_key", True, "2020-01-01")
    assert st == "stale"

def test_reported_when_no_evidence():
    st, _ = judge(None, None, "unknown")
    assert st == "reported"
