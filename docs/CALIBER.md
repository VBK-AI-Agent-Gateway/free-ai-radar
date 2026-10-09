# 设计：免费类型分类（free_type）+ 三态字段 — 数据口径修正

> 修"价格为 0 = 免费"这个判定 bug（两条路都错），并把"未知写成 false"改回三态。
> 这是**数据正本**，采集/发布/页面都照此实现。对应外部意见的 P0 第 1 条。

---

## 一、为什么改：现在两条路都错

| 现在的做法 | 错在哪 |
| --- | --- |
| `free = (input==0 and output==0)` | **误判**：按次/按秒计费的模型（Lyria 每首 $0.08、gpt-live 按秒、auto 按所选模型计价）token 单价字段空/0 → 被当成免费，**是假免费** |
| 同上 | **漏判**：Google/Groq/Mistral/Cloudflare/SambaNova 的免费层是"价格非零但**有限额**的免费额度"，价格字段不是 0 → 被漏掉，而它们才是长期免费主力 |
| 混在一起 | 订阅套餐（Alibaba/MiniMax/Volcengine "Token/Coding Plan"、GitLab Duo）、本地软件（LMStudio/QVAC）被当成"托管免费 API" |
| 能力字段 `bool(...)` | "没抓到" 被写成 `false`（如 requesty gemma 的 tools/image_input），违反"无证据写 unknown" |

---

## 二、`free_type` 字段：免费类型分类

**每个模型加一个 `free_type`**（枚举），`free` 布尔变成由 `free_type` 推导：

```yaml
# providers/{id}.yaml 里每个 model:
- id: xxx
  free: true              # 由 free_type 推导(见下)
  free_type: permanent    # ← 新增, 免费类型
  free_evidence: "..."    # ← 新增, 证据(限额/条款原文), 无则留空
```

### 枚举定义

| `free_type` | 含义 | `free`? | 首页算"免费"? | 证据要求 |
| --- | --- | --- | --- | --- |
| `permanent` | **永久免费层**：厂商文档明说的免费额度/免费档（如 Gemini 免费层 RPM/TPM、Groq 免费档） | `true` | ✅ 算 | 必须有厂商文档的**限额条款**（RPM/RPD/TPM），`free_evidence` 写限额 |
| `trial` | **试用额度**：新用户送 N 美元/额度，用完即止 | `true` | ✅ 算 | 送多少、多久 |
| `promo` | **限时促销**：活动期免费，会过期 | `true` | ✅ 算 | 活动截止日 |
| `subscription` | **订阅内含**：套餐（Coding Plan/Token Plan/Duo）里含，不是独立免费 API | `false` | ❌ 不算 | 属于哪个套餐 |
| `local` | **本地运行**：LMStudio/QVAC 等本地软件，非托管 API | `false` | ❌ 不算 | 本地部署说明 |
| `zero_price` | **仅价格为 0（待核验）**：抓到价格=0，但**没证据**是真免费层（可能是按次计费单价空、或数据缺失） | `null`(unknown) | ⚠️ 不算（待核验区） | 缺 —— 需人工补 |
| `paid` | 明确付费 | `false` | ❌ 不算 | 定价页 |
| `unknown` | 完全没证据 | `null` | ❌ 不算 | 缺 |

### 推导规则（`free` 布尔）

```python
FREE_TYPES_COUNTABLE = {"permanent", "trial", "promo"}   # 首页只把这三类算"免费"

def derive_free(free_type):
    if free_type in FREE_TYPES_COUNTABLE: return True
    if free_type in ("subscription", "local", "paid"): return False
    return None   # zero_price / unknown -> None(不进免费清单, 也不武断判 false)
```

### 怎么判出 `free_type`（采集时）

**不再用"价格=0"直接判 `free`**，改成：

1. **结构信号优先**（能自动判的）：
   - 描述/字段里有 `per song`/`per second`/`per image`/`per request`/按次/按秒/按图 → **不是按 token 计价** → `zero_price`（待核验，除非同时有免费额度证据）。
   - id/description 含 `:free`、`free` 标记、厂商明示 free tier → 候选 `permanent`。
   - id/description/厂商名含 `plan`/`subscription`/`duo`/`token plan`/`coding plan` → `subscription`。
   - 厂商/描述表明本地运行（`local`/`ollama`/`lmstudio`/`desktop`）→ `local`。
2. **价格信号兜底**（只在没有上面信号时）：
   - `input==0 and output==0` **且** 有证据支持免费层 → `permanent`；**只有价格 0 没别的证据 → `zero_price`**（待核验，**不进免费清单**）。
   - 价格 > 0 → `paid`（**除非**有免费额度证据，那是 `permanent`，需 `free_evidence`）。
3. **人工核验**：`zero_price` 和需要限额的 `permanent`，由人（或带 key 的探测）补 `free_evidence` 后转正。

**关键：首页免费数 = `free_type ∈ {permanent, trial, promo}` 的个数**，`zero_price` 单列"待核验"，不混进免费数。

---

## 三、三态字段（能力 + free）

**原则：`true` / `false` / `unknown` 三态，unknown 不写成 false。**

### 1. 能力字段（`image_input`/`reasoning`/`tools`/`json_mode`/`context_length`…）

采集时区分三种：
- **明确支持** → `true`（有 `supported_parameters` 含 tools、或架构明示）
- **明确不支持** → `false`（接口/文档明示不支持）
- **没抓到 / 接口不给** → `null`（**unknown**）

现在 `_caps` 用 `{k:v for ... if v not in (None, False, ...)}` **把 false 和 null 一起丢掉**，下游读不到就当 false —— 这是 bug 根源。改成**保留三态**：

```python
def _caps(m):
    # 只有"明确在 supported_parameters 里"才 True; 接口没给这个字段 -> None(unknown), 不是 False
    params = m.get("supported_parameters")
    if params is None:
        tools = reason = jsonm = None          # 接口不给 -> unknown
    else:
        params = set(params)
        tools = "tools" in params
        reason = "reasoning" in params
        jsonm  = "response_format" in params or "structured_outputs" in params
    # image_input 同理: arch 给了 input_modalities 才判, 没给 -> None
    inp = (m.get("architecture") or {}).get("input_modalities")
    image = ("image" in inp) if inp is not None else None
    return {"tools": tools, "reasoning": reason, "json_mode": jsonm, "image_input": image,
            "context_length": m.get("context_length")}   # 没有就是 None
```

### 2. 页面显示规范

| 值 | 卡片显示 | 筛选（"工具调用"芯片）行为 |
| --- | --- | --- |
| `true` | ✅ 工具调用 | 命中 |
| `false` | （不显示该标签） | 不命中 |
| `null` | **"未知"**（灰色标签） | **不命中但单独可筛"含未知"**；默认排除在"确认支持"外 |

- `context_length: null` → 显示"上下文 未知"，不显示 `0`/`-`。
- `free: null`（zero_price/unknown）→ 不进免费清单，在"待核验"区，badge 显示"待核验"不是"FREE"。

### 3. `free` 也三态

`free: true / false / null`，`null` = 没证据，**页面不把它当免费也不当付费**，归"待核验"。

---

## 四、时间字段：拆"抓取"和"实测"

现在 `last_verified` 其实是**抓取时间**（`status: declared` 无实测），卡片却写"验证"。拆：

```yaml
last_fetched: 2026-10-09     # ← 最后抓取(目录/接口拉取时间), declared 条目只有这个
last_probed: null            # ← 最后实测(真发请求验证), 只有 status=probed 才有
```

- `status: declared`（厂商声明/目录抓取）→ 卡片显示 **"抓取 2026-10-09"**，**不显示"验证"**。
- `status: probed`（探测员真发了请求）→ 卡片显示 **"实测 2026-10-09"**。
- 页面统一：有 `last_probed` 显示"实测 X"，否则显示"抓取 X（未实测）"。

---

## 五、首页数字统一（三档，自动生成）

现在"68 总数 / 68 免费 / 13 渠道"自相矛盾（总数=免费因为总闸；13 是文件数但只有 5 家有数据）。统一成：

```
已收录(有详情, 可路由)  N   ← free_type ∈ {permanent,trial,promo} 且在正本有详情的模型数
目录发现(待核验)        M   ← 目录里 free_type=zero_price/unknown 或 apply-key 厂商的模型
已实测(probed)          K   ← status=probed 的模型数(没实测就是 0)
```

- 三个数都由数据算，**不写死**。
- "渠道"数 = **有数据的厂商数**（`len(providers 有 models)`），不是 yaml 文件数。
- 删掉无意义的"总数=免费"那档。

---

## 六、安全修正（随本设计一起做）

1. **`https:` 白名单**：`register_url`/`apply_url`/`provider_home`/`pricing_url` 进 `href` 前过 `safeUrl()`，非 `https:`（含 `javascript:`）一律回 `#`。
2. **去内联 onclick 注入**：`regClick('...')`/`reportFor('...')` 现在把 provider/id 拼进 JS 字符串（`esc` 不转单引号）→ 改 `data-*` 属性 + `addEventListener`（点赞按钮已是这写法）。
3. **`esc()` 补单引号**：转义 `'` 防属性逃逸。
4. **刷新降频**：60s `?t=Date.now()`+`no-store` → 改 5 分钟，且带版本号文件而非每次 no-store 打 Pages。
5. **查重修 bug**：`seen[url]` 拿 URL 比模型 ID 永远不中 → 端点唯一键 = `provider + "/" + model_id`，且查重也比对**目录里的厂商域名**。

---

## 七、落地清单（A 的代码改动）

- [ ] `free_type` 枚举 + `derive_free()` 推导（`updater.py`/`enrich.py` 判定逻辑改）
- [ ] `_caps` 三态（保留 None，不吞 false）
- [ ] `last_fetched` / `last_probed` 拆分，卡片显示改"抓取/实测"
- [ ] 首页数字改 已收录/目录发现/已实测（动态算）
- [ ] 安全：`safeUrl()` + 去内联 onclick + `esc` 补引号 + 降频
- [ ] 查重：端点唯一键 `provider+id`、查目录域名
- [ ] 页面：`free_type` 待核验区、能力"未知"显示、`free_type` badge