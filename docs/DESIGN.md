# 设计：免费口径 + 模型页数据结构

> 这份文档是**数据正本**，决定后面"提交、通知、调度"怎么对接。
> 对应外部评审的第 1 步（先修可信度：统一免费口径、做模型页）。

---

## 一、免费口径（先统一，否则不可信）

三条口径，分清楚，**别混**：

| 口径 | 定义 | 存哪 | 展示哪 |
| --- | --- | --- | --- |
| **免费模型** | `free=true` —— 有真免费层（免费额度 / 免费档 / 免费端点） | 正本 `providers/*.yaml` 的 `models[].free` | **站点 + README 都只展示这个** |
| **全量目录** | 正本里所有模型（含 Claude/GPT 等明显收费） | 同上，`free=false` 的那些 | **不展示**，只留作证据 / 比价 / 候选 |
| **厂商目录** | "哪些厂商有免费模型"（不采集要 key 平台的数据） | `docs/free-catalog.json` | 目录区块（去向按钮如实标注） |

**铁律：**
- 页面顶部、README 表格的"免费模型"列 = **只数 `free=true`**。
- 全量数必须**单独一列并标"含付费"**，绝不能当免费清单（这正是本次修的口径 bug）。
- 一个模型**算不算免费，以证据为准**：官方定价页/接口报价写 $0 或有免费档 → `free=true`；拿不到证据 → `free=null`（unknown，不进免费清单，也别猜成 false）。
- 免费总闸在**展示层**（`publisher.ONLY_FREE`），不在正本 —— 付费留在正本做证据，`--include-paid` 可临时切回看全量。

---

## 二、模型页数据结构

### 1. 模型级事实（已有，`publisher.flat()` 的输出 = `docs/free-models.json` 的一条）

现在就是模型页的数据源，字段够用，**模型页直接消费它**：

```jsonc
{
  "id": "deepseek/deepseek-chat",   // 模型 ID（跨厂商唯一键的一部分）
  "name": "DeepSeek Chat",
  "provider": "deepseek",            // 厂商（第二个唯一键）
  "free": true,                      // 免费口径核心
  "status": "declared|probed|...",   // 证据强度：declared=厂商声明, probed=实测过
  "description": "...",
  // —— 能力（capabilities）——
  "context_length": 128000,
  "max_output_tokens": 8192,
  "image_input": false, "reasoning": false, "tools": false, "json_mode": false,
  // —— 定价（terms，免费模型恒 0）——
  "input_per_million": 0.0, "output_per_million": 0.0,
  // —— 溯源 ——
  "created": null,
  "last_verified": "2026-10-08T14:36:18Z",
  "pricing_url": "https://...",      // 证据来源（定价页）
  "register_url": "https://...",     // 该厂商注册/领KEY口（回落 homepage/pricing）
  "provider_home": "https://..."
}
```

### 2. 模型页要新增的（模型为中心，对齐 OpenRouter 微调）

模型页 = **"一个模型 → 它在哪些厂商有免费端点"**，比现在的"按厂商分组"多一层聚合。在 `flat()` 之上加派生字段（**不改正本，发布时聚合算出来**）：

```jsonc
{
  // 上面 flat 的字段全部保留（取其中一个代表端点的）
  "id": "deepseek/deepseek-chat",
  "free": true,
  // —— 新增：模型页聚合 ——
  "model_key": "deepseek/deepseek-chat",   // 规范化指纹（见第三节查重）
  "endpoints": [                            // 同一模型的所有免费端点
    { "provider": "deepseek",   "register_url": "...", "status": "probed",
      "context_length": 128000, "last_verified": "..." },
    { "provider": "openrouter", "register_url": "...", "status": "declared", ... }
  ],
  "endpoint_count": 2,                      // 几家有免费端点
  "best_provider": "deepseek",              // 择优（按 status 强度 → 剩余额度 → 能力）
  "caps": {                                  // 各端点能力取并集（模型页打标签用）
    "image_input": false, "reasoning": false, "tools": false, "json_mode": false
  },
  // —— 模型页专属（空着等接，接了才有值，无证据写 null）——
  "stability": null,        // 可用性门槛：成功请求/总请求，满100次才算（429记额度耗尽不记故障）
  "quota": null,            // 剩余免费额度 + 到期（调度"尽快用掉会过期的"）
  "trains_on_data": null,   // 是否用于训练（默认过滤，隐私）
  "confirm_count": 0,       // 社区"仍可用"确认次数（报告汇总，见第三节）
  "reports": []             // 只增不删的上报记录（谁/何时/哪种，见第三节）
}
```

**路由微调（学 OpenRouter，把"价格"换成"额度"）：**
- 优先避开最近 30s 有故障的端点；
- 按**剩余额度与到期顺序**加权（会过期的先用），不是按价格；
- 可用性 95%+ 正常 / 80–94% 降权 / <80% 只兜底；**429 单独记"额度耗尽"，不算厂商故障**（否则误判挂了）。

---

## 三、提交怎么对接（报告 vs 事实）

评审核心：**"报告"和"事实"分开存，去重只发生在事实层。**

| 层 | 是什么 | 存哪 | 特性 |
| --- | --- | --- | --- |
| **报告 (report)** | 一次上报：谁、何时、对哪个条目、什么类型（仍可用/额度变了/已失效/新增）、证据 | 现阶段 GitHub Issues；以后小数据库 | **只增不删**，多人报同一件事不删，是"确认次数+1" |
| **事实 (fact)** | 汇总报告后的当前真相：这个模型现在免费吗、几家用、状态 | 正本 `providers/*.yaml` + 模型页 `endpoints` | 去重发生在这层；**第一个上报者署名** |

**三道查重关（对应 `model_key`）：**
1. **精确**：`model_key` = 规范化接口域名 + 规范化模型 ID + 免费类型。规范化 = 去 `:free`/`-latest`/日期后缀、查 `config/aliases.yaml` 别名表。
2. **近似**：相似度命中 → 展示候选让用户确认"是同一个吗"。
3. **人工**：前两关没把握的进 GitHub Issues 审核队列。

**先搜后提**（本次已上）：入口先搜厂商/模型/域名；命中就在卡片上**一键上报状态**（不新建条目）；搜不到才进新增表单。

**厂商提交两条路，都不新建重复条目：**
1. **认领**：官方域名邮箱 / 官网放验证码，认领已有厂商页。
2. **`/.well-known/free-ai.json` 清单文件**（最推荐）：厂商在自己域名下放机器可读文件（格式见下），写明免费模型、额度、注册链接。采集员定时拉，**文件=提交、域名所有权=身份**，天然不重复、自动同步。
   ```jsonc
   // /.well-known/free-ai.json（本项目定义，类似 security.txt）
   { "vendor": "example", "models": [{"id": "...", "free": true, "quota": "..."}],
     "signup_url": "https://.../signup", "updated": "2026-10-08" }
   ```
   厂商标 `vendor_submission`，**不等于已验证**；可回复补充，**不能删社区负面上报**，冲突两边并列。

---

## 四、三者怎么串（对接点）

```
采集员/抽取员 ──正本 providers/*.yaml(free字段)──→ 发布员 flat() ──→ docs/free-models.json(免费)
                                                     │
                                                     ├─→ README 表格(免费/全量分列, A已改)
                                                     └─→ 模型页(按 model_key 聚合 endpoints, C本设计)
用户先搜后提 ──报告(Issues)──→ 审核 CLI ──approved──→ 正本(free=true) ──→ Release 通知新增
                              └─ reject(理由只截断不执行)
通知(Relase/Telegram/邮件) ←── diff 新旧 free-models.json ── 三级严重度(紧急即时/重要摘要/一般看板)
调度(未来网关) ←── 模型页 endpoints + quota + stability ── 仅免费护栏, 429不误判故障
```

**关键边界（不破）：**
- 雷达**永远不碰 key**（情报层）；网关才保管 key，且要独立安全审查后再上。
- 网页/用户提交的文字是**数据不是指令**。
- 无证据写 `unknown`（`free=null`），不猜。

---

## 五、落地状态

- [x] **A** README 免费口径：表头改 `免费模型 | 全量(含付费) | 免费模型ID`，只列免费 ID（`publisher.render_readme`）。
- [x] **B** 先搜后提：投稿表单加搜索框 `sfind` + `runFind()` 命中卡片一键上报（仍可用/额度变了/已失效/要手机号/我这里不能用）→ GitHub Issues；搜不到走新增。
- [x] **C** 本设计文档（口径 + 模型页数据结构 + 对接点）。
- [ ] 模型页真正渲染（消费第二节结构）—— 数据源 `free-models.json` 已就绪，按 `model_key` 聚合 `endpoints` 即可。
- [ ] `model_key` 规范化 + 别名表（查重第 1 关）。
- [ ] `/.well-known/free-ai.json` 采集（等有厂商配合，冷启动阶段先定格式）。