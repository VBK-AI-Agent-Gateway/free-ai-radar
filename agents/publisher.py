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
FREE_TYPES_COUNTABLE = {"free_tier", "free_variant", "trial", "promo"}  # 首页只把这四类算"免费"(见 docs/CALIBER.md)


def _is_countable_free(m):
    """免费口径: 有 free_type 用分类判(只永久层/免费变体/试用/促销算); 没有 free_type 回落 free==True。待核验/未知不算。"""
    ft = m.get("free_type")
    if ft:
        return ft in FREE_TYPES_COUNTABLE
    return bool(m.get("free"))


def _show_on_page(m):
    """总闸: 展示 = 确认可免费(免费层/免费变体/试用/促销) + 待核验(price_zero_unverified: 价格0但无证据);
    付费/订阅/本地/unknown(无价格也无证据, 可能付费) 不进免费页。待核验 badge 标"待核验"不是"FREE"。"""
    ft = m.get("free_type")
    if ft:
        return ft in FREE_TYPES_COUNTABLE or ft == "price_zero_unverified"
    return bool(m.get("free"))


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
            if ONLY_FREE and not _show_on_page(m):
                continue  # 免费总闸: 只进 确认可免费 + 待核验(price_zero_unverified); 付费/订阅/本地不进
            caps = m.get("capabilities") or {}
            terms = m.get("terms") or {}
            out.append({
                "id": m.get("id"), "name": m.get("name"), "provider": r["provider"],
                "status": m.get("status"), "free": m.get("free"),
                "free_type": m.get("free_type"),
                "free_limits": m.get("free_limits"),
                "free_evidence": m.get("free_evidence"),
                "description": m.get("description"),
                "context_length": caps.get("context_length"),
                "max_output_tokens": caps.get("max_output_tokens"),
                "input_per_million": terms.get("input_per_million"),
                "output_per_million": terms.get("output_per_million"),
                # 能力三态: 原样传 None(unknown), 不 bool() 压成 False
                "image_input": caps.get("image_input"),
                "reasoning": caps.get("reasoning"),
                "tools": caps.get("tools"),
                "json_mode": caps.get("json_mode"),
                "created": m.get("created"),
                "last_verified": r.get("last_verified"),
                "last_fetched": m.get("last_fetched") or r.get("last_fetched") or r.get("last_verified"),
                "last_probed": m.get("last_probed") or r.get("last_probed"),
                "pricing_url": r.get("pricing_url"),
                "register_url": reg, "provider_home": home,
            })
    return out


def render_readme(rows):
    lines = ["# free-ai-radar", "",
             "免费AI情报汇聚智能体 — 每条事实带来源与验证时间,无证据写 unknown。", "",
             "口径: **免费模型** = 本页与站点展示的免费清单(含免费层);全量 = 正本所有模型(含付费,留作证据/比价,不展示)。", "",
             "| 厂商 | 免费模型 | 全量(含付费) | 免费模型ID | 最后验证 | 说明 |", "| --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        allm = r.get("models") or []
        freem = [m for m in allm if _is_countable_free(m)]  # 免费口径: 只数免费层/免费变体/试用/促销(不含待核验)
        # 只列免费模型ID(免费口径), 不再把全量(含Claude/GPT收费)当免费清单
        ids = ", ".join(m.get("id", "?") for m in freem) or "(待采集员首轮抓取)"
        lines.append(f"| {r['provider']} | {len(freem)} | {len(allm)} | {ids} | {r.get('last_verified')} | {r.get('pricing_url', '')} |")
    lines += ["", "数据正本: `providers/*.yaml`。生成时间: " + time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), ""]
    return "\n".join(lines)


SITE_TEMPLATE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>free-ai-radar - Free AI model directory</title>
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
.catalog{{margin-top:26px}}
.catalog h2{{font-size:16px;margin:0 0 4px}}
.catalog .hint{{color:#8b949e;font-size:12px;margin:0 0 10px}}
.catalog .vgrid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:8px}}
.catalog .v{{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:14px 16px;margin:0}}
.catalog .v.live{{border-color:#238636;box-shadow:0 0 0 1px #23863644}}
.catalog .v .top{{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:baseline}}
.catalog .v .nm{{font-weight:600;color:#e6edf3;font-size:15px}}
.catalog .v .vn{{font-weight:600;font-size:13px;display:flex;justify-content:space-between;gap:6px}}
.catalog .v .vn .badge{{font-size:10px;color:#238636;font-weight:400}}
.catalog .v .vn .badge.apply{{color:#d29922}}
.catalog .v .vc{{font-size:12px;color:#58a6ff;margin:6px 0 2px}}
.catalog .v .vm{{font-size:11px;color:#8b949e;word-break:break-all;line-height:1.4}}
.catalog .v .vmeta{{display:flex;gap:12px;flex-wrap:wrap;font-size:12.5px;color:#8b949e;margin-top:6px}}
.catalog .v a{{display:inline-block;margin-top:8px;font-size:13px;background:#238636;color:#fff;text-decoration:none;border-radius:20px;padding:4px 12px}}
.catalog .v a:hover{{background:#2ea043}}
.catalog .v .vk{{font-size:11px;color:#d29922;margin-top:6px;line-height:1.3}}
.chip{background:#1f6feb33;border:1px solid #1f6feb;color:#79c0ff;border-radius:20px;padding:3px 10px;font-size:12px;cursor:pointer;user-select:none}
.chip.on{background:#1f6feb;color:#fff}
.card{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:14px 16px;margin:10px 0}
.card.free{border-color:#238636;box-shadow:0 0 0 1px #23863644}
.top{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;align-items:baseline}
.nm{font-weight:600;color:#e6edf3;font-size:15px} .nid{color:#8b949e;font-size:12px;font-family:ui-monospace,monospace}
.badge{font-size:11px;padding:3px 9px;border-radius:10px;white-space:nowrap}
.badge.free{background:#238636;color:#fff} .badge.paid{background:#30363d;color:#8b949e} .badge.pend{background:#3a2e12;color:#d29922;border:1px solid #d2992255}
.card.pend{border-color:#d2992244}
.desc{color:#a5adb6;font-size:13px;margin:8px 0}
.meta{display:flex;gap:14px;flex-wrap:wrap;font-size:12.5px;color:#8b949e;margin-top:8px}
.meta b{color:#c9d1d9;font-weight:600}
.tags{display:flex;gap:5px;flex-wrap:wrap;margin-top:8px}
.tag{font-size:11px;background:#21262d;border:1px solid #30363d;color:#8b949e;padding:1px 7px;border-radius:4px}
.tag.unk{background:#161b22;border-style:dashed;color:#6e7681}
.flim{font-size:11px;color:#8b949e;margin-top:5px} .flim.unk{color:#d29922}
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
.submitbox input,.submitbox textarea,.submitbox select{background:#0d1117;border:1px solid #30363d;color:#c9d1d9;border-radius:6px;padding:8px 10px;font-size:13px}
.submitbox select{min-width:150px}
.submitbox .frow{display:flex;gap:8px;flex-wrap:wrap}
.submitbox .frow select{flex:1;min-width:160px}
.submitbox .attest{display:flex;align-items:center;gap:7px;font-size:13px;color:#c9d1d9;cursor:pointer}
.submitbox .attest input{width:auto;padding:0}
.submitbox button{background:#1f6feb;color:#fff;border:0;border-radius:6px;padding:9px;cursor:pointer;font-size:14px;justify-self:start}
.submitbox h2{font-size:15px;margin:0 0 6px}
.submitbox h2 .hint{font-size:12px;color:#8b949e;font-weight:400}
.findbox{display:grid;gap:6px}
.findbox input{background:#0d1117;border:1px solid #30363d;color:#c9d1d9;border-radius:6px;padding:8px 10px;font-size:13px}
#sfindres{display:grid;gap:6px}
.fhit{display:flex;flex-wrap:wrap;gap:8px;align-items:center;background:#161b22;border:1px solid #30363d;border-radius:8px;padding:8px 10px;font-size:13px}
.fhit .fid{color:#c9d1d9;font-weight:600}
.fhit .fp{color:#8b949e;font-size:12px}
.fhit button{background:#21262d;border:1px solid #30363d;color:#c9d1d9;border-radius:6px;padding:4px 8px;font-size:12px;cursor:pointer}
.fhit button:hover{border-color:#58a6ff;color:#58a6ff}
.fnone{color:#8b949e;font-size:12px;padding:4px 2px}
.submitbar{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:10px 0 4px}
.subbtn{background:#1f6feb;color:#fff;text-decoration:none;font-weight:600;padding:9px 16px;border-radius:8px;font-size:14px}
.subbtn:hover{background:#388bfd}
.subhint{color:#8b949e;font-size:12px}
#submsg{font-size:13px}
#submsg.ok{color:#3fb950}
#submsg.dup{color:#d29922}
footer{color:#484f58;font-size:12px;margin-top:24px;text-align:center}
code{background:#21262d;padding:1px 5px;border-radius:4px}
</style></head><body><div class="wrap">
<header><h1>&#128269; free-ai-radar &mdash; <span data-i18n="h1">Free AI model directory</span></h1>
<div class="sub">Every fact carries a source &amp; fetched/probed time &middot; no evidence = unknown &middot; source of truth <code>providers/*.yaml</code> &middot; <span data-i18n="updated">updated</span> <span id="gents">__GEN__</span></div></header>
<div class="hero">
  <a class="cta" id="regbtn" href="#catalog" data-reg="site" data-i18n="cta">&#127760; Browse free models from 74 vendors — click any model/vendor below to sign up</a>
  <span class="ctahint"><span data-i18n="ctahint">Click "Get API key" on any model to upvote it</span> &middot; <span data-i18n="registered">registered</span> <b id="regcount">0</b></span>
</div>
<div class="submitbar">
  <a href="#subform" class="subbtn" id="subopen" data-i18n="submitbtn">&#128227; Submit a free model / new channel</a>
  <span class="subhint" data-i18n="subhint">Auto-dedup, manually verified before landing</span>
</div>
<div class="stats">
<div class="stat"><b>__TOTAL__</b><span data-i18n="stat_total">Ingested (routable)</span></div>
<div class="stat"><b>__PEND__</b><span data-i18n="stat_pend">To verify (price 0)</span></div>
<div class="stat"><b>__CATALOGN__</b><span data-i18n="stat_catalog">In directory (to verify)</span></div>
<div class="stat"><b>__PROBED__</b><span data-i18n="stat_probed">Probed live</span></div>
<div class="stat"><b>__PROV__</b><span data-i18n="stat_prov">Channels (with data)</span></div>
</div>
<div class="chanbar" id="chanbar"></div>
<div class="controls">
<input type="search" id="q" placeholder="Search model / description / vendor...">
<label class="toggle"><input type="checkbox" id="onlyfree"> <span data-i18n="onlyfree">Free only</span></label>
<select id="sort">
<option value="free" data-i18n="sort_free">Sort: free first</option>
<option value="ctx" data-i18n="sort_ctx">Sort: largest context</option>
<option value="price" data-i18n="sort_price">Sort: lowest price</option>
<option value="new" data-i18n="sort_new">Sort: newest</option>
</select>
<select id="langsel" title="Language">
<option value="en" selected>English</option>
<option value="zh">中文</option>
</select>
</div>
<div class="chips" id="chips">
<span class="chip" data-f="image_input" data-i18n="f_image">Vision input</span>
<span class="chip" data-f="reasoning" data-i18n="f_reason">Reasoning</span>
<span class="chip" data-f="tools" data-i18n="f_tools">Tool calling</span>
<span class="chip" data-f="json_mode" data-i18n="f_json">JSON output</span>
</div>
<div id="list"></div>
<section class="catalog" id="catalog">
<h2>&#127760; <span data-i18n="cat_h">Free-model directory — which vendors have free models</span></h2>
<p class="hint" data-i18n="cat_hint">Ingested ones you can open directly; pending buttons honestly label where they lead (signup / console / docs) — you must apply at the vendor yourself. models.dev only gives doc links, so most buttons are "view official docs" rather than a direct signup page.</p>
<div class="vgrid" id="vgrid"></div>
</section>
<section class="submitbox open" id="submitbox">
<h2>&#128227; <span data-i18n="sub_h">Submit a free model / new channel</span> <span class="hint" data-i18n="sub_hhint">(auto-dedup + manual review, fields match the Issue template)</span></h2>
<form id="subform">
  <div class="findbox">
    <input id="sfind" placeholder="Search first: vendor, model or domain — if found, report on the card; only add below if not found" autocomplete="off">
    <div id="sfindres"></div>
  </div>
  <input id="surl" type="url" placeholder="Endpoint https://.../v1/models or vendor pricing page (required)" required>
  <input id="smid" placeholder="Model ID (optional, e.g. deepseek/DeepSeek-V3)">
  <div class="frow">
    <select id="stype" required>
      <option value="" data-i18n="stype_empty">Source type (required)…</option>
      <option value="official_api">official_api official API</option>
      <option value="official_page">official_page official pricing page</option>
      <option value="vendor_submission">vendor_submission vendor self-report</option>
      <option value="community">community community/media lead</option>
      <option value="probe">probe live probe</option>
      <option value="telemetry">telemetry usage telemetry</option>
    </select>
    <select id="stier" required>
      <option value="" data-i18n="stier_empty">Free status (required)…</option>
      <option value="完全免费" data-i18n="stier_free">Fully free (price = 0)</option>
      <option value="免费额度层" data-i18n="stier_tier">Free tier (quota)</option>
      <option value="限时免费" data-i18n="stier_promo">Limited-time / promo free</option>
      <option value="不确定" data-i18n="stier_unsure">Not sure, to verify</option>
    </select>
  </div>
  <textarea id="snote" placeholder="Note / evidence: free quota, signup entry, etc. (plain text, manually verified)"></textarea>
  <label class="attest"><input type="checkbox" id="sattest" required> <span data-i18n="attest">I checked the list; this endpoint/model is not a duplicate</span></label>
  <button type="submit" data-i18n="subbtn">Submit</button>
  <span id="submsg"></span>
</form></section>
<footer data-i18n="footer">Data from official APIs/pages, evidence in <code>providers/*.yaml</code> &middot; no evidence = unknown, no guessing</footer>
</div>
<script>
let MODELS = __DATA__;
let CATALOG = __CATALOG__;
const REG_URL = "__REGISTER_URL__";
// ---- 人气: 点赞(心) + 注册点击,本地按模型ID去重,防刷;计数只增 ----
const POP_KEY = "radar_pop_v1", REG_KEY = "radar_reg_v0";
const load = k => { try { return JSON.parse(localStorage.getItem(k)) || {c:{},m:{}} } catch(e){ return {c:{},m:{}} } };
let POP = load(POP_KEY), REG = load(REG_KEY);
const save = (k,v) => { try { localStorage.setItem(k, JSON.stringify(v)) } catch(e){} };
const popOf = id => (POP.c[id]||0);
function likeBtn(id){
  const liked = !!POP.m[id], n = popOf(id);
  return '<button class="like'+(liked?' on':'')+'" data-id="'+esc(id)+'" title="'+t("like")+'">&#10084; '+n+'</button>';
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
// 应用语言: 静态(data-i18n) + 重渲染动态内容 + 切 <html lang>
function applyLang(lang){
  LANG = (lang==="zh"||lang==="en")?lang:"en";
  try{ localStorage.setItem("radar_lang", LANG); }catch(e){}
  document.documentElement.lang = LANG;
  document.querySelectorAll("[data-i18n]").forEach(el=>{
    const k=el.dataset.i18n, v=t(k);
    if(v==null) return;
    if(/<code|&lt;|&amp;/.test(v) || v.indexOf("<code")>=0) el.innerHTML=v; else el.textContent=v;
  });
  const sel=document.getElementById("langsel"); if(sel) sel.value=LANG;
  // 重渲染依赖 t() 的动态区
  renderChan(); renderCatalog(); render(); runFind(); paintReg();
}
const esc = s => (s==null?"":String(s)).replace(/[&<>"']/g, c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
// ---- i18n: 英文默认, 可切中文 (静态用 data-i18n, 动态用 t()) ----
const I18N = {
  en: {
    h1:"Free AI model directory", updated:"updated", cta:"Browse free models from 74 vendors — click any model/vendor below to sign up",
    ctahint:"Click \"Get API key\" on any model to upvote it", registered:"registered", submitbtn:"Submit a free model / new channel",
    subhint:"Auto-dedup, manually verified before landing", stat_total:"Ingested (routable)", stat_pend:"To verify (price 0)",
    stat_catalog:"In directory (to verify)", stat_probed:"Probed live", stat_prov:"Channels (with data)", onlyfree:"Free only",
    sort_free:"Sort: free first", sort_ctx:"Sort: largest context", sort_price:"Sort: lowest price", sort_new:"Sort: newest",
    f_image:"Vision input", f_reason:"Reasoning", f_tools:"Tool calling", f_json:"JSON output",
    cat_h:"Free-model directory — which vendors have free models",
    cat_hint:"Ingested ones you can open directly; pending buttons honestly label where they lead (signup / console / docs) — you must apply at the vendor yourself. models.dev only gives doc links, so most buttons are \"view official docs\" rather than a direct signup page.",
    sub_h:"Submit a free model / new channel", sub_hhint:"(auto-dedup + manual review, fields match the Issue template)",
    stype_empty:"Source type (required)…", stier_empty:"Free status (required)…", stier_free:"Fully free (price = 0)",
    stier_tier:"Free tier (quota)", stier_promo:"Limited-time / promo free", stier_unsure:"Not sure, to verify",
    attest:"I checked the list; this endpoint/model is not a duplicate", subbtn:"Submit",
    footer:"Data from official APIs/pages, evidence in <code>providers/*.yaml</code> · no evidence = unknown, no guessing",
    // dynamic (JS-built) strings
    free:"FREE free", pend:"To verify", no_match:"No matching models",
    probed:"Probed", fetched:"Fetched", not_probed:"(not probed)", status_declared:"Vendor-declared", status_probed:"Probed live", status_verified:"Verified",
    pricing:"Pricing page", getkey:"Get API key", limit:"Limit", limit_unknown:"Free limit — see official page (unverified)", ctx:"Context", maxout:"Max output", unknown:"unknown",
    ingested:"ingested", open:"Open", live_ingested:"Ingested", to_apply:"To apply", verified:"Verified", apply_key:"Apply for key",
    link_signup:"Signup", link_console:"Console", link_doc:"Official docs", link_pricing:"Pricing", link_home:"Website", link_link:"Link", free_models:"free models",
    none_found:"↳ Not in the list → fill in a new submission below", needs_key:"needs key",
    rep_still:"Still works", rep_quota:"Quota changed", rep_gone:"No longer works", rep_phone:"Requires phone", rep_region:"Doesn't work for me",
    msg_fill:"⚠ Please enter an endpoint or pricing page", msg_dup:"⚠ That endpoint/model is already in the list — duplicate, cannot submit",
    msg_selfdup:"⚠ You already submitted this endpoint — duplicate, cannot submit", msg_ok:"✓ Passed dedup (not a duplicate). ", msg_gh:"→ Submit on GitHub for review",
    report_tag:"[Report]", submit_tag:"[Submission]", like:"Upvote"
  },
  zh: {
    h1:"免费AI模型清单", updated:"更新", cta:"看 74 家厂商的免费模型 — 点下方任一模型/厂商进去申请",
    ctahint:"点任一模型的“注册领KEY”即计入人气", registered:"已注册", submitbtn:"我要提交一个免费模型 / 新渠道",
    subhint:"自动查重,人工核验后入库", stat_total:"已收录(可路由)", stat_pend:"待核验(价格0)",
    stat_catalog:"目录发现(待核验)", stat_probed:"已实测", stat_prov:"渠道(有数据)", onlyfree:"只看免费",
    sort_free:"排序: 免费优先", sort_ctx:"排序: 上下文最大", sort_price:"排序: 价格最低", sort_new:"排序: 最新收录",
    f_image:"图像输入", f_reason:"推理", f_tools:"工具调用", f_json:"JSON输出",
    cat_h:"免费模型总目录 — 哪些厂商有免费模型",
    cat_hint:"已收录的直接看;待申请的按钮如实标注去向(注册口/控制台/文档),需自行到厂商处申请。models.dev 只提供文档链接,多数按钮是“查官方文档”而非直接注册页。",
    sub_h:"主动提交免费模型 / 新渠道", sub_hhint:"(自动查重 + 人工审核, 字段与 Issue 模板一致)",
    stype_empty:"来源类型(必选)…", stier_empty:"免费情况(必选)…", stier_free:"完全免费(价格=0)",
    stier_tier:"免费额度层(free tier)", stier_promo:"限时/活动免费", stier_unsure:"不确定,待核验",
    attest:"我已查过清单,该地址/模型不重复", subbtn:"提交投稿",
    footer:"数据来源: 官方API/页面, 证据见 <code>providers/*.yaml</code> · 无证据写 unknown, 不猜",
    free:"FREE 免费", pend:"待核验", no_match:"没有匹配的模型",
    probed:"实测", fetched:"抓取", not_probed:"(未实测)", status_declared:"厂商声明", status_probed:"实测", status_verified:"已验证",
    pricing:"定价页", getkey:"注册领KEY", limit:"限额", limit_unknown:"免费限额见官方页(未核验)", ctx:"上下文", maxout:"输出上限", unknown:"未知",
    ingested:"个免费模型", open:"打开", live_ingested:"已收录", to_apply:"待申请", verified:"已验证", apply_key:"待申请key", free_models:"个免费模型",
    link_signup:"注册口", link_console:"控制台", link_doc:"官方文档", link_pricing:"定价页", link_home:"官网", link_link:"链接", needs_key:"待配key",
    none_found:"↳ 清单未命中 → 在下面填新增投稿", rep_still:"仍可用", rep_quota:"额度变了", rep_gone:"已失效", rep_phone:"要手机号", rep_region:"我这里不能用",
    msg_fill:"⚠ 请填接口地址或定价页", msg_dup:"⚠ 该地址/模型已在清单中,重复,无法提交",
    msg_selfdup:"⚠ 你已提交过该地址,重复,无法提交", msg_ok:"✓ 查重通过(非重复)。", msg_gh:"→ 去 GitHub 提交审核",
    report_tag:"[上报]", submit_tag:"[投稿]", like:"点赞"
  }
};
let LANG = "en";  // 英文默认
try { LANG = localStorage.getItem("radar_lang") || "en"; } catch(e){}
const t = k => (I18N[LANG] && I18N[LANG][k]) || (I18N.en[k] || k);
// 安全: 第三方数据(register/apply/home/pricing)进 href 前过 https 白名单, 非 https(javascript:)一律回 #
const safeUrl = u => { try{ const x=new URL(u, location.href); return x.protocol==="https:" ? x.href : "#"; }catch(e){ return "#"; } };
const fmtCtx = n => (n==null)?t("unknown"):n>=1e6?(n/1e6).toFixed(0)+"M":n>=1e3?(n/1e3).toFixed(0)+"K":String(n);
const fmtPrice = v => v==null?"?":v===0?"$0":v<0.01?"$"+v.toFixed(4):"$"+v.toFixed(2);
const FIELDS = ["image_input","reasoning","tools","json_mode"];
const LBLK = {image_input:"f_image",reasoning:"f_reason",tools:"f_tools",json_mode:"f_json"};
// 能力三态标签: true=确认支持(绿); false=不显示; null=未知(灰, 单独标)
function capTags(m){
  let s = FIELDS.filter(f=>m[f]===true).map(f=>'<span class="tag y">'+t(LBLK[f])+'</span>').join("")
        + FIELDS.filter(f=>m[f]===null).map(f=>'<span class="tag unk">'+t(LBLK[f])+' '+t("unknown")+'</span>').join("");
  s += (m.context_length!=null?'<span class="tag">'+t("ctx")+' '+fmtCtx(m.context_length)+'</span>':"")
     + (m.max_output_tokens!=null?'<span class="tag">'+t("maxout")+' '+fmtCtx(m.max_output_tokens)+'</span>':"");
  return s;
}
// 筛选: 三态, true 才算"支持"; null(unknown) 不算支持(但可被"含未知"单独筛)
function capPass(m,f){ if(m[f]===true) return true; if(m[f]===null && active.has(f+"?")) return true; return false; }
let active = new Set();
function render(){
  const q = document.getElementById("q").value.toLowerCase();
  const onlyFree = document.getElementById("onlyfree").checked;
  const sort = document.getElementById("sort").value;
  let list = MODELS.filter(m => {
    if (onlyFree && !m.free) return false;
    for (const f of active) if (!capPass(m,f)) return false;
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
  if (!list.length) { el.innerHTML = '<div class="empty">'+t("no_match")+'</div>'; return; }
  el.innerHTML = list.map(m => {
    const tags = capTags(m);
    // 免费类型 badge: 免费层/免费变体/试用/促销 -> FREE; price_zero_unverified/unknown -> 待核验; 其余显示价格
    let price;
    if (m.free_type==="free_tier"||m.free_type==="free_variant"||m.free_type==="trial"||m.free_type==="promo")
      price = '<span class="badge free">'+t("free")+'</span>';
    else if (m.free_type==="price_zero_unverified"||m.free_type==="unknown"||m.free===null||m.free===undefined)
      price = '<span class="badge pend">'+t("pend")+'</span>';
    else
      price = '<span class="badge paid">'+fmtPrice(m.input_per_million)+' / '+fmtPrice(m.output_per_million)+' per 1M</span>';
    const desc = m.description ? '<div class="desc">'+esc(m.description)+'</div>' : "";
    // 时间: 有 last_probed 显示"实测", 否则"抓取(未实测)" — 不把抓取当验证
    const timeLbl = m.last_probed
      ? '&#128200; '+t("probed")+' '+esc(String(m.last_probed).slice(0,10))
      : '&#128197; '+t("fetched")+' '+esc(String(m.last_fetched||m.last_verified||"-").slice(0,10))+' '+t("not_probed");
    return '<div class="card '+((m.free===true)?"free":"pend")+'">'
      + '<div class="top"><div><span class="nm">'+esc(m.name||m.id)+'</span>'
      + '<div class="nid">'+esc(m.id)+'</div></div>'+price+'</div>'
      + desc
      + '<div class="meta"><span>&#127760; <a href="'+safeUrl(m.provider_home||"")+'" target="_blank" rel="noopener">'+esc(m.provider)+'</a></span>'
      + '<span>'+timeLbl+'</span>'
      + (m.status?'<span class="tag">'+({declared:t("status_declared"),probed:t("status_probed"),verified:t("status_verified")}[m.status]||esc(m.status))+'</span>':"")
      + '<span>&#128279; <a href="'+safeUrl(m.pricing_url||"")+'" target="_blank" rel="noopener">'+t("pricing")+'</a></span></div>'
      + (tags?'<div class="tags">'+tags+'</div>':"")
      + (m.free_limits && m.free_limits!=="unknown" ? '<div class="flim">&#128200; '+t("limit")+' '+esc(typeof m.free_limits==="object"?JSON.stringify(m.free_limits):String(m.free_limits))+'</div>' : (m.free_type==="free_variant"||m.free_type==="free_tier" ? '<div class="flim unk">&#9888; '+t("limit_unknown")+'</div>' : ""))
      + '<div class="pop">'+likeBtn(m.id)
      + (m.register_url ? ' <a class="reglink" href="'+safeUrl(m.register_url)+'" target="_blank" rel="noopener" data-reg="'+esc(m.provider)+'">&#128279; '+t("getkey")+'</a>' : '')
      + '</div>'
      + '</div>';
  }).join("");
  document.querySelectorAll(".like").forEach(b=>b.addEventListener("click",()=>toggleLike(b.dataset.id)));
  document.querySelectorAll("[data-reg]").forEach(a=>a.addEventListener("click",()=>regClick(a.dataset.reg)));
}
// ---- 投稿查重: 端点唯一键 = provider + model id (同一ID跨厂商是不同端点); 真去重在 agents/enrich.py ----
const NORM = u => (u||"").trim().toLowerCase().replace(/^https?:\/\//,"").replace(/^www\./,"").replace(/\/$/,"");
const EKEY = m => (m.provider+"/"+m.id).toLowerCase();   // 端点唯一键
let seen = MODELS.reduce((s,m)=>{ s[EKEY(m)]=1; s[NORM(m.id)]=1; return s; }, {});
// 目录里的厂商域名也进查重集(投稿填了已收录厂商的接口/定价页 -> 拦)
let seenDomains = {};
if (CATALOG && CATALOG.vendors) CATALOG.vendors.forEach(v=>{ const h=NORM(v.home||v.apply_url||""); if(h) seenDomains[h.split("/")[0]]=1; });
function renderChan(){
  const by = MODELS.reduce((a,m)=>{ a[m.provider]=(a[m.provider]||0)+1; return a; },{});
  const el = document.getElementById("chanbar");
  if(!el) return;
  el.innerHTML = Object.keys(by).sort((a,b)=>by[b]-by[a]).map(p=>
    '<span class="chan live">'+esc(p)+' <b>'+by[p]+'</b></span>').join("")
    + '<span class="chan" title="'+t("needs_key")+'">groq/google/openai <b>'+t("needs_key")+'</b></span>';
}
// ---- 免费模型总目录: live=已收录可直接看; apply=确认有免费模型+去申请key入口 ----
function renderCatalog(){
  const el = document.getElementById("vgrid");
  if(!el || !CATALOG || !CATALOG.vendors) return;
  el.innerHTML = CATALOG.vendors.map(v=>{
    const live = v.status==="live";
    const btn = v.btn || (live?t("open"):t("open"));
    const badge = live ? '<span class="badge free">'+t("live_ingested")+'</span>' : '<span class="badge apply">'+t("to_apply")+'</span>';
    const link = v.apply_url
      ? '<a href="'+safeUrl(v.apply_url)+'" target="_blank" rel="noopener" title="'+esc(v.note||"")+'" data-reg="'+esc(v.provider)+'">'+esc(btn)+'</a>' : '';
    const models = (v.sample_models||[]).slice(0,4).join(", ");
    const kindLbl = {signup:t("link_signup"), console:t("link_console"), doc:t("link_doc"), pricing:t("link_pricing"), homepage:t("link_home")}[v.link_kind]||t("link_link");
    return '<div class="v'+(live?" live":"")+'">'
      + '<div class="top"><div class="nm">'+esc(v.name)+'</div>'+badge+'</div>'
      + '<div class="vc">'+v.free_count+' '+t("free_models")+'</div>'
      + '<div class="vm">'+esc(models)+'</div>'
      + '<div class="vmeta"><span>&#128279; '+kindLbl+'</span>'+(live?'<span>&#9989; '+t("verified")+'</span>':'<span>&#128269; '+t("apply_key")+'</span>')+'</div>'
      + (v.note? '<div class="vk">'+esc(v.note)+'</div>':'')
      + link + '</div>';
  }).join("");
  el.querySelectorAll("[data-reg]").forEach(a=>a.addEventListener("click",()=>regClick(a.dataset.reg)));
}
// ---- 先搜后提: 搜清单, 命中就在卡片上一键上报(仍可用/额度变了/已失效), 搜不到才走下面新增 ----
function reportFor(mid, prov, kind){
  const title=encodeURIComponent(t("report_tag")+" "+kind+" — "+mid);
  const body=encodeURIComponent(
    "- 类型: 对已有条目的上报(非新增)\n"+
    "- 模型: "+mid+"\n- 厂商: "+(prov||"-")+"\n- 上报: "+kind+"\n"+
    "- 说明: (可在此补证据, 如截图链接/额度数值)\n\n"+
    "_先搜后提: 这是对清单中已收录条目的状态上报, 不是重复新增。请审核。_");
  window.open("https://github.com/VBK-AI-Agent-Gateway/free-ai-radar/issues/new?title="+title+"&body="+body, "_blank", "noopener");
}
const REPORT_KEYS=["rep_still","rep_quota","rep_gone","rep_phone","rep_region"];
const REPORT_KINDS=()=>REPORT_KEYS.map(t);
function runFind(){
  const box=document.getElementById("sfindres"); if(!box) return;
  const q=(document.getElementById("sfind").value||"").trim().toLowerCase();
  if(!q){ box.innerHTML=""; return; }
  // 搜模型 ID / 名称 / 厂商 / 域名(register_url|provider_home|pricing_url)
  const hits=MODELS.filter(m=>{
    const hay=((m.id||"")+" "+(m.name||"")+" "+(m.provider||"")+" "+(m.register_url||"")+" "+(m.provider_home||"")+" "+(m.pricing_url||"")).toLowerCase();
    return hay.indexOf(q)>=0;
  }).slice(0,8);
  if(!hits.length){ box.innerHTML='<div class="fnone">'+t("none_found")+'</div>'; return; }
  box.innerHTML=hits.map(m=>
    '<div class="fhit"><span class="fid">'+esc(m.id)+'</span><span class="fp">'+esc(m.provider)+'</span>'+
    REPORT_KINDS().map((k,ki)=>'<button data-rep="'+esc(EKEY(m))+'" data-repk="'+ki+'">'+k+'</button>').join("")+
    '</div>').join("");
  box.querySelectorAll("[data-rep]").forEach(b=>b.addEventListener("click",()=>{
    const p=b.dataset.rep.split("/"); reportFor(p.slice(1).join("/"), p[0], REPORT_KINDS()[+b.dataset.repk]);
  }));
}
function openSubmit(){
  const b=document.getElementById("submitbox");
  if(b){ b.scrollIntoView({behavior:"smooth",block:"center"}); const f=document.getElementById("surl"); if(f) setTimeout(()=>f.focus(),400); }
  return false; // 阻止 #subform 默认跳,改平滑滚动
}
// ---- init: 所有顶层 DOM 绑定收进这里,挂 DOMContentLoaded(已加载则立即跑),防整体崩 ----
function init(){
  applyLang(LANG);  // 英文默认, 已存偏好则切换
  document.getElementById("q").addEventListener("input", render);
  document.getElementById("onlyfree").addEventListener("change", render);
  document.getElementById("sort").addEventListener("change", render);
  const ls=document.getElementById("langsel");
  if(ls) ls.addEventListener("change", ()=>applyLang(ls.value));
  document.querySelectorAll(".chip").forEach(c=>c.addEventListener("click", ()=>{
    const f=c.dataset.f; active.has(f)?active.delete(f):active.add(f);
    c.classList.toggle("on"); render();
  }));
  document.getElementById("sfind").addEventListener("input", runFind);
  document.getElementById("subopen").addEventListener("click", (e)=>{ e.preventDefault(); openSubmit(); });
  document.getElementById("subform").addEventListener("submit", e=>{
    e.preventDefault();
    const url=NORM(document.getElementById("surl").value), mid=NORM(document.getElementById("smid").value);
    const msg=document.getElementById("submsg");
    if (!url) { msg.textContent=t("msg_fill"); msg.className="dup"; return; }
    // 第1层: 前端实时查重(端点唯一键 provider/id + 目录域名 + 模型ID -> 拒绝)
    const dom = url.split("/")[0];
    if ((mid && seen[mid]) || seenDomains[dom]) { msg.textContent=t("msg_dup"); msg.className="dup"; return; }
    // 第2层: 本地已提交过 -> 拒绝
    let q=[]; try{ q=JSON.parse(localStorage.getItem("radar_subs")||"[]") }catch(e){}
    if (q.some(x=>NORM(x.url)===url)) { msg.textContent=t("msg_selfdup"); msg.className="dup"; return; }
    q.push({url:url, model_id:mid}); try{ localStorage.setItem("radar_subs",JSON.stringify(q)) }catch(e){}
    // 第3层(后端): 投稿 -> GitHub Issues(免费审核队列), 你在 Issues 里审核 approve/reject
    const stype=document.getElementById("stype").value||"-";
    const stier=document.getElementById("stier").value||"-";
    const title=encodeURIComponent(t("submit_tag")+" "+(mid||"新免费模型/渠道"));
    const body=encodeURIComponent(
      "- 接口/定价页: "+document.getElementById("surl").value+"\n"+
      "- 模型 ID: "+(document.getElementById("smid").value||"-")+"\n"+
      "- 来源类型: "+stype+"\n"+
      "- 免费情况: "+stier+"\n"+
      "- 说明: "+(document.getElementById("snote").value||"-")+"\n\n"+
      "_前端已查重通过(非重复)。请审核后关闭此 Issue。_");
    const gh="https://github.com/VBK-AI-Agent-Gateway/free-ai-radar/issues/new?title="+title+"&body="+body;
    msg.innerHTML=t("msg_ok")+'<a href="'+safeUrl(gh)+'" target="_blank" rel="noopener" style="color:#58a6ff">'+t("msg_gh")+'</a>';
    msg.className="ok";
    window.open(gh, "_blank", "noopener");
    e.target.reset();
  });
  paintReg();
  renderChan();
  renderCatalog();
  document.querySelectorAll("[data-reg]").forEach(a=>a.addEventListener("click",()=>regClick(a.dataset.reg)));
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
    seen = MODELS.reduce((s,m)=>{ s[EKEY(m)]=1; s[NORM(m.id)]=1; return s; }, {});  // 重建查重集(端点键)
    if (j.catalog) { CATALOG = j.catalog; renderCatalog(); }  // 目录也刷新(不再等重部署)
    renderChan();
    document.getElementById("regcount").textContent = REG.n||0;
    render();
    const ts=document.getElementById("gents"); if(ts) ts.textContent=(j.generated_at||"").replace("T"," ");
  }catch(e){}
}
setInterval(()=>{ if(document.visibilityState === "visible") refresh(); }, 300000);  // 5分钟(降频, 减轻 Pages 带宽)
document.addEventListener("visibilitychange", ()=>{ if(document.visibilityState === "visible") refresh(); });
</script></body></html>"""


SITE_REGISTER_URL = os.environ.get("RADAR_REGISTER_URL", "https://openrouter.ai/")  # 注册领KEY落地页


def _load_cat():
    """读免费模型总目录(free-catalog.json), 供首页"目录发现"数与刷新用;读不到返回空。"""
    try:
        return json.loads((ROOT / "docs" / "free-catalog.json").read_text(encoding="utf-8"))
    except Exception:
        return {"vendors": [], "total_free_models": 0}


def render_site(rows):
    data = flat(rows)
    providers = {r["provider"] for r in rows}
    gen = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    # 免费模型总目录(确认有免费模型的厂商清单)
    _cat = _load_cat()
    out = SITE_TEMPLATE
    out = out.replace("__GEN__", html.escape(gen))
    out = out.replace("__TOTAL__", str(sum(1 for m in data if m.get("free_type") in FREE_TYPES_COUNTABLE)))  # 已收录: 确认可免费
    out = out.replace("__PEND__", str(sum(1 for m in data if m.get("free_type") == "price_zero_unverified")))  # 待核验: 价格0无证据
    out = out.replace("__PROBED__", str(sum(1 for m in data if m.get("status") == "probed")))
    # 目录发现: free-catalog 里全部待核验/待申请的模型数
    out = out.replace("__CATALOGN__", str(_cat.get("total_free_models", 0) or 0))
    # 渠道: 只算有模型数据的厂商(不是 yaml 文件数)
    prov_with_data = {r["provider"] for r in rows if r.get("models")}
    out = out.replace("__PROV__", str(len(prov_with_data)))
    import re as _re
    _safe = json.dumps(data, ensure_ascii=False)
    _safe = _re.sub(r"[<>&]", lambda c: "\\u%04x" % ord(c.group()), _safe)
    out = out.replace("__DATA__", _safe)
    _cat_s = json.dumps(_cat, ensure_ascii=False)
    _cat_s = _re.sub(r"[<>&]", lambda c: "\\u%04x" % ord(c.group()), _cat_s)
    out = out.replace("__CATALOG__", _cat_s)
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
                    "models": flat(rows), "providers": len(rows),
                    "catalog": _load_cat()},
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