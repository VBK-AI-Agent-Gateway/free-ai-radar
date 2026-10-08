# -*- coding: utf-8 -*-
"""发现员(方案第 1 层: 目录/聚合器): 把外部目录当参考并集,对比正本,把"有免费层但没收录"
的厂商/模型推进候选队列 candidates/discover.json,标待确认。纯代码,不调 AI,不碰密钥。
覆盖率度量(方案"怎么证明覆盖多少")也算在这里。"""
import json, pathlib, sys, time, urllib.request, urllib.error, urllib.parse
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROV = ROOT / "providers"
SNAP = ROOT / "snapshots"
CAND = ROOT / "candidates"
UA = {"User-Agent": "free-ai-radar/0 (+https://github.com/VBK-AI-Agent-Gateway/free-ai-radar)"}

# 外部参考目录(方案第 1 层): models.dev + OpenRouter。偏西方,会高估覆盖(方案已注明)。
REF_DIRS = {
    "models_dev": "https://models.dev/api.json",
    "openrouter": "https://openrouter.ai/api/v1/models",
}


def _get(url, timeout=25):
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"discover: fetch fail {url}: {str(e)[:120]}", file=sys.stderr)
        return None


def load_canonical_providers():
    """正本里已收录的厂商 id -> set。"""
    out = set()
    for fp in PROV.glob("*.yaml"):
        out.add(fp.stem)
    return out


def canonical_free_ids():
    """正本里已收录的免费模型 id -> set(用于查重)。"""
    free = set()
    for fp in PROV.glob("*.yaml"):
        d = yaml.safe_load(fp.read_text(encoding="utf-8")) or {}
        for m in d.get("models") or []:
            if m.get("free"):
                free.add(m.get("id"))
    return free


def ref_free_providers():
    """外部目录'有免费层'的真厂商 -> {provider: {free_models:[...], src}}。
    provider 级只取 models.dev(226 个真厂商 key);openrouter 是聚合器且其 20 个 free 已在正本,
    不产候选(否则把 author/model 当厂商全是噪音)。pricing=null 不判免费(宁可少收)。"""
    found = {}
    md = _get(REF_DIRS["models_dev"])
    if isinstance(md, dict):
        for prov, info in md.items():
            models = (info or {}).get("models") or {}
            free_ids = []
            for mid, mi in models.items():
                c = (mi or {}).get("cost")   # 定价在 cost:{input,output}($/1M),不是 pricing
                if not isinstance(c, dict):
                    continue
                try:
                    if str(c.get("input", "x")).strip() in ("0", "0.0") and str(c.get("output", "x")).strip() in ("0", "0.0"):
                        free_ids.append(mid)
                except Exception:
                    pass
            if free_ids:
                found.setdefault(prov, {"free_models": free_ids, "src": "models_dev"})
    return found


def build_candidates():
    """外部目录的免费来源 - 正本已收录 = 候选(标待确认)。"""
    have = load_canonical_providers()
    have_free_ids = canonical_free_ids()
    ref = ref_free_providers()
    CAND.mkdir(exist_ok=True)
    out = []
    for prov, info in ref.items():
        if prov in have:
            continue  # 已收录该厂商
        new_models = [m for m in info["free_models"] if m not in have_free_ids]
        if not new_models and prov not in have:
            out.append({"provider": prov, "status": "candidate", "reason": "provider not in canonical",
                        "src": info["src"], "free_models": info["free_models"][:20]})
        elif new_models:
            out.append({"provider": prov, "status": "candidate", "reason": "provider not in canonical",
                        "src": info["src"], "free_models": new_models[:20]})
    # 写队列(去重:按 provider)
    by_p = {c["provider"]: c for c in out}
    (CAND / "discover.json").write_text(
        json.dumps({"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "candidates": list(by_p.values())}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    return by_p


def coverage(candidates):
    """方案"怎么证明覆盖多少"的最简版: 外部目录并集里,正本收录了多少。
    ref_total=外部目录有免费层的厂商数;covered=其中已在正本的;rate=covered/ref_total。"""
    have = load_canonical_providers()
    ref = ref_free_providers()
    ref_total = len(ref)
    covered = sum(1 for p in ref if p in have)
    rate = (covered / ref_total) if ref_total else None
    return {"ref_providers": ref_total, "covered": covered,
            "candidate": ref_total - covered,
            "coverage_rate": round(rate, 3) if rate is not None else None,
            "note": "外部目录并集偏西方,会高估覆盖(方案注明);这是参考不是真值"}


def community_mentions():
    """方案第 4 层(社区/媒体发现): 抓 HN Algolia 公开搜'免费 LLM API'帖,提取标题提到的平台线索。
    纯发现,不入库 -> 进 candidates/community.json 标待确认。Reddit 匿名 403,暂不接。"""
    q = urllib.parse.quote("free LLM API free tier")
    data = _get(f"https://hn.algolia.com/api/v1/search?query={q}&tags=story&hitsPerPage=20")
    if not isinstance(data, dict):
        return []
    out = []
    for h in data.get("hits") or []:
        title = (h.get("title") or "").strip()
        if title:
            out.append({"title": title[:160],
                        "url": f"https://news.ycombinator.com/item?id={h.get('objectID')}",
                        "points": h.get("points"), "at": h.get("created_at")})
    (CAND / "community.json").write_text(
        json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "source": "hn_algolia", "mentions": out}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    return out


def regional_candidates():
    """把候选按地区粗分(方案'其它国家地区'): 启发式按已知地区厂商名归类。写 candidates/regional.json。"""
    # 启发式地区映射(厂商名关键词 -> 地区)。只标注,不保证(候选本来就待确认)。
    regions = {
        "cn": ("alibaba", "qwen", "zhipu", "zai", "baidu", "qianfan", "volcengine", "dashscope",
               "deepseek", "moonshot", "kimi", "minimax", "baichuan", "stepfun", "iflytek", "siliconflow",
               "xiaomi", "scnet", "iflowcn", "modelscope", "bothub", "tencent"),
        "in": ("sarvam", "krutrim", "indiallm", "kissan"),
        "jp": ("rinna", "sakana", "cyberagent", "elastika"),
        "kr": ("exaone", "lgai", "naver", "hyperclova"),
        "ru": ("yandex", "sber", "gigachat"),
        "me": ("g42", "core42", "jais", "tap"),
        "sea": ("sea-lion", "sealion", "globant", "grit"),
        "eu": ("mistral", "ovhcloud", "hetzner", "infomaniak", "adept", "mistral_fr", "deepinfra_eu"),
    }
    cands = json.loads((CAND / "discover.json").read_text(encoding="utf-8")).get("candidates", [])
    grouped = {k: [] for k in regions}
    grouped["other"] = []
    for c in cands:
        p = (c.get("provider") or "").lower()
        placed = False
        for reg, keys in regions.items():
            if any(k in p for k in keys):
                grouped[reg].append(c["provider"]); placed = True; break
        if not placed:
            grouped["other"].append(c["provider"])
    grouped = {k: v for k, v in grouped.items() if v}
    (CAND / "regional.json").write_text(
        json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "note": "启发式地区标注,候选待确认", "regions": grouped}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    return grouped


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="发现员")
    ap.add_argument("--json", action="store_true", help="只打印 JSON 报告")
    args = ap.parse_args(argv)
    cands = build_candidates()
    cov = coverage(cands)
    comm = community_mentions()          # 第 4 层: 社区/媒体发现
    reg = regional_candidates()          # 其它国家地区候选归类
    report = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "coverage": cov, "candidates": list(cands.values())[:50],
              "community_mentions": len(comm),
              "regional_groups": {k: len(v) for k, v in reg.items()}}
    (CAND / "coverage.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    else:
        print(f"discover: ref={cov['ref_providers']} covered={cov['covered']} "
              f"candidate={cov['candidate']} rate={cov['coverage_rate']}")
        print(f"  community mentions: {len(comm)} | regional groups: {len(reg)}")
        for c in list(cands.values())[:10]:
            print(f"  + {c['provider']} ({c['src']}): {len(c['free_models'])} free models")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())