# -*- coding: utf-8 -*-
"""免费模型总目录(方案外的展示层): 把"确认有免费模型的厂商"列成目录,附去申请 key 的入口。
不采集要 key 的平台数据 —— 只列"哪些厂商有免费模型"+ 申请链接,让用户自己去厂商处申请。
数据源: models.dev(标了 env=需哪些 key + doc=文档/定价页) + 正本 providers/*.yaml(已收录的)。
纯代码,不调 AI,不碰密钥。
"""
import json, sys, pathlib, time
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from discover import _get, REF_DIRS, load_canonical_providers

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROV = ROOT / "providers"
DOCS = ROOT / "docs"


def canonical_free():
    """已正本收录的厂商 -> (名字, 免费模型数, 申请链接=signup/homepage)。"""
    out = {}
    for f in sorted(PROV.glob("*.yaml")):
        d = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        pid = d.get("provider") or f.stem
        ms = d.get("models") or []
        free = [m for m in ms if m.get("free")]
        if not free:
            continue
        su = d.get("signup") or {}
        link = su.get("url") or d.get("homepage") or d.get("pricing_url") or ""
        out[pid] = {"provider": pid, "name": pid, "free_count": len(free),
                    "sample_models": [m["id"] for m in free[:6]],
                    "apply_url": link or None, "status": "live",
                    "note": "已收录,直接可看"}
    return out


def candidate_free():
    """候选(有免费层但没采到数据) -> 列出来 + 申请链接=models.dev doc。用户自己去申请 key。"""
    md = _get(REF_DIRS["models_dev"]) or {}
    have = load_canonical_providers()
    cands = json.loads((ROOT / "candidates" / "discover.json").read_text(encoding="utf-8")) \
        .get("candidates", [])
    out = {}
    for c in cands:
        p = c.get("provider")
        if not p or p in have:
            continue
        info = md.get(p) or {}
        env = info.get("env") or []
        doc = info.get("doc") or None
        name = info.get("name") or p
        free = c.get("free_models") or []
        if not free:
            continue
        out[p] = {"provider": p, "name": name, "free_count": len(free),
                  "sample_models": free[:6],
                  "apply_url": doc, "status": "apply_key",
                  "needs_env": env,
                  "note": "有免费模型;需自行到厂商申请 key" if env else "有免费模型"}
    return out


def build_catalog():
    live = canonical_free()
    apply = candidate_free()
    all_rows = list(live.values()) + list(apply.values())
    all_rows.sort(key=lambda r: (-r["free_count"], r["provider"]))
    cat = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "live_count": len(live), "apply_count": len(apply),
           "total_free_models": sum(r["free_count"] for r in all_rows),
           "vendors": all_rows}
    (DOCS / "free-catalog.json").write_text(
        json.dumps(cat, ensure_ascii=False, indent=1), encoding="utf-8")
    return cat


def main(argv=None):
    cat = build_catalog()
    print(f"free-catalog: {cat['live_count']} live + {cat['apply_count']} apply-key "
          f"= {cat['live_count'] + cat['apply_count']} vendors, "
          f"{cat['total_free_models']} free models total")
    for r in cat["vendors"][:12]:
        print(f"  [{r['status']:9}] {r['name'][:26]:26} {r['free_count']:3} free  "
              f"{(r.get('apply_url') or '(no link)')[:40]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())