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


def zukixa_free_providers():
    """方案第 1 层补充源: zukixa/cool-ai-stuff README 表格, 提取每行 Models 列的 /v1/models 端点。
    这些是 OpenAI 兼容的免费/试用 API 端点, 作为候选 provider 进队列待确认。
    返回 {provider: {free_models:[], src, models_url}}; provider 取自服务名(小写去空格)。"""
    url = "https://raw.githubusercontent.com/zukixa/cool-ai-stuff/main/README.md"
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=25) as r:
            text = r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"discover: fetch fail {url}: {str(e)[:120]}", file=sys.stderr)
        return {}
    found = {}
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 6:
            continue
        # 表头/分隔行跳过
        if cells[0].lower() in ("service", "services") or set(cells[0]) <= set("-: "):
            continue
        # 服务名在第 0 列的 [Name](link) 里
        name = cells[0]
        if "[" in name and "](" in name:
            name = name.split("[", 1)[1].split("]", 1)[0]
        name = name.strip().lower().replace(" ", "-")
        if not name:
            continue
        # Models 端点在任意列的 [Models](url) 里
        models_url = None
        for cell in cells:
            if "Models](" in cell:
                u = cell.split("](", 1)[1].rsplit(")", 1)[0]
                if "/models" in u or "/v1/models" in u:
                    models_url = u
                    break
        if not models_url:
            continue
        found.setdefault(name, {"free_models": [], "src": "zukixa", "models_url": models_url})
    return found


def build_candidates():
    """外部目录的免费来源 - 正本已收录 = 候选(标待确认)。"""
    have = load_canonical_providers()
    have_free_ids = canonical_free_ids()
    ref = ref_free_providers()
    # 合并 zukixa 发现源(端点级候选, free_models 留空待采集员接)
    for prov, info in zukixa_free_providers().items():
        if prov not in ref:
            ref[prov] = info
    # ① GitHub 发现源(搜活跃 repo README 里的 /v1/models 端点)
    for prov, info in github_free_endpoints().items():
        if prov not in ref:
            ref[prov] = info
    # ③ ClawLabsAI 目录源: openrouter 模型 id 补进 openrouter 候选的 free_models
    claw = clawlabs_free_models()
    if "openrouter" in claw and "openrouter" in ref:
        merged = list(dict.fromkeys(ref["openrouter"].get("free_models", []) + claw["openrouter"]["free_models"]))
        ref["openrouter"]["free_models"] = merged
    elif "openrouter" in claw:
        ref["openrouter"] = claw["openrouter"]
    CAND.mkdir(exist_ok=True)
    out = []
    for prov, info in ref.items():
        if prov in have:
            continue  # 已收录该厂商
        new_models = [m for m in info["free_models"] if m not in have_free_ids]
        if not new_models and prov not in have:
            out.append({"provider": prov, "status": "candidate", "reason": "provider not in canonical",
                        "src": info["src"], "free_models": info["free_models"][:20],
                        "models_url": info.get("models_url")})
        elif new_models:
            out.append({"provider": prov, "status": "candidate", "reason": "provider not in canonical",
                        "src": info["src"], "free_models": new_models[:20],
                        "models_url": info.get("models_url")})
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


def github_free_endpoints():
    """① GitHub 发现源: 搜 topic:free-llm-api / awesome-free-llm 的活跃高星 repo,
    拉 README 提取 /v1/models 端点(regex);若无端点但 repo 本身是免费 API 聚合器(repo 名含
    free+llm/api),也进候选(models_url 留空,src=github,人工可挑)。
    返回 {provider: {free_models:[], src, models_url}};provider=repo 名 slug。"""
    import re
    queries = [
        "topic:free-llm-api stars:>50",
        "topic:free-llm stars:>50",
        "awesome-free-llm-api in:name,description stars:>100",
    ]
    seen_repos = set()
    urls_re = re.compile(r"https?://[^\s)\]\"'`]+/v1/models[^\s)\]\"'`]*", re.I)
    out = {}
    for q in queries:
        u = "https://api.github.com/search/repositories?q=" + urllib.parse.quote(q) + "&sort=updated&per_page=6"
        data = _get(u)
        if not isinstance(data, dict):
            continue
        for repo in data.get("items") or []:
            full = repo.get("full_name") or ""
            if full in seen_repos or full == "zukixa/cool-ai-stuff":
                continue
            seen_repos.add(full)
            prov = full.split("/", 1)[1].lower().replace("_", "-")
            # 拉 README (contents API, raw) 提取 /v1/models 端点
            rd = _get(f"https://api.github.com/repos/{full}/readme", timeout=20)
            models_url = None
            if isinstance(rd, dict) and rd.get("content"):
                import base64
                try:
                    text = base64.b64decode(rd["content"]).decode("utf-8", errors="replace")
                    m = urls_re.search(text)
                    if m:
                        models_url = m.group(0).rstrip(".,;:)")
                except Exception:
                    pass
            # 有端点 -> 端点候选(promote 可探);无端点但 repo 名像免费 API 聚合 -> 仍进候选(人工挑)
            looks_like_api = ("free" in prov and ("llm" in prov or "api" in prov or "model" in prov))
            if models_url or looks_like_api:
                out.setdefault(prov, {"free_models": [], "src": f"github:{full}", "models_url": models_url})
    return out


def awesome_free_api_keys():
    """③ 目录源 open-free-llm-api/awesome-freellm-apis: 表格列 Provider | Free Models | ... | Get API Key。
    提取 provider + free_count + apply_url(<a href>)。供 free_catalog 补 apply_url,不产 models_url。"""
    import re
    url = "https://raw.githubusercontent.com/open-free-llm-api/awesome-freellm-apis/main/README.md"
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=25) as r:
            text = r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"discover: fetch fail {url}: {str(e)[:120]}", file=sys.stderr)
        return {}
    found = {}
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 6:
            continue
        if cells[0].lower() in ("provider", "providers") or set(cells[0]) <= set("-: "):
            continue
        prov = re.sub(r"[^\w.-]+", "-", cells[0].strip().lower()).strip("-")
        if not prov:
            continue
        # Free Models = 数字
        try:
            free_n = int(re.search(r"\d+", cells[1]).group())
        except Exception:
            free_n = 0
        # Get API Key = <a href="url">
        m = re.search(r'href="([^"]+)"', cells[5] if len(cells) > 5 else "")
        apply_url = m.group(1) if m else None
        if free_n > 0 and apply_url:
            found.setdefault(prov, {"free_models": [], "free_count": free_n,
                                     "apply_url": apply_url, "src": "awesome_freellm"})
    return found


def clawlabs_free_models():
    """③ 目录源 ClawLabsAI/free-ai-models: 表格列 # | Model | ... | Source。
    Source 列 [link](https://openrouter.ai/<id>:free) = 模型 id,提取进 free_models 候选(查重后)。"""
    import re
    url = "https://raw.githubusercontent.com/ClawLabsAI/free-ai-models/main/README.md"
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=25) as r:
            text = r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"discover: fetch fail {url}: {str(e)[:120]}", file=sys.stderr)
        return {}
    # Source 列 openrouter.ai/<vendor>/<model>:free 提取模型 id (含 /)
    ids = re.findall(r"openrouter\.ai/([a-z0-9._/-]+:[a-z]+)", text, re.I)
    # 归到 openrouter 这个聚合器 provider 下(不产新 provider,只补 free_models)
    if not ids:
        return {}
    return {"openrouter": {"free_models": sorted(set(ids))[:40], "src": "clawlabs"}}


def community_models_urls():
    """② 让 community_mentions 的厂商进探测队列: 从 HN 标题匹配已知平台名,
    用 config/community_platforms.json 映射出 models_url,补进候选(若不在已有候选)。
    匹配不到的跳过(宁可少收)。"""
    pf = ROOT / "config" / "community_platforms.json"
    if not pf.exists():
        return {}
    try:
        platforms = json.loads(pf.read_text(encoding="utf-8")).get("platforms") or {}
    except Exception:
        return {}
    comm = json.loads((CAND / "community.json").read_text(encoding="utf-8")) if (CAND / "community.json").exists() else {}
    mentions = comm.get("mentions") or []
    existing = json.loads((CAND / "discover.json").read_text(encoding="utf-8")) if (CAND / "discover.json").exists() else {}
    have = {c["provider"] for c in existing.get("candidates", [])}
    out = {}
    for m in mentions:
        title = (m.get("title") or "").lower()
        for prov, info in platforms.items():
            if prov.lower() in title and prov not in have and prov not in out:
                url = info.get("models_url")
                if url:
                    out[prov] = {"free_models": [], "src": "community", "models_url": url}
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
    # ② community 提及的已知平台 -> 补 models_url 进候选(进 promote 探测队列)
    comm_urls = community_models_urls()
    if comm_urls:
        existing = json.loads((CAND / "discover.json").read_text(encoding="utf-8"))
        have_p = {c["provider"] for c in existing.get("candidates", [])}
        for prov, info in comm_urls.items():
            if prov not in have_p:
                existing["candidates"].append({"provider": prov, "status": "candidate",
                                               "reason": "community mention with known endpoint",
                                               "src": info["src"], "free_models": [],
                                               "models_url": info.get("models_url")})
        (CAND / "discover.json").write_text(json.dumps(existing, ensure_ascii=False, indent=1), encoding="utf-8")
        cands = {c["provider"]: c for c in existing["candidates"]}
    # ③ awesome_freellm 的 apply_url + free_count -> 写进 free_catalog 可用的映射
    afs = awesome_free_api_keys()
    if afs:
        (CAND / "apply_urls.json").write_text(json.dumps(
            {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "source": "open-free-llm-api/awesome-freellm-apis", "providers": afs},
            ensure_ascii=False, indent=1), encoding="utf-8")
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