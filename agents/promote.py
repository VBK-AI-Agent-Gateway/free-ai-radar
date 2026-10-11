# -*- coding: utf-8 -*-
"""转化员(候选 -> 正本采集源): 把 candidates/discover.json 里带 models_url 的候选
端点逐一探测,通过则加进 config/sources.yaml,由既有管线(collector 抓快照 ->
enrich.run_new_channels 解析 -> providers/*.yaml)接管。纯代码,不调 AI,不碰密钥。

资格标准(宁可少收,不可编造): 匿名 GET 200 + 返回 JSON + data 数组非空。
不重复加(已有同 provider 源则跳过)。加进 sources.yaml 的源全部:
  type=official_api, parser=openai_compat, check=daily, 无 needs_key。
"""
import json, pathlib, sys, yaml
import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
CAND = ROOT / "candidates" / "discover.json"
SOURCES = ROOT / "config" / "sources.yaml"
PROV = ROOT / "providers"
UA = {"User-Agent": "free-ai-radar/0 (+https://github.com/VBK-AI-Agent-Gateway/free-ai-radar)"}


def _homepage(url):
    from urllib.parse import urlparse
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def ensure_homepage(pid, url):
    """promote 时给正本补 homepage(根URL),让 free_catalog 能算出申请链接。幂等:已有 signup/homepage 不动。"""
    PROV.mkdir(exist_ok=True)
    fp = PROV / f"{pid}.yaml"
    d = yaml.safe_load(fp.read_text(encoding="utf-8")) if fp.exists() else {"provider": pid, "models": []}
    if not (d.get("signup") or {}).get("url") and not d.get("homepage"):
        d["homepage"] = _homepage(url)
        fp.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")


def load_candidates():
    if not CAND.exists():
        return []
    return json.loads(CAND.read_text(encoding="utf-8")).get("candidates") or []


def load_sources():
    doc = yaml.safe_load(SOURCES.read_text(encoding="utf-8")) or {}
    return doc.get("sources") or []


def probe_endpoint(url, timeout=15):
    """-> (ok, info) 匿名探测 models_url: 必须 200 + JSON + data 非空。"""
    try:
        r = requests.get(url, headers=UA, timeout=timeout)
        if r.status_code != 200:
            return False, f"HTTP {r.status_code}"
        try:
            payload = r.json()
        except Exception:
            return False, "not JSON"
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list) or not data:
            return False, "no data[] array"
        return True, {"count": len(data)}
    except Exception as e:
        return False, str(e)[:160]


def promote(dry_run=False):
    """扫描候选,探测合格端点,写进 sources.yaml。返回 (promoted, skipped)。"""
    cands = load_candidates()
    existing = load_sources()
    have = {s.get("provider") for s in existing}
    have_urls = {s.get("url") for s in existing}
    promoted, skipped = [], []

    for c in cands:
        pid = c.get("provider")
        url = c.get("models_url")
        if not pid or not url:
            continue
        if pid in have or url in have_urls:
            skipped.append((pid, "already in sources"))
            continue
        ok, info = probe_endpoint(url)
        if not ok:
            skipped.append((pid, info))
            continue
        promoted.append((pid, url, info["count"]))
        if not dry_run:
            ensure_homepage(pid, url)
            existing.append({
                "provider": pid,
                "type": "official_api",
                "url": url,
                "check": "daily",
                "parser": "openai_compat",
            })

    if promoted and not dry_run:
        doc = yaml.safe_load(SOURCES.read_text(encoding="utf-8")) or {}
        doc["sources"] = existing
        SOURCES.write_text(
            yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")

    return promoted, skipped


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="转化员: 候选端点 -> sources.yaml")
    ap.add_argument("--dry-run", action="store_true", help="只探测打印,不写 sources.yaml")
    args = ap.parse_args(argv)
    promoted, skipped = promote(dry_run=args.dry_run)
    for pid, url, n in promoted:
        print(f"promote {pid}: {url} ({n} models)" + (" [dry-run]" if args.dry_run else ""))
    for pid, why in skipped:
        print(f"skip {pid}: {why}")
    print(f"promote: {len(promoted)} promoted, {len(skipped)} skipped"
          + (" (dry-run)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())