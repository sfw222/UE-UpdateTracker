# AGENTS.md — UE-UpdateTracker

通过 GitHub Actions 监控 Unreal Engine 私有仓库的更新，由 AI（智谱 GLM）进行摘要并发布到 Discussion/Slack/Discord 的工具。

## 项目结构

```
scripts/main.py          # 全部逻辑（单文件、函数式、无类）
prompts/report_prompt.md # 发给 GLM 的 Prompt 模板（填充 {report_language}, {aggregated_commits}）
requirements.txt         # PyGithub, openai, python-dotenv, tzdata, requests
```

## 命令

```bash
pip install -r requirements.txt
python scripts/main.py   # 需要: UE_REPO_PAT, ZHIPU_API_KEY + 通知目标环境变量
```

## 架构要点

- 所有分支的提交在过滤后 **一次性批量发送给 GLM**（不是逐条调用 API）
- `filter_commit()` 过滤 Merge 空提交 / 纯文档 / 纯本地化 / 单文件 typo 修复
- `process_branch()` 编排分支级别的 fetch → filter → analyze，失败隔离（一个分支的错误不影响其他分支）
- `_build_combined_report()` 将各分支报告以 H2 标题 + `---` 分隔符合并
- 通知渠道：Discussion（GraphQL）、Slack（Webhook，3000 字符限制分块）、Discord（Webhook，4096 字符限制分条发送）

## 重要约束

- **不将提交差异发送给 AI**（遵守 Epic Games 许可协议）。仅发送提交信息和文件路径。
- Discussion 发布为主动选择加入（需同时设置 `DISCUSSION_REPO` + `DISCUSSION_REPO_PAT`）。有意不回退到 `GITHUB_TOKEN`（防止误发布到公开仓库）。
- 如果未配置任何通知目标，脚本以 `sys.exit(1)` 退出。
- 重复提交（如 cherry-pick 出现在多个分支）仅警告，不去重。
- 无状态执行：每次运行获取最近 24 小时的提交（无持久化存储）。

## 命名规范

- 函数: `snake_case`，内部辅助函数以 `_` 前缀（如 `_run_graphql_query`, `_chunk_text`）
- 日志输出: 直接使用 `print()`（不使用 `logging` 模块）
- 字符串格式化: f-string

## CI/CD

- `.github/workflows/main.yml` — 每天 23:00 UTC 定时执行 + `workflow_dispatch` 手动触发
- `.github/workflows/keepalive.yml` — 防止 60 天无操作后定时任务被自动禁用（空提交）
- 依赖管理: Dependabot（`pip`，每周一）

详细设置步骤请参考 [README.md](README.md)。
