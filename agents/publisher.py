# -*- coding: utf-8 -*-
"""发布员:由正本生成产物(docs/free-models.json、README 表格、docs/index.html),
再推送 Telegram 变更摘要。唯一能写通知令牌的智能体;不读探测密钥。"""
import argparse, datetime, html, json, os, pathlib, sys, time
import requests, yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROV = ROOT / "providers"
DOCS = ROOT / "docs"
STATE = ROOT / "state.local"


def load_all():
    rows = []
    for fp in sorted(PROV.glob("*.yaml")):
        rows.append(yaml.safe_load(fp.read_text(encoding="utf-8")))
    return rows


def flat(rows):
    out = []
    for r in rows:
        for m in r.get("models") or []:
            out.append({"id": m.get("id"), "provider": r["provider"], "status": m.get("status"),
                        "free": m.get("free"), "last_verified": r.get("last_verified"),
                        "pricing_url": r.get("pricing_url")})
    return out


def render_readme(rows):
    lines = ["# free-ai-radar", "",
             "免费AI情报汇聚智能体 — 每条事实带来源与验证时间,无证据写 unknown。",
             "", "| 厂商 | 模型数 | 已收录模型 | 最后验证 | 说明 |", "| --- | --- | --- | --- | --- |"]
    for r in rows:
        ids = ", ".join(m.get("id", "?") for m in (r.get("models") or [])) or "(待采集员首轮抓取)"
        lines.append(f"| {r['provider']} | {len(r.get('models') or [])} | {ids} | {r.get('last_verified')} | {r.get('pricing_url', '')} |")
    lines += ["", "数据正本: `providers/*.yaml`。生成时间: " + time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), ""]
    return "\n".join(lines)


def render_site(rows):
    cards = []
    for r in rows:
        li = "".join(f"<li>{html.escape(m.get('id','?'))} <span class='s'>{m.get('status','')}</span></li>"
                     for m in (r.get("models") or [])) or "<li class='s'>待采集员首轮抓取</li>"
        cards.append(f"<div class='card'><h3>{html.escape(r['provider'])}</h3><ul>{li}</ul>"
                     f"<a href='{r.get('pricing_url','')}'>定价页</a> · 最后验证 {r.get('last_verified')}</div>")
    return f"""<!doctype html><meta charset=utf-8><title>free-ai-radar</title>
<style>body{{font:15px/1.6 system-ui;max-width:960px;margin:2rem auto;padding:0 1rem}}
.card{{border:1px solid #ddd;border-radius:8px;padding:1rem;margin:.6rem 0}}
.s{{color:#666;font-size:.85em}}</style>
<h1>free-ai-radar</h1><p>哪些 AI 模型现在免费 — 每条事实带证据与验证时间。</p>
{''.join(cards)}"""


def telegram(msg):
    tok = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not tok or not chat:
        print("telegram: no token/chat configured, skip notify")
        return None  # 未配置 = 跳过,不算失败
    r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                      json={"chat_id": chat, "text": msg, "parse_mode": "HTML"}, timeout=20)
    ok = r.status_code == 200
    print(f"telegram: http {r.status_code}")
    return ok


def events_path():
    return ROOT / "state.changes.json"


def main(argv=None):
    ap = argparse.ArgumentParser(description="发布员")
    ap.add_argument("--notify", action="store_true", help="有变更事件时推送 Telegram")
    ap.add_argument("--message", help="直接推送这条消息(重大变化人审后用)")
    args = ap.parse_args(argv)
    rows = load_all()
    DOCS.mkdir(exist_ok=True)
    (DOCS / "free-models.json").write_text(
        json.dumps({"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "models": flat(rows), "providers": len(rows)},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    (DOCS / "index.html").write_text(render_site(rows), encoding="utf-8")
    (ROOT / "README.md").write_text(render_readme(rows), encoding="utf-8")
    print(f"publisher: wrote docs/free-models.json, docs/index.html, README.md ({len(rows)} providers)")

    if args.message:
        r = telegram(args.message)
        return 0 if r in (True, None) else 1  # None=skip, not fail
    if args.notify:
        ev_p = events_path()
        events = json.loads(ev_p.read_text(encoding="utf-8")) if ev_p.exists() else []
        if not events:
            print("publisher: no changes, no notify")
            return 0
        lines = [f"📡 free-ai-radar 检测到 {len(events)} 处变化:"]
        for e in events[:10]:
            lines.append(f"- {e['provider']}: {e['type']} 变化 <a href='{e['url']}'>来源</a>")
        r = telegram("\n".join(lines))
        return 0 if r in (True, None) else 1  # None=skip, not fail
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
