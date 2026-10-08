# -*- coding: utf-8 -*-
"""采集员:抓官方接口/页面 -> snapshots/{provider}.{ext},对比出变化事件。
纯代码,不调 AI。探测密钥不在此读(那是探测员的权限)。"""
import argparse, hashlib, json, os, pathlib, sys, time
import requests, yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
SNAP = ROOT / "snapshots"
RUNS = ROOT / "runs"
UA = {"User-Agent": "free-ai-radar/0 (+https://github.com/VBK-AI-Agent-Gateway/free-ai-radar)"}


def load_sources():
    with open(ROOT / "config/sources.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)["sources"]


def _headers(src):
    """needs_key 的接口注入对应密钥(只从环境读,绝不打印/落盘)。"""
    h = dict(UA)
    if not src.get("needs_key"):
        return h
    pid = src["provider"]
    if pid == "google":
        k = os.environ.get("GEMINI_API_KEY")
        if k:
            h["x-goog-api-key"] = k
    else:
        k = os.environ.get(f"{pid.upper()}_API_KEY") or os.environ.get("PROBE_API_KEY")
        if k:
            h["Authorization"] = f"Bearer {k}"
    return h


def fetch(src):
    """-> (ok, kind 'json'|'text', payload)"""
    try:
        r = requests.get(src["url"], headers=_headers(src), timeout=20)
        if r.status_code != 200:
            return False, None, f"HTTP {r.status_code}"
        if src["type"] == "official_api" or r.headers.get("content-type", "").startswith("application/json"):
            return True, "json", r.json()
        return True, "text", r.text
    except Exception as e:  # 网络/解析失败都算采集失败,保留旧快照
        return False, None, str(e)[:200]


def snap_paths(pid):
    return SNAP / f"{pid}.json", SNAP / f"{pid}.txt"


def digest(payload):
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def collect_one(src, changed_events):
    pid = src["provider"]
    ok, kind, payload = fetch(src)
    if not ok:
        return {"provider": pid, "ok": False, "error": payload}
    pj, pt = snap_paths(pid)
    old_hash = None
    if kind == "json" and pj.exists():
        old_hash = json.loads(pj.read_text(encoding="utf-8")).get("hash")
    new_hash = digest(payload)
    changed = old_hash is not None and old_hash != new_hash
    if kind == "json":
        pj.write_text(json.dumps({"fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                   "url": src["url"], "hash": new_hash, "payload": payload},
                                  ensure_ascii=False, indent=1), encoding="utf-8")
    else:
        pt.write_text(payload, encoding="utf-8")
    if changed:
        changed_events.append({"provider": pid, "url": src["url"], "type": src["type"],
                               "old_hash": old_hash, "new_hash": new_hash})
    return {"provider": pid, "ok": True, "changed": bool(changed and old_hash)}


def main(argv=None):
    ap = argparse.ArgumentParser(description="采集员")
    ap.add_argument("--dry-run", action="store_true", help="只打印,不写快照")
    args = ap.parse_args(argv)
    if args.dry_run:
        for s in load_sources():
            print(f"[dry-run] would fetch {s['provider']} {s['url']}")
        return 0
    SNAP.mkdir(exist_ok=True); RUNS.mkdir(exist_ok=True)
    events, results = [], []
    for s in load_sources():
        results.append(collect_one(s, events))
    report = {"agent": "collector", "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "results": results, "changes": events}
    (RUNS / f"collector-{time.strftime('%Y-%m-%dT%H%M')}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    (ROOT / "state.changes.json").write_text(json.dumps(events, ensure_ascii=False, indent=1), encoding="utf-8")
    fails = [r for r in results if not r["ok"]]
    print(f"collector: {len(results)} sources, {len(events)} changed, {len(fails)} failed")
    for f in fails:
        print(f"  FAIL {f['provider']}: {f['error']}", file=sys.stderr)
    return 0  # 单源失败不阻断(降级为保留上次快照并标待核验)


if __name__ == "__main__":
    raise SystemExit(main())
