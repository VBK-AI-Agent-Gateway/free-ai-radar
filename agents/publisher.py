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
            caps = m.get("capabilities") or {}
            terms = m.get("terms") or {}
            out.append({
                "id": m.get("id"), "name": m.get("name"), "provider": r["provider"],
                "status": m.get("status"), "free": m.get("free"),
                "description": m.get("description"),
                "context_length": caps.get("context_length"),
                "max_output_tokens": caps.get("max_output_tokens"),
                "input_per_million": terms.get("input_per_million"),
                "output_per_million": terms.get("output_per_million"),
                "image_input": bool(caps.get("image_input")),
                "reasoning": bool(caps.get("reasoning")),
                "tools": bool(caps.get("tools")),
                "json_mode": bool(caps.get("json_mode")),
                "created": m.get("created"),
                "last_verified": r.get("last_verified"), "pricing_url": r.get("pricing_url"),
            })
    return out


def render_readme(rows):
    lines = ["# free-ai-radar", "",
             "免费AI情报汇聚智能体 — 每条事实带来源与验证时间,无证据写 unknown。", "",
             "| 厂商 | 模型数 | 已收录模型 | 最后验证 | 说明 |", "| --- | --- | --- | --- | --- |"]
    for r in rows:
        ids = ", ".join(m.get("id", "?") for m in (r.get("models") or [])) or "(待采集员首轮抓取)"
        lines.append(f"| {r['provider']} | {len(r.get('models') or [])} | {ids} | {r.get('last_verified')} | {r.get('pricing_url', '')} |")
    lines += ["", "数据正本: `providers/*.yaml`。生成时间: " + time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), ""]
    return "\n".join(lines)


SITE_TEMPLATE = r"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>free-ai-radar - 免费AI模型清单</title>
<style>
*{box-sizing:border-box} body{font:15px/1.55 -apple-system,Segoe UI,system-ui,sans-serif;margin:0;background:#0d1117;color:#c9d1d9}
.wrap{max-width:1080px;margin:0 auto;padding:20px 16px}
header h1{font-size:22px;margin:0 0 4px;color:#e6edf3} .sub{color:#8b949e;font-size:13px}
.stats{display:flex;gap:16px;margin:14px 0;flex-wrap:wrap}
.stat{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:8px 16px}
.stat b{display:block;font-size:20px;color:#e6edf3} .stat span{font-size:12px;color:#8b949e}
.controls{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0}
input[type=search],select{background:#161b22;border:1px solid #30363d;color:#c9d1d9;padding:8px 10px;border-radius:6px;font-size:14px}
input[type=search]{flex:1;min-width:200px} select{cursor:pointer}
label.toggle{display:flex;align-items:center;gap:6px;background:#161b22;border:1px solid #30363d;padding:8px 12px;border-radius:6px;cursor:pointer;font-size:14px}
.chips{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px}
.chip{background:#1f6feb33;border:1px solid #1f6feb;color:#79c0ff;border-radius:20px;padding:3px 10px;font-size:12px;cursor:pointer;user-select:none}
.chip.on{background:#1f6feb;color:#fff}
.card{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:14px 16px;margin:10px 0}
.card.free{border-color:#238636;box-shadow:0 0 0 1px #23863644}
.top{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:baseline}
.nm{font-weight:600;color:#e6edf3;font-size:15px} .nid{color:#8b949e;font-size:12px;font-family:ui-monospace,monospace}
.badge{font-size:11px;padding:3px 9px;border-radius:10px;white-space:nowrap}
.badge.free{background:#238636;color:#fff} .badge.paid{background:#30363d;color:#8b949e}
.desc{color:#a5adb6;font-size:13px;margin:8px 0}
.meta{display:flex;gap:14px;flex-wrap:wrap;font-size:12.5px;color:#8b949e;margin-top:8px}
.meta b{color:#c9d1d9;font-weight:600}
.tags{display:flex;gap:5px;flex-wrap:wrap;margin-top:8px}
.tag{font-size:11px;background:#21262d;border:1px solid #30363d;color:#8b949e;padding:1px 7px;border-radius:4px}
.tag.y{border-color:#d29922;color:#e3b341}
a{color:#58a6ff;text-decoration:none} a:hover{text-decoration:underline}
.empty{color:#8b949e;text-align:center;padding:30px}
footer{color:#484f58;font-size:12px;margin-top:24px;text-align:center}
code{background:#21262d;padding:1px 5px;border-radius:4px}
</style></head><body><div class="wrap">
<header><h1>&#128269; free-ai-radar &mdash; 免费AI模型清单</h1>
<div class="sub">每条事实带来源与验证时间 &middot; 数据正本 <code>providers/*.yaml</code> &middot; 更新 __GEN__</div></header>
<div class="stats">
<div class="stat"><b>__TOTAL__</b><span>模型总数</span></div>
<div class="stat"><b>__FREE__</b><span>免费模型</span></div>
<div class="stat"><b>__PROV__</b><span>厂商</span></div>
</div>
<div class="controls">
<input type="search" id="q" placeholder="搜模型名 / 描述 / 厂商...">
<label class="toggle"><input type="checkbox" id="onlyfree"> 只看免费</label>
<select id="sort">
<option value="free">排序: 免费优先</option>
<option value="ctx">排序: 上下文最大</option>
<option value="price">排序: 价格最低</option>
<option value="new">排序: 最新收录</option>
</select>
</div>
<div class="chips" id="chips">
<span class="chip" data-f="image_input">图像输入</span>
<span class="chip" data-f="reasoning">推理</span>
<span class="chip" data-f="tools">工具调用</span>
<span class="chip" data-f="json_mode">JSON输出</span>
</div>
<div id="list"></div>
<footer>数据来源: 官方API/页面, 证据见 <code>providers/*.yaml</code> &middot; 无证据写 unknown, 不猜</footer>
</div>
<script>
const MODELS = __DATA__;
const esc = s => (s==null?"":String(s)).replace(/[&<>"]/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const fmtCtx = n => !n?"-":n>=1e6?(n/1e6).toFixed(0)+"M":n>=1e3?(n/1e3).toFixed(0)+"K":String(n);
const fmtPrice = v => v==null?"?":v===0?"$0":v<0.01?"$"+v.toFixed(4):"$"+v.toFixed(2);
const FIELDS = ["image_input","reasoning","tools","json_mode"];
const LABEL = {image_input:"图像输入",reasoning:"推理",tools:"工具调用",json_mode:"JSON输出"};
let active = new Set();
function render(){
  const q = document.getElementById("q").value.toLowerCase();
  const onlyFree = document.getElementById("onlyfree").checked;
  const sort = document.getElementById("sort").value;
  let list = MODELS.filter(m => {
    if (onlyFree && !m.free) return false;
    for (const f of active) if (!m[f]) return false;
    if (q) {
      const hay = ((m.name||"")+" "+m.id+" "+(m.description||"")+" "+m.provider).toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
  list.sort((a,b)=>{
    if (sort==="free") return (b.free?1:0)-(a.free?1:0) || (a.name||"").localeCompare(b.name||"");
    if (sort==="ctx") return (b.context_length||0)-(a.context_length||0);
    if (sort==="price") return (a.input_per_million==null?1e9:a.input_per_million)-(b.input_per_million==null?1e9:b.input_per_million);
    if (sort==="new") return (b.created||0)-(a.created||0);
    return 0;
  });
  const el = document.getElementById("list");
  if (!list.length) { el.innerHTML = '<div class="empty">没有匹配的模型</div>'; return; }
  el.innerHTML = list.map(m => {
    const tags = FIELDS.filter(f=>m[f]).map(f=>'<span class="tag y">'+LABEL[f]+'</span>').join("")
      + (m.context_length?'<span class="tag">上下文 '+fmtCtx(m.context_length)+'</span>':"")
      + (m.max_output_tokens?'<span class="tag">输出上限 '+fmtCtx(m.max_output_tokens)+'</span>':"");
    const price = m.free
      ? '<span class="badge free">FREE 免费</span>'
      : '<span class="badge paid">'+fmtPrice(m.input_per_million)+' / '+fmtPrice(m.output_per_million)+' per 1M</span>';
    const desc = m.description ? '<div class="desc">'+esc(m.description)+'</div>' : "";
    return '<div class="card '+(m.free?"free":"")+'">'
      + '<div class="top"><div><span class="nm">'+esc(m.name||m.id)+'</span>'
      + '<div class="nid">'+esc(m.id)+'</div></div>'+price+'</div>'
      + desc
      + '<div class="meta"><span>&#127760; '+esc(m.provider)+'</span>'
      + '<span>&#128197; 验证 '+esc(m.last_verified||"-")+'</span>'
      + '<span>&#128279; <a href="'+esc(m.pricing_url||"#")+'" target="_blank" rel="noopener">定价页</a></span></div>'
      + (tags?'<div class="tags">'+tags+'</div>':"")
      + '</div>';
  }).join("");
}
document.getElementById("q").addEventListener("input", render);
document.getElementById("onlyfree").addEventListener("change", render);
document.getElementById("sort").addEventListener("change", render);
document.querySelectorAll(".chip").forEach(c=>c.addEventListener("click", ()=>{
  const f=c.dataset.f; active.has(f)?active.delete(f):active.add(f);
  c.classList.toggle("on"); render();
}));
render();
</script></body></html>"""


def render_site(rows):
    data = flat(rows)
    providers = {r["provider"] for r in rows}
    gen = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    out = SITE_TEMPLATE
    out = out.replace("__GEN__", html.escape(gen))
    out = out.replace("__TOTAL__", str(len(data)))
    out = out.replace("__FREE__", str(sum(1 for m in data if m.get("free"))))
    out = out.replace("__PROV__", str(len(providers)))
    import re as _re
    _safe = json.dumps(data, ensure_ascii=False)
    _safe = _re.sub(r"[<>&]", lambda c: "\\u%04x" % ord(c.group()), _safe)
    out = out.replace("__DATA__", _safe)
    return out


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