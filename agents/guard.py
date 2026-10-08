# -*- coding: utf-8 -*-
"""守卫:入库前安全闸。key 扫描、注入检测、格式校验、查重。纯规则,不调 AI。
用法: python agents/guard.py --file providers/openai.yaml   (CI 在 commit 前跑)"""
import argparse, json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
ALLOW_TOP = {"provider", "homepage", "pricing_url", "signup", "models", "evidence", "last_verified"}
ALLOW_MODEL = {"id", "status", "free", "capabilities", "terms", "evidence", "last_verified", "ttl_days", "name", "notes", "description", "created"}
STATUSES = {"verified", "declared", "reported", "disputed", "stale"}
SOURCE_KINDS = {"probe", "official_api", "official_page", "vendor_submission", "community", "telemetry",
                "page_quote", "detector", "human"}

KEY_PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "openai-style key"),
    (re.compile(r"ghp_[A-Za-z0-9]{20,}"), "github PAT"),
    (re.compile(r"AIza[0-9A-Za-z\-_]{30,}"), "google api key"),
    (re.compile(r"gsk_[A-Za-z0-9]{20,}"), "groq key"),
    (re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{20,}"), "bearer token"),
]
INJECT = re.compile(r"ignore\s+(all\s+)?(previous|above)\s+instructions|system prompt|你是一个开发者|forget your rules", re.I)
def scan_keys(text):
    return [name for pat, name in KEY_PATTERNS if pat.search(text)]


def guard_text(text, seen_ids=None):
    """返回错误列表;空列表=通过。"""
    errs = []
    hits = scan_keys(text)
    if hits:
        errs.append(f"BLOCKED key-like content: {', '.join(hits)} -> 立刻吊销该密钥!")
    if INJECT.search(text):
        errs.append("BLOCKED instruction-like text in data (提示注入嫌疑)")
    return errs


def guard_provider(data, seen_ids=None):
    errs = []
    if not isinstance(data, dict):
        return ["root must be a mapping"]
    unknown = set(data) - ALLOW_TOP
    if unknown:
        errs.append(f"unknown top-level fields: {sorted(unknown)}")
    for m in data.get("models", []) or []:
        if not isinstance(m, dict) or "id" not in m:
            errs.append("model entry missing id"); continue
        bad = set(m) - ALLOW_MODEL
        if bad:
            errs.append(f"model {m['id']}: unknown fields {sorted(bad)}")
        st = m.get("status")
        if st is not None and st not in STATUSES:
            errs.append(f"model {m['id']}: bad status {st!r}")
        for ev in m.get("evidence", []) or []:
            if isinstance(ev, dict) and ev.get("kind") and ev["kind"] not in SOURCE_KINDS:
                errs.append(f"model {m['id']}: bad evidence kind {ev['kind']!r}")
        if seen_ids is not None:
            if m["id"] in seen_ids:
                errs.append(f"duplicate model id {m['id']}")
            seen_ids.add(m["id"])
    return errs


def main(argv=None):
    ap = argparse.ArgumentParser(description="守卫")
    ap.add_argument("--file", nargs="+", required=True, help="要检查的 yaml/json 文件(可多个,支持 shell 通配展开)")
    args = ap.parse_args(argv)
    import yaml
    failed = 0
    for fp in (args.file or []):
        p = pathlib.Path(fp)
        text = p.read_text(encoding="utf-8")
        errs = guard_text(text)
        try:
            data = yaml.safe_load(text)
        except Exception as e:
            errs.append(f"yaml parse error: {e}")
            data = None
        if data is not None and p.suffix in (".yaml", ".yml") and "providers" in str(p.parent):
            errs += guard_provider(data)
        if errs:
            failed = 1
            print(f"GUARD FAIL {fp}:")
            for e in errs:
                print(f"  - {e}")
        else:
            print(f"guard ok: {fp}")
    return failed


if __name__ == "__main__":
    raise SystemExit(main())
