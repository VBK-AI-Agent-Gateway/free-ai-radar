# -*- coding: utf-8 -*-
"""探测员:用公开无 key 的最小请求实测可用性/延迟/免费标记。
唯一能读探测密钥的智能体(GROQ_API_KEY 等,只从环境读,绝不打印)。
预算:每家每天最多 probe.daily_runs_per_provider 次,计数在 runs/probe-count.json。"""
import argparse, json, os, pathlib, sys, time
import requests, yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNS = ROOT / "runs"
STATE = ROOT / "state.local"
UA = {"User-Agent": "free-ai-radar/0 (+https://github.com/VBK-AI-Agent-Gateway/free-ai-radar)"}


def budgets():
    with open(ROOT / "config/budgets.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def sources():
    with open(ROOT / "config/sources.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)["sources"]


def today():
    return time.strftime("%Y-%m-%d", time.gmtime())


def count_path():
    return RUNS / "probe-count.json"


def read_counts():
    p = count_path()
    if p.exists():
        c = json.loads(p.read_text(encoding="utf-8"))
        if c.get("date") == today():
            return c
    return {"date": today(), "providers": {}}


def write_counts(c):
    RUNS.mkdir(exist_ok=True)
    count_path().write_text(json.dumps(c, indent=1), encoding="utf-8")


def probe_one(src, timeout):
    """-> dict: status(readable|needs_key|not_found|error), latency_ms, free_marker"""
    headers = dict(UA)
    url = src["url"]
    if src.get("needs_key"):
        key = os.environ.get(f"{src['provider'].upper()}_API_KEY") or os.environ.get("PROBE_API_KEY")
        if not key:
            return {"status": "needs_key", "latency_ms": None, "free_marker": None}
        if "groq" in src["provider"]:
            headers["Authorization"] = f"Bearer {key}"
        elif "google" in src["provider"]:
            url = f"{url}?key={key}"
    t0 = time.time()
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        ms = int((time.time() - t0) * 1000)
        if r.status_code == 200:
            body = r.text[:4000].lower()
            return {"status": "readable", "latency_ms": ms,
                    "free_marker": ("free" in body or ":free" in body),
                    "ratelimit_remaining": r.headers.get("x-ratelimit-remaining"),
                    "http": 200}
        if r.status_code in (401, 403):
            return {"status": "needs_key" if not src.get("needs_key") else "error",
                    "latency_ms": ms, "http": r.status_code}
        if r.status_code == 404:
            return {"status": "not_found", "latency_ms": ms, "http": 404}
        return {"status": "error", "latency_ms": ms, "http": r.status_code}
    except Exception as e:
        return {"status": "error", "latency_ms": None, "error": str(e)[:200]}


def main(argv=None):
    ap = argparse.ArgumentParser(description="探测员")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--provider", help="只探测这一家")
    args = ap.parse_args(argv)
    b = budgets()
    timeout = b["probe"]["request_timeout_sec"]
    daily = b["probe"]["daily_runs_per_provider"]
    if args.dry_run:
        for s in sources():
            print(f"[dry-run] would probe {s['provider']} {s['url']}")
        return 0
    counts = read_counts()
    results, skipped = [], []
    for s in sources():
        pid = s["provider"]
        if args.provider and pid != args.provider:
            continue
        used = counts["providers"].get(pid, 0)
        if used >= daily:
            skipped.append(pid)
            continue
        r = probe_one(s, timeout)
        r.update({"provider": pid, "url": s["url"], "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        results.append(r)
        counts["providers"][pid] = used + 1
    write_counts(counts)
    RUNS.mkdir(exist_ok=True)
    (RUNS / f"probe-{time.strftime('%Y-%m-%dT%H%M')}.json").write_text(
        json.dumps({"agent": "prober", "results": results, "skipped_budget": skipped},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"prober: probed {len(results)}, budget-skipped {len(skipped)} ({', '.join(skipped) or '-'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
