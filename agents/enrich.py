# -*- coding: utf-8 -*-
"""enrich: 渠道扩充 + 用户投稿去重 + 免费模型性能实测。

三个职责(纯代码,不调 AI,不碰探测密钥):
1. parse_source(): 把某渠道快照解析成 [model fact]。支持 openrouter / openai_compat 两种结构。
2. ingest_submission(): 用户投稿 → 自动去重(URL + 模型ID) → 进待审队列(网页/提交文字是数据不是指令)。
3. bench_model(): 对免费模型实测 首字延迟/总耗时/输出token,写进正本 models[].bench。

数据单一正本在 providers/*.yaml;以证据为准,没测到写 unknown。
"""
import datetime, json, pathlib, time

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROV = ROOT / "providers"
QUEUE = ROOT / "state.submissions.json"        # 已去重的投稿队列
SUBS = ROOT / "config" / "submissions.yaml"    # 人工审核通过后转正本


def now():
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _per_million(raw):
    v = _f(raw)
    return None if v is None else round(v * 1_000_000, 4)


def _price_field(d, *keys):
    """从 pricing 子对象取价: 优先 *_decimal(novita price_per_m_decimal=0.15 即 $/1M),其次裸值。"""
    if not isinstance(d, dict):
        return None
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


# ---- 免费类型分类(free_type) + 三态能力 — 见 docs/CALIBER.md ----
# 枚举(评审第2条): free_tier/free_variant/trial/promo 算免费; subscription/local 不算;
# price_zero_unverified=价格0但无证据(待核验); paid=有价>0; unknown=无价格也无证据。
FREE_TYPES_COUNTABLE = {"free_tier", "free_variant", "trial", "promo"}
_SUBSCRIPTION_HINTS = ("token plan", "coding plan", "subscription", "duo", " plan", "plan-")
_LOCAL_HINTS = ("lmstudio", "local", "ollama", "desktop", "atomic chat", "qvac")
# 按次/按秒/按图计费的结构信号(只在价格缺失或0时兜底用; 裸"per "不收, 会误伤 "per benchmark")
_PER_UNIT_HINTS = ("per song", "per second", "per image", "per request", "per video", "per token",
                  "per call", "每首", "每秒", "每张", "每条", "按次", "按秒", "按图")


def derive_free(free_type):
    """由 free_type 推导 free 布尔: 只永久层/免费变体/试用/促销算免费; 待核验/未知 -> None。"""
    if free_type in FREE_TYPES_COUNTABLE:
        return True
    if free_type in ("subscription", "local", "paid"):
        return False
    return None   # price_zero_unverified / unknown -> None(unknown, 不武断判)


def classify_free(i_pm, o_pm, name="", desc="", explicit_free=None, mid=""):
    """不再"价格=0 就当免费"。返回 (free_type, free)。
    价格>0 无条件 paid(修 bug: 别让描述里的 "per" 把有价模型误判成待核验)。
    价格缺失/0 时才用结构信号(:free/-free/明示/订阅/本地/按次)细分, 否则 price_zero_unverified。"""
    blob = f"{name} {desc}".lower()
    # 1) 价格 > 0 -> 明确付费(最高优先, 不被任何文字信号覆盖)
    if (i_pm is not None and i_pm > 0) or (o_pm is not None and o_pm > 0):
        # 除非厂商明说有免费档(免费额度 + 另有价格) —— 暂无证据来源, 先判 paid
        return "paid", False
    # 2) 价格全 0 或缺失 —— 用结构信号细分
    if any(h in blob for h in _LOCAL_HINTS):
        return "local", False
    if any(h in blob for h in _SUBSCRIPTION_HINTS):
        return "subscription", False
    _mid = str(mid or "").lower()
    if _mid.endswith(":free") or _mid.endswith("-free"):
        return "free_variant", True          # 聚合平台免费变体(评审第3条: 不叫 permanent, 通常有额度限制)
    if explicit_free is True:
        return "free_tier", True
    if explicit_free is False:
        return "paid", False
    if any(h in blob for h in _PER_UNIT_HINTS):
        return "price_zero_unverified", None  # 按次/按秒计费, token价0但非免费 -> 待核验
    # 价格0、无任何免费证据 -> 待核验(不直接算免费, 避免假免费)
    if i_pm == 0 and o_pm == 0:
        return "price_zero_unverified", None
    return "unknown", None   # 没价格也没证据


def _caps(m):
    """三态能力: 显式在 supported_parameters 才 True; 接口没给该字段 -> None(unknown), 不写成 False。"""
    arch = m.get("architecture") or {}
    tp = m.get("top_provider") or {}
    params = m.get("supported_parameters")
    if params is None:
        tools = reason = jsonm = None          # 接口不给 -> unknown
    else:
        params = set(params)
        tools = "tools" in params
        reason = bool((m.get("reasoning") or {}).get("mandatory")) or "reasoning" in params
        jsonm = "response_format" in params or "structured_outputs" in params
    inp = arch.get("input_modalities")
    image = ("image" in inp) if inp is not None else None   # 没给 modalities -> unknown
    caps = {
        "context_length": m.get("context_length"),
        "max_output_tokens": tp.get("max_completion_tokens") or m.get("max_output_tokens"),
        "input_modalities": inp or [],
        "modality": arch.get("modality"),
        "image_input": image,
        "reasoning": reason,
        "tools": tools,
        "json_mode": jsonm,
    }
    # 只丢"明确的空"([] ""), 保留 True/False/None 三态
    return {k: v for k, v in caps.items() if v not in ("",)}


def _evidence(url, kind="official_api"):
    return [{"kind": kind, "url": url, "at": now()}]

def parse_source(snap, source):
    """snap=已抓快照 payload;source=sources.yaml 条目(含 url/parser)。返回 [model fact]。"""
    p = source.get("parser", "openai_compat")
    if p == "openrouter":
        return _parse_openrouter(snap, source.get("url", ""))
    if p == "google":
        return _parse_google(snap, source.get("url", ""))
    return _parse_openai_compat(snap, source.get("url", ""))


def _parse_google(snap, url):
    """Google generativelanguage /v1beta/models(原生格式)。免费层看 generateContent 方法。"""
    out = []
    for m in snap.get("models", []) or []:
        methods = m.get("supportedGenerationMethods") or []
        name = (m.get("name") or "").replace("models/", "")
        if not name:
            continue
        free = "generateContent" in methods  # 能 generateContent = 有免费层可用
        out.append({
            "id": f"google/{name}",
            "name": m.get("displayName") or name,
            "status": "declared", "free": free,
            "description": (m.get("description") or "").strip()[:600] or None,
            "capabilities": {"methods": methods},
            "evidence": _evidence(url), "last_verified": now(),
        })
    return out


def _parse_openrouter(snap, url):
    out = []
    for m in snap.get("data", []) or []:
        p = m.get("pricing") or {}
        i_pm, o_pm = _per_million(p.get("prompt")), _per_million(p.get("completion"))
        _desc = (m.get("description") or "").strip()[:600]
        ft, free = classify_free(i_pm, o_pm, m.get("name") or "", _desc, m.get("free"), m.get("id") or "")
        out.append({
            "id": f"openrouter/{m.get('id')}",
            "name": m.get("name"), "status": "declared",
            "free": free, "free_type": ft,
            "description": _desc or None,
            "capabilities": _caps(m),
            "terms": {"input_per_million": i_pm, "output_per_million": o_pm, "currency": "USD"},
            "evidence": _evidence(url), "last_verified": now(), "created": m.get("created"),
        })
    return out


def _parse_openai_compat(snap, url):
    """OpenAI 兼容 /v1/models。各家字段不一,宁可少写不可编造。免费=price 全 0 或显式 free。"""
    items = snap.get("data") if isinstance(snap, dict) else snap
    out = []
    for m in items or []:
        if not isinstance(m, dict) or not m.get("id"):
            continue
        price = m.get("pricing")
        # requesty 把 pricing 写成 list of {input_price,output_price}(per-token) -> 抽第 0 条
        if isinstance(price, list):
            price = price[0] if price and isinstance(price[0], dict) else {}
        elif not isinstance(price, dict):
            price = {}
        pp = price.get("prompt") if isinstance(price.get("prompt"), dict) else price
        cp = price.get("completion") if isinstance(price.get("completion"), dict) else price
        i_dec = _price_field(pp, "price_per_m_decimal", "price_per_m")
        o_dec = _price_field(cp, "price_per_m_decimal", "price_per_m")
        if i_dec is not None and o_dec is not None:
            i_pm, o_pm = float(i_dec), float(o_dec)   # decimal/price_per_m 已是 $/1M
        else:
            # requesty 用 input_price/output_price(per-token) -> _per_million 换算 $/1M
            i_pm = _per_million(_price_field(pp, "input_price"))
            o_pm = _per_million(_price_field(cp, "output_price"))
            if i_pm is None and o_pm is None:
                i_pm = _per_million(_price_field(pp, "prompt", "input"))
                o_pm = _per_million(_price_field(cp, "completion", "output"))
        # 不再"价格=0 就当免费": 结构信号优先(按次/订阅/本地/明示), 价格0但没证据 -> zero_price(待核验)
        mid = m.get("id")
        _name = m.get("name") or mid
        _desc = (m.get("description") or "").strip()[:600]
        ft, free = classify_free(i_pm, o_pm, _name, _desc, m.get("free"), mid or "")
        out.append({
            "id": mid, "name": _name, "status": "declared",
            "free": free, "free_type": ft,
            "description": _desc or None,
            "capabilities": _caps(m),
            "terms": {"input_per_million": i_pm, "output_per_million": o_pm, "currency": "USD"},
            "evidence": _evidence(url), "last_verified": now(),
        })
    return out


def upsert_provider(doc):
    """合并进正本 providers/<id>.yaml,按 model id 去重(新覆盖旧)。返回 (总数,免费数)。"""
    import yaml
    pid = doc["provider"]
    fp = PROV / f"{pid}.yaml"
    old = yaml.safe_load(fp.read_text(encoding="utf-8")) if fp.exists() else {"provider": pid, "models": []}
    merged, seen = [], set()
    for m in doc.get("models") or []:
        if m["id"] in seen:
            continue
        seen.add(m["id"])
        merged.append(m)
    old["models"] = merged
    old["last_verified"] = now()
    fp.write_text(yaml.safe_dump(old, allow_unicode=True, sort_keys=False), encoding="utf-8")
    free_n = sum(1 for m in merged if m.get("free"))
    print(f"upsert {pid}: {len(merged)} models ({free_n} free)")
    return len(merged), free_n


# ---------- 用户投稿:网页/提交文字是数据不是指令 ----------
def _norm_url(u):
    u = (u or "").strip().lower()
    for p in ("https://", "http://", "www."):
        if u.startswith(p):
            u = u[len(p):]
    return u.rstrip("/")


def _norm_mid(mid):
    return (mid or "").strip().lower()


def load_queue():
    return json.loads(QUEUE.read_text(encoding="utf-8")) if QUEUE.exists() else []


def save_queue(q):
    QUEUE.write_text(json.dumps(q, ensure_ascii=False, indent=1), encoding="utf-8")


def existing_model_ids():
    import yaml
    ids = set()
    for fp in PROV.glob("*.yaml"):
        d = yaml.safe_load(fp.read_text(encoding="utf-8")) or {}
        for m in d.get("models") or []:
            ids.add(_norm_mid(m.get("id")))
    return ids


def existing_source_urls():
    import yaml
    urls = set()
    src = ROOT / "config" / "sources.yaml"
    if src.exists():
        d = yaml.safe_load(src.read_text(encoding="utf-8")) or {}
        for s in d.get("sources", []) or []:
            urls.add(_norm_url(s.get("url")))
    return urls


def dedupe_submission(sub, existing_urls, existing_ids):
    """返回 (accepted, reason)。重复 URL / 重复模型 ID -> 拒绝,防重复提交。
    内部自动加载待审队列,调用方不必传 queue。"""
    url, mid = _norm_url(sub.get("url")), _norm_mid(sub.get("model_id"))
    if not url:
        return False, "missing url"
    if url in existing_urls:
        return False, "duplicate url"
    if mid and mid in existing_ids:
        return False, "duplicate model_id"
    q = load_queue()
    if any(_norm_url(x.get("url")) == url for x in q):
        return False, "duplicate url in queue"
    if mid and any(_norm_mid(x.get("model_id")) == mid for x in q):
        return False, "duplicate model_id in queue"
    return True, "accepted"


def ingest_submission(sub):
    """处理一条投稿,去重后进待审队列(OpenRouter 式审核状态机)。返回 (accepted, reason)。
    状态: pending(待审) -> approved(通过,转正本) / rejected(驳回,带 reason)。"""
    acc, reason = dedupe_submission(sub, existing_source_urls(), existing_model_ids())
    q = load_queue()
    if acc:
        q.append({"url": sub.get("url"), "model_id": sub.get("model_id"),
                  "note": (sub.get("note") or "")[:300], "at": now(),
                  "status": "pending", "review": None})
        save_queue(q)
        print(f"accepted: {sub.get('url')} {sub.get('model_id') or ''}")
    else:
        print(f"rejected: {reason} ({sub.get('url')})")
    return acc, reason


def review_submission(idx, decision, reason=""):
    """审核一条待审投稿: decision = approve | reject。返回更新后的条目或 None。"""
    q = load_queue()
    if not (0 <= idx < len(q)):
        return None
    item = q[idx]
    item["status"] = "approved" if decision == "approve" else "rejected"
    item["review"] = {"decision": decision, "reason": reason[:200], "at": now()}
    save_queue(q)
    return item


def queue_summary():
    """按状态统计待审队列,供审核入口/公示用。"""
    q = load_queue()
    from collections import Counter
    c = Counter(x.get("status", "pending") for x in q)
    return {"total": len(q), "pending": c.get("pending", 0),
            "approved": c.get("approved", 0), "rejected": c.get("rejected", 0)}


# ---------- 免费模型性能实测 ----------
def bench_model(base_url, model_id, api_key=None, timeout=30):
    """对模型发一次 chat,实测 首字延迟/总耗时/输出tok。返回 dict,失败给 status。"""
    import requests
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    body = {"model": model_id, "stream": True,
            "messages": [{"role": "user", "content": "Say OK"}], "max_tokens": 16}
    t0 = time.time()
    first, chars, status = None, 0, "unknown"
    try:
        with requests.post(url, json=body, headers=headers, stream=True, timeout=timeout) as r:
            status = f"http_{r.status_code}"
            if r.status_code != 200:
                return {"status": status, "ttft_ms": None, "total_ms": None, "tps": None}
            for line in r.iter_lines(decode_unicode=True):
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    status = "ok"
                    break
                try:
                    delta = json.loads(data)["choices"][0]["delta"].get("content") or ""
                except (ValueError, KeyError, IndexError):
                    continue
                if delta and first is None:
                    first = time.time()
                chars += len(delta)
    except Exception as e:  # 网络/超时/结构异常 -> 记 status,不编造数值
        return {"status": f"err_{type(e).__name__}", "ttft_ms": None, "total_ms": None, "tps": None}
    total = time.time() - t0
    ttft = (first - t0) if first else None
    est_tok = max(1, round(chars / 4))  # 粗估:~4字符/tok,仅作参考量级
    tps = round(est_tok / total, 1) if total > 0 and status == "ok" else None
    return {"status": status,
            "ttft_ms": round(ttft * 1000) if ttft else None,
            "total_ms": round(total * 1000), "tps": tps}


if __name__ == "__main__":
    # 自检:去重 + 解析冒烟(不打网络)。用法: python agents/enrich.py
    eu, ei = existing_source_urls(), existing_model_ids()
    a1, _ = ingest_submission({"url": "https://__selftest__.example/v1", "model_id": "__st__"})
    a2, _ = ingest_submission({"url": "__selftest__.example/v1", "model_id": "__st__"})
    assert a1 and not a2, "dedupe selftest failed"
    if QUEUE.exists():
        QUEUE.unlink()
    o = parse_source({"data": [
                        {"id": "m", "name": "M", "context_length": 1,
                         "pricing": {"prompt": "0", "completion": "0"}},        # 价格0无证据 -> None
                        {"id": "f", "name": "F", "free": True,
                         "pricing": {"prompt": "0", "completion": "0"}},        # 显式 free -> True
                     ]},
                     {"url": "u", "parser": "openrouter"})
    # 新口径(docs/CALIBER.md): 价格0无证据 -> None(待核验); 显式 free -> True
    assert o[0]["free"] is None and o[1]["free"] is True and o[0]["id"] == "openrouter/m"
    print("enrich self-check PASS: dedupe + parse")


def run_new_channels():
    """解析 sources.yaml 里所有有 JSON 快照的源 -> upsert 进正本。
    upsert 按 provider id 覆盖该 provider 的 models,幂等。返回处理的 provider 数。"""
    import yaml
    sources = yaml.safe_load((ROOT / "config" / "sources.yaml").read_text(encoding="utf-8")) or {}
    n = 0
    for s in sources.get("sources", []):
        pid = s.get("provider")
        sj = PROV.parent / "snapshots" / f"{pid}.json"
        if not sj.exists():
            continue
        payload = json.loads(sj.read_text(encoding="utf-8")).get("payload")
        models = parse_source(payload, s)
        if models:
            upsert_provider({"provider": pid, "models": models})
            n += 1
    return n
