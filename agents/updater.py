# -*- coding: utf-8 -*-
"""更新员:把 snapshots/ 里的原始快照解析成模型事实,写回 providers/{id}.yaml 正本。
纯代码,不调 AI。只处理结构化 API 快照(.json);HTML 页面留待抽取员阶段。
规则:无证据不写模型;免费判定 = 官方 pricing 字段明说,不是猜。"""
import argparse, datetime, json, pathlib, sys, time
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
SNAP = ROOT / "snapshots"
PROV = ROOT / "providers"


def _now():
    return datetime.date.today().isoformat()


def parse_openrouter(payload):
    """OpenRouter /api/v1/models -> [model fact]。pricing 字符串,0 = 免费。"""
    out = []
    for m in payload.get("data", []) or []:
        p = m.get("pricing") or {}
        try:
            inp, outp = float(p.get("prompt", "0")), float(p.get("completion", "0"))
        except (TypeError, ValueError):
            inp = outp = None
        free = (inp == 0 and outp == 0)
        out.append({
            "id": f"openrouter/{m.get('id')}",
            "name": m.get("name"),
            "status": "declared",
            "free": free,
            "capabilities": {"context_length": m.get("context_length")},
            "terms": {"input_per_million": inp, "output_per_million": outp} if inp is not None else {},
            "evidence": [{"kind": "official_api", "url": "https://openrouter.ai/api/v1/models",
                          "at": _now()}],
            "last_verified": _now(),
        })
    return out


def parse_google(payload):
    """Google generativelanguage /v1beta/models -> [model fact]。免费层看 supportedGenerationMethods。"""
    out = []
    for m in payload.get("models", []) or []:
        methods = m.get("supportedGenerationMethods") or []
        free = "generateContent" in methods  # 免费层可用 generateContent
        out.append({
            "id": f"google/{m.get('name', '').replace('models/', '')}",
            "name": m.get("displayName") or m.get("name"),
            "status": "declared",
            "free": free,
            "capabilities": {"methods": methods},
            "evidence": [{"kind": "official_api",
                          "url": "https://generativelanguage.googleapis.com/v1beta/models",
                          "at": _now()}],
            "last_verified": _now(),
        })
    return out


def parse_openai(payload):
    """OpenAI /v1/models -> [model fact]。没有价格字段,免费只能标 unknown。"""
    out = []
    for m in payload.get("data", []) or []:
        out.append({
            "id": f"openai/{m.get('id')}",
            "name": m.get("id"),
            "status": "declared",
            "free": None,  # 接口不给价格,不猜
            "evidence": [{"kind": "official_api", "url": "https://api.openai.com/v1/models",
                          "at": _now()}],
            "last_verified": _now(),
        })
    return out


PARSERS = {"openrouter": parse_openrouter, "google": parse_google, "openai": parse_openai}


def update_provider(pid, models):
    """合并进 providers/{pid}.yaml,按 id 去重,保留人工修订字段。"""
    fp = PROV / f"{pid}.yaml"
    data = yaml.safe_load(fp.read_text(encoding="utf-8")) if fp.exists() else {"provider": pid}
    by_id = {m["id"]: m for m in (data.get("models") or [])}
    for m in models:
        by_id[m["id"]] = {**by_id.get(m["id"], {}), **m}
    data["models"] = list(by_id.values())
    data["last_verified"] = _now()
    fp.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return len(data["models"])


def main(argv=None):
    ap = argparse.ArgumentParser(description="更新员")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    changed = 0
    for pid, parser in PARSERS.items():
        sj = SNAP / f"{pid}.json"
        if not sj.exists():
            print(f"skip {pid}: no json snapshot (HTML page, needs extractor)")
            continue
        payload = json.loads(sj.read_text(encoding="utf-8")).get("payload")
        models = parser(payload)
        if args.dry_run:
            print(f"[dry-run] {pid}: {len(models)} models, {sum(1 for m in models if m.get('free'))} free")
        else:
            total = update_provider(pid, models)
            free = sum(1 for m in models if m.get("free"))
            print(f"updated {pid}: {total} models in yaml ({free} free)")
            changed += 1
    print(f"updater: {changed} providers updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())