# -*- coding: utf-8 -*-
"""发布员:由正本生成产物(docs/free-models.json、README 表格、docs/index.html),
再推送 Telegram 变更摘要。唯一能写通知令牌的智能体;不读探测密钥。"""
import argparse, datetime, html, json, os, pathlib, sys, time
import requests, yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
PROV = ROOT / "providers"
DOCS = ROOT / "docs"
STATE = ROOT / "state.local"
ONLY_FREE = True  # 免费总闸: 默认只收录/展示免费模型(付费留在正本做证据,不进页面)


def load_all():
    rows = []
    for fp in sorted(PROV.glob("*.yaml")):
        rows.append(yaml.safe_load(fp.read_text(encoding="utf-8")))
    return rows


def flat(rows):
    out = []
    for r in rows:
        # 每模型注册跳转: 该厂商自己的 signup(领KEY页),回落 homepage/pricing_url
        su = r.get("signup") or {}
        reg = su.get("url") if isinstance(su, dict) else (su or None)
        reg = reg or r.get("homepage") or r.get("pricing_url")
        home = r.get("homepage") or reg
        for m in r.get("models") or []:
            if ONLY_FREE and not m.get("free"):
                continue  # 免费总闸: 只收录免费模型
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
                "register_url": reg, "provider_home": home,
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
.chanbar{display:flex;gap:8px;flex-wrap:wrap;margin:6px 0 16px}
.chan{background:#161b22;border:1px solid #30363d;border-radius:16px;padding:4px 11px;font-size:12px;color:#8b949e}
.chan b{color:#79c0ff}
.chan.live{border-color:#238636}
.chan.live b{color:#3fb950}
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
.hero{display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin:16px 0}
.cta{background:#238636;color:#fff;text-decoration:none;font-weight:700;padding:11px 20px;border-radius:8px;font-size:15px;box-shadow:0 2px 8px #23863655}
.cta:hover{background:#2ea043}
.ctahint{color:#8b949e;font-size:13px}
.ctahint b{color:#3fb950}
.pop{margin-top:8px}
.reglink{margin-left:8px;background:#238636;color:#fff;text-decoration:none;border-radius:20px;padding:4px 12px;font-size:13px;transition:.15s}
.reglink:hover{background:#2ea043}
.like{background:#21262d;border:1px solid #30363d;color:#8b949e;border-radius:20px;padding:3px 12px;font-size:13px;cursor:pointer;transition:.15s}
.like:hover{border-color:#f85149;color:#f85149}
.like.on{border-color:#f85149;color:#f85149;background:#f8514922}
.submitbox{margin:16px 0;border:1px dashed #30363d;border-radius:10px;padding:10px 14px}
.submitbox summary{cursor:pointer;color:#79c0ff;font-size:14px}
.submitbox form{display:grid;gap:8px;margin-top:10px}
.submitbox input,.submitbox textarea{background:#0d1117;border:1px solid #30363d;color:#c9d1d9;border-radius:6px;padding:8px 10px;font-size:13px}
.submitbox button{background:#1f6feb;color:#fff;border:0;border-radius:6px;padding:9px;cursor:pointer;font-size:14px;justify-self:start}
#submsg{font-size:13px}
#submsg.ok{color:#3fb950}
#submsg.dup{color:#d29922}
footer{color:#484f58;font-size:12px;margin-top:24px;text-align:center}
code{background:#21262d;padding:1px 5px;border-radius:4px}
</style></head><body><div class="wrap">
<header><h1>&#128269; free-ai-radar &mdash; 免费AI模型清单</h1>
<div class="sub">每条事实带来源与验证时间 &middot; 数据正本 <code>providers/*.yaml</code> &middot; 更新 __GEN__</div></header>
<div class="hero">
  <a class="cta" id="regbtn" href="__REGISTER_URL__" target="_blank" rel="noopener" onclick="regClick('site')">&#128279; 各模型注册领免费 KEY &mdash; 点模型卡进入对应厂商</a>
  <span class="ctahint">点任一模型的"注册领KEY"即计入人气 &middot; 已注册 <b id="regcount">0</b></span>
</div>
<div class="stats">
<div class="stat"><b>__TOTAL__</b><span>模型总数</span></div>
<div class="stat"><b>__FREE__</b><span>免费模型</span></div>
<div class="stat"><b>__PROV__</b><span>渠道</span></div>
</div>
<div class="chanbar" id="chanbar"></div>
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
<details class="submitbox"><summary>&#128227; 投稿新模型 / 新渠道(自动查重)</summary>
<form id="subform">
  <input id="surl" type="url" placeholder="接口地址 https://.../v1/models 或厂商定价页" required>
  <input id="smid" placeholder="模型 ID(可选,如 deepseek/DeepSeek-V3)">
  <textarea id="snote" placeholder="说明: 免费额度 / 注册入口等(纯文本,我们会人工核验)"></textarea>
  <button type="submit">提交投稿</button>
  <span id="submsg"></span>
</form></details>
<footer>数据来源: 官方API/页面, 证据见 <code>providers/*.yaml</code> &middot; 无证据写 unknown, 不猜</footer>
</div>
<script>
let MODELS = __DATA__;
const REG_URL = "__REGISTER_URL__";
// ---- 人气: 点赞(心) + 注册点击,本地按模型ID去重,防刷;计数只增 ----
const POP_KEY = "radar_pop_v1", REG_KEY = "radar_reg_v0";
const load = k => { try { return JSON.parse(localStorage.getItem(k)) || {c:{},m:{}} } catch(e){ return {c:{},m:{}} } };
let POP = load(POP_KEY), REG = load(REG_KEY);
const save = (k,v) => { try { localStorage.setItem(k, JSON.stringify(v)) } catch(e){} };
const popOf = id => (POP.c[id]||0);
function likeBtn(id){
  const liked = !!POP.m[id], n = popOf(id);
  return '<button class="like'+(liked?' on':'')+'" data-id="'+esc(id)+'" title="点赞">&#10084; '+n+'</button>';
}
function toggleLike(id){
  if (POP.m[id]) return;            // 已点过 -> 去重,不重复计
  POP.m[id]=1; POP.c[id]=popOf(id)+1; save(POP_KEY,POP); render();
}
function regClick(prov){
  // 记录哪个厂商的注册被点(人气),再计总数一次
  if (prov) { try{ REG.p = REG.p||{}; REG.p[prov]=(REG.p[prov]||0)+1; save(REG_KEY,REG); }catch(e){} }
  if (REG.done) return;             // 总数只计一次
  REG.done=1; REG.n=(REG.n||0)+1; save(REG_KEY,REG); paintReg();
}
function paintReg(){ document.getElementById("regcount").textContent = REG.n||0; }
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
      + '<div class="meta"><span>&#127760; <a href="'+esc(m.provider_home||"#")+'" target="_blank" rel="noopener">'+esc(m.provider)+'</a></span>'
      + '<span>&#128197; 验证 '+esc(m.last_verified||"-")+'</span>'
      + '<span>&#128279; <a href="'+esc(m.pricing_url||"#")+'" target="_blank" rel="noopener">定价页</a></span></div>'
      + (tags?'<div class="tags">'+tags+'</div>':"")
      + '<div class="pop">'+likeBtn(m.id)
      + (m.register_url ? ' <a class="reglink" href="'+esc(m.register_url)+'" target="_blank" rel="noopener" onclick="regClick(\''+esc(m.provider)+'\')">&#128279; 注册领KEY</a>' : '')
      + '</div>'
      + '</div>';
  }).join("");
  document.querySelectorAll(".like").forEach(b=>b.addEventListener("click",()=>toggleLike(b.dataset.id)));
}
// ---- 投稿查重: 客户端提示,真去重在 agents/enrich.py ----
const NORM = u => (u||"").trim().toLowerCase().replace(/^https?:\/\//,"").replace(/^www\./,"").replace(/\/$/,"");
let seen = MODELS.reduce((s,m)=>{ s[NORM(m.id)]=1; return s; }, {});
function renderChan(){
  const by = MODELS.reduce((a,m)=>{ a[m.provider]=(a[m.provider]||0)+1; return a; },{});
  const el = document.getElementById("chanbar");
  if(!el) return;
  el.innerHTML = Object.keys(by).sort((a,b)=>by[b]-by[a]).map(p=>
    '<span class="chan live">'+esc(p)+' <b>'+by[p]+'</b></span>').join("")
    + '<span class="chan" title="配 key 后自动接入">groq/google/openai <b>待配key</b></span>';
}
// ---- init: 所有顶层 DOM 绑定收进这里,挂 DOMContentLoaded(已加载则立即跑),防整体崩 ----
function init(){
  document.getElementById("q").addEventListener("input", render);
  document.getElementById("onlyfree").addEventListener("change", render);
  document.getElementById("sort").addEventListener("change", render);
  document.querySelectorAll(".chip").forEach(c=>c.addEventListener("click", ()=>{
    const f=c.dataset.f; active.has(f)?active.delete(f):active.add(f);
    c.classList.toggle("on"); render();
  }));
  document.getElementById("subform").addEventListener("submit", e=>{
    e.preventDefault();
    const url=NORM(document.getElementById("surl").value), mid=(document.getElementById("smid").value||"").trim().toLowerCase();
    const msg=document.getElementById("submsg");
    if (seen[NORM(url)] || (mid && seen[NORM(mid)])) { msg.textContent="\u26a0 该地址/模型已在清单中,已查重跳过"; msg.className="dup"; return; }
    const rec={url:document.getElementById("surl").value, model_id:mid, note:document.getElementById("snote").value};
    let q=[]; try{ q=JSON.parse(localStorage.getItem("radar_subs")||"[]") }catch(e){}
    if (q.some(x=>NORM(x.url)===NORM(rec.url))) { msg.textContent="\u26a0 你已提交过该地址,已查重跳过"; msg.className="dup"; return; }
    q.push(rec); try{ localStorage.setItem("radar_subs",JSON.stringify(q)) }catch(e){}
    msg.textContent="\u2713 已记录,将人工核验后入库(服务器端再次查重)"; msg.className="ok";
    e.target.reset();
  });
  paintReg();
  renderChan();
  render();
}
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
else init();
const DATA_URL = "free-models.json";
async function refresh(){
  try{
    const r = await fetch(DATA_URL+"?t="+Date.now(), {cache:"no-store"});
    if(!r.ok) return;
    const j = await r.json();
    if(!j.models || j.models.length === MODELS.length && JSON.stringify(j.models) === JSON.stringify(MODELS)) return;
    MODELS = j.models;
    seen = MODELS.reduce((s,m)=>{ s[NORM(m.id)]=1; return s; }, {});  // 重建查重集
    renderChan();
    document.getElementById("regcount").textContent = REG.n||0;
    render();
    const g=document.querySelector("header .sub"); if(g) g.innerHTML = g.innerHTML.replace(/更新 .*/, "更新 " + (j.generated_at||"").replace("T"," "));
  }catch(e){}
}
setInterval(()=>{ if(document.visibilityState === "visible") refresh(); }, 60000);
document.addEventListener("visibilitychange", ()=>{ if(document.visibilityState === "visible") refresh(); });
</script></body></html>"""


SITE_REGISTER_URL = os.environ.get("RADAR_REGISTER_URL", "https://openrouter.ai/")  # 注册领KEY落地页


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
    out = out.replace("__REGISTER_URL__", html.escape(SITE_REGISTER_URL))
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
    ap.add_argument("--include-paid", action="store_true", help="临时把付费模型也放进页面(默认只收录免费)")
    args = ap.parse_args(argv)
    if args.include_paid:
        globals()["ONLY_FREE"] = False
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