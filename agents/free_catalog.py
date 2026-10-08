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


def _link_kind(url):
    """诚实分类链接真实去向(不冒充): signup=注册口, console/platform=控制台(通常含注册),
    doc/help=文档, homepage=官网。models.dev 只给 doc,多数是文档 -> 不叫'去申请KEY'。"""
    if not url:
        return None
    u = url.lower()
    path = u.split("?", 1)[0]
    host = path.split("/")[2] if path.startswith("http") and path.count("/") >= 2 else ""
    # 路径优先: 明确的注册口/文档路径最可信
    if any(k in path for k in ("/signup", "/sign-up", "/register", "/join", "/login", "/auth/login")):
        return "signup"
    if any(k in path for k in ("/docs", "/help", "/doc/")) or path.rstrip("/").endswith("/docs") or "docs." in host:
        return "doc"
    if "/pricing" in path:
        return "pricing"
    # 无明确路径 -> 看 host 是不是控制台/平台域名(通常含注册)
    if any(h in host for h in ("console.", "platform.", "dashboard.", "app.")):
        return "console"
    return "homepage"


_KIND_LABEL = {
    "signup": ("去注册", "真注册入口(curl 已验证)"),
    "console": ("去控制台", "控制台/平台,通常可注册领key"),
    "doc": ("查官方文档", "帮助文档(页内通常有 Get API key 入口)"),
    "pricing": ("看定价页", "定价/免费额度说明"),
    "homepage": ("去官网", "厂商官网(找注册/控制台入口)"),
}

# 已验证真注册口(config/signup_urls.json): curl 200 + body 含注册特征 + 同品牌核验过。
# 这些优先于 models.dev 的 doc 链接(那是文档不是注册口)。
def _verified_signups():
    p = ROOT / "config" / "signup_urls.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def canonical_free():
    """已正本收录的厂商 -> 申请链接=正本 signup/homepage(已实测真注册口)。"""
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
        kind = _link_kind(link) or "homepage"
        out[pid] = {"provider": pid, "name": pid, "free_count": len(free),
                    "sample_models": [m["id"] for m in free[:6]],
                    "apply_url": link or None, "link_kind": kind,
                    "btn": _KIND_LABEL[kind][0],
                    "status": "live",
                    "note": "已收录,直接可看"}
    return out


def candidate_free():
    """候选(有免费层但没采到数据) -> 链接=models.dev doc, 但诚实标注它是文档不是注册口。"""
    md = _get(REF_DIRS["models_dev"]) or {}
    have = load_canonical_providers()
    verified = _verified_signups()
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
        # 有已验证真注册口 -> 优先用它(kind=signup, btn=去注册);否则用 doc(诚实标注)
        link = verified.get(p) or doc
        kind = _link_kind(link) or "doc"
        out[p] = {"provider": p, "name": name, "free_count": len(free),
                  "sample_models": free[:6],
                  "apply_url": link, "link_kind": kind,
                  "btn": _KIND_LABEL[kind][0],
                  "status": "apply_key",
                  "needs_env": env,
                  "note": _KIND_LABEL[kind][1]}
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