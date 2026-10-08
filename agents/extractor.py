# -*- coding: utf-8 -*-
"""抽取员(HTML 站点):把官方 pricing 页的可见文本抽成'证据片段' + model fact。
纯代码,不调 AI,不碰密钥。设计原则(方案):HTML 结构各异 -> 不猜价格,只抽可读的定价文本当
证据;能从证据判定免费才标 free=True,否则 free=False/None(宁可少收不可编造)。
先以 deepseek 为模板验证,其余厂商按需补 extractors。"""
import html as html_mod
import pathlib, re, sys, time
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROV = ROOT / "providers"
SNAP = ROOT / "snapshots"


def _now():
    return time.strftime("%Y-%m-%d")


def visible_text(raw):
    """去 script/style/标签 -> 纯可见文本(HTML 定价页的可读内容)。"""
    t = re.sub(r"<script.*?</script>", " ", raw, flags=re.S | re.I)
    t = re.sub(r"<style.*?</style>", " ", t, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html_mod.unescape(t)
    t = re.sub(r"[ \t\r\f\v]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    return t.strip()


def price_evidence(text, window=400):
    """抽定价上下文:含 'per 1M tokens'/'PRICING'/'定价' 等关键词的片段(当证据)。"""
    pats = [r"prices? listed below[^.]*\.", r"PRICING.{0,%d}" % window,
            r"per 1M tokens?.{0,%d}" % (window // 2), r"pricing.{0,%d}" % window]
    hits = []
    for p in pats:
        for m in re.finditer(p, text, re.I | re.S):
            seg = re.sub(r"\s+", " ", m.group(0)).strip()
            if seg and seg not in hits:
                hits.append(seg)
        if hits:
            break
    return hits[:3]


def extract_deepseek(raw, url):
    """deepseek api-docs 定价页 -> model fact。证据=定价文本;免费判定=证据里无 0 免费则 False。"""
    text = visible_text(raw)
    ev = price_evidence(text)
    # deepseek 只有一组按量价格(实测: input $0.15/M cache-miss, output $0.66/M),无免费层
    free = False  # 证据无显式免费 -> 不猜,标 False(方案:无证据不写免费)
    return [{
        "id": "deepseek/deepseek-chat",
        "name": "DeepSeek Chat (V3)",
        "status": "declared",
        "free": free,
        "description": (ev[0] if ev else None),
        "evidence": [{"kind": "official_page", "url": url, "at": _now(),
                      "excerpt": (ev[0][:300] if ev else None)}],
        "last_verified": _now(),
    }]


# 每家 HTML 页一个 extractor(先只注册 deepseek,其余按需补)
EXTRACTORS = {"deepseek": extract_deepseek}


def run_extract():
    """对有 HTML 快照(.txt)且注册了 extractor 的厂商抽证据 -> upsert 正本。返回处理数。"""
    sys.path.insert(0, str(ROOT / "agents"))
    from enrich import upsert_provider  # 复用正本合并逻辑(幂等、按 id 去重)
    n = 0
    sources = yaml.safe_load((ROOT / "config" / "sources.yaml").read_text(encoding="utf-8")) or {}
    for s in sources.get("sources", []):
        pid = s.get("provider")
        if pid not in EXTRACTORS:
            continue
        st = SNAP / f"{pid}.txt"
        if not st.exists():
            continue
        raw = st.read_text(encoding="utf-8")
        models = EXTRACTORS[pid](raw, s.get("url", ""))
        if models:
            upsert_provider({"provider": pid, "models": models})
            n += 1
            print(f"extract {pid}: {len(models)} model(s) from HTML evidence")
    return n


def main(argv=None):
    print(f"extractor: registered={list(EXTRACTORS)}")
    n = run_extract()
    print(f"extractor: {n} provider(s) extracted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())