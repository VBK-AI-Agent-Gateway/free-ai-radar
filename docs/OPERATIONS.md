# 运维手册(大白话)

## 仓库 Secrets(必须配)
GitHub -> Settings -> Secrets and variables -> Actions -> New repository secret:

| 名字 | 用途 | 谁能读 |
| --- | --- | --- |
| TELEGRAM_BOT_TOKEN | 推送通知 | 只有 publish job |
| TELEGRAM_CHAT_ID | 推送目标 | 只有 publish job |
| GROQ_API_KEY | 探测密钥(可选) | 只有 probe job |
| PROBE_API_KEY | 探测密钥(可选) | 只有 probe job |

**外部 PR 的 workflow 默认拿不到这些 secrets。**

## 权限最小化
- test / collect / probe / publish 四个 job,publish 才有 `contents: write`。
- 抽取员(阶段 1 加)两个密钥都读不到。
- 守卫在 publish 提交前跑,拦截 key 和提示注入,不过闸整个 run 失败。

## 你拍板的数(已生效)
- 每天最多调 AI: 100 次 -> `config/budgets.yaml: ai.daily_call_limit`
- 每家每天最多探测: 2 次 -> `config/budgets.yaml: probe.daily_runs_per_provider`(prober 本地计数兜底)

## 手动触发
Actions -> radar -> Run workflow。首次建议手动跑一遍看日志。

## 重大变化人审
核验员 `python agents/verdict.py --major-quota-pct N` 退出码 3 = 需要批准;
批准后手动推: `TELEGRAM_BOT_TOKEN=.. TELEGRAM_CHAT_ID=.. python agents/publisher.py --message "..."`。
