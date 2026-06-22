# Unreal Engine 更新追踪

[日本語版はこちら](https://github.com/pafuhana1213/UnrealEngine-UpdateTracker)

本项目是一个自动化工具，定期监控 Unreal Engine 私有 GitHub 仓库的更新，使用 AI（Google Gemini）对重要变更（如新功能和规格变更）进行摘要，并以报告形式发布到 GitHub Discussions。

<table><tr><td>
<img width="644" alt="image" src="https://github.com/pafuhana1213/Screenshot/blob/master/Report_sample_jp.png" />
</td></tr></table>

注意：此图片为报告示例，其内容均为虚构数据，不代表 Unreal Engine 的实际更新。

## 🚀 快速开始

1. **Fork 本仓库**（点击右上角 Fork 按钮）
2. **设置 Secrets**（`Settings` > `Secrets and variables` > `Actions`）：
   - `UE_REPO_PAT`：能访问 `EpicGames/UnrealEngine` 私有仓库的 [Personal Access Token](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
   - `GEMINI_API_KEY`：从 [Google AI Studio](https://aistudio.google.com/app/apikey) 获取的 API 密钥
3. **配置通知目标**（至少设置一种）：
   - **GitHub Discussion**：`DISCUSSION_REPO`（目标仓库，格式 `用户名/仓库名`）+ `DISCUSSION_REPO_PAT`（具有 Discussions 写入权限的 PAT）
   - **Slack**：`SLACK_WEBHOOK_URL` + `SLACK_CHANNEL`
   - **Discord**：`DISCORD_WEBHOOK_URL`
4. （可选）在 `Variables` 中设置 `REPORT_LANGUAGE` 为 `Chinese`

## 订阅最新报告

无需自行搭建此工具，你也可以订阅已生成的最新报告。
以下仓库每天定时将生成的报告发布到 GitHub Discussions。

[**订阅 UnrealEngine-UpdateTrackerReport 仓库**](https://github.com/pafuhana1213/UnrealEngine-UpdateTrackerReport)

注意：此报告仓库为私有，查看需要具有 [访问 Unreal Engine 源代码仓库权限的 GitHub 账号](https://www.unrealengine.com/zh-CN/ue-on-github)。

## 主要功能

- **自动更新检查**：通过 GitHub Actions，每天定时（北京时间 7:00 / UTC 23:00）或手动获取 UE 仓库的最新提交。
- **多分支并行追踪**：默认同时追踪 `ue5-main` 和 `ue6-main`（可通过 `UE_BRANCHES` 更改）。
- **AI 摘要**：Gemini API 分析提交内容，按"新功能""重大变更""性能优化""Bug 修复"等类别分类并摘要。
- **Discussion 发布**：将生成的报告以"Unreal Engine 每日报告"的形式发布到仓库的 GitHub Discussions。各追踪分支（UE5 / UE6 等）在同一报告内按标题分开并列展示。
- **Slack 通知**：可同时将报告通知到指定的 Slack 频道。
- **Discord 通知**：可同时将报告通知到指定的 Discord 频道。

## 运行方式

- **自动运行**：按设定计划（默认每天北京时间 7:00 / UTC 23:00）自动执行工作流。
- **手动运行**：在仓库的 `Actions` 标签页选择 `Unreal Engine 更新追踪` 工作流，点击 `Run workflow` 按钮手动触发（手动运行仅限仓库管理员）。
  - **Report Language**：输入报告输出语言（如 `Chinese`、`Japanese`、`English`）。默认为 `Japanese`。
  - **Commit Scan Limit**：手动运行时扫描的最近提交数量。默认为过去 24 小时。
  - **UE Branches**：以逗号分隔指定追踪分支（如 `ue5-main,ue6-main`）。默认为 `ue5-main,ue6-main`。
  - **Discussion Category**：报告发布到的 Discussion 分类名称。默认为 `Daily Reports`。
  - **Gemini Model**：分析使用的 AI 模型名称。默认为 `gemini-3.5-flash`。
  - **Slack Webhook URL**：临时使用的 Slack Webhook URL，会覆盖 Secret 中的值。
  - **Slack Channel**：临时使用的 Slack 频道名称，会覆盖 Secret 中的值。
  - **Discord Webhook URL**：临时使用的 Discord Webhook URL，会覆盖 Secret 中的值。

- **修改默认值**：
  定时运行和手动运行的默认值可在仓库的 Variables 中修改。在 `Settings` > `Secrets and variables` > `Actions` 的 `Variables` 标签页中设置以下内容。
  - `REPORT_LANGUAGE`：默认报告语言（如 `Chinese`）。
  - `DISCUSSION_CATEGORY`：默认发布分类名称（如 `Daily Reports`）。
  - `GEMINI_MODEL`：默认使用的 AI 模型。默认为 `gemini-3.5-flash`。如需更高质量，可改为 `gemini-2.5-pro` 等。
  - `REPORT_TIMEZONE`：报告标题日期的时区。默认为 `Asia/Tokyo`。中国用户可设为 `Asia/Shanghai`。
  - `UE_BRANCHES`：以逗号分隔指定监控分支（如 `ue5-main,ue6-main` 或 `release`）。默认为 `ue5-main,ue6-main`。指定多个时，各分支的报告在同一个帖子内按标题分开并列展示（Discord 由于字数限制会自动拆分为多条消息）。此外，传统的单分支 `UE_BRANCH` Variable 仍可兼容使用（仅在 `UE_BRANCHES` 未设置时被引用）。

## 自定义

### 修改报告格式

报告的类别、摘要风格和整体结构由发送给 AI 的提示词（Prompt）决定。

如果需要更详细的报告，或想强调特定信息等格式调整，可直接编辑仓库根目录下的 `prompts/report_prompt.md` 文件。修改此文件即可自定义 AI 行为，无需改动 Python 代码。

## 支持开发

如果这个工具对你的每日 UE 跟进有所帮助，我会很高兴。

这个工具由个人以兴趣和实用兼顾的方式开发，自掏腰包承担咖啡费用和 API 使用费 ☕
如果你喜欢它，可以通过 GitHub Sponsors 支持我，这将是开发的莫大动力。

[💖 **在 GitHub Sponsors 上支持**](https://github.com/sponsors/pafuhana1213)

## 重要：安全运行建议

Unreal Engine 的更新历史是基于 Epic Games 许可协议、仅允许授权账号访问的机密信息。为防止意外信息泄露，此工具在未配置任何通知目标时将停止运行。

强烈建议将报告发布目标（`DISCUSSION_REPO`、Slack 频道、Discord 频道）设置为仅限具有 Unreal Engine 源代码仓库 Fork 权限或同等访问权限的成员参与的私有空间。这样可以在遵守许可协议的前提下安全地共享信息。

## 许可和使用注意事项

使用本工具前，请务必阅读以下内容。

- **用户责任**：本工具已谨慎设计以遵守 Unreal Engine 许可协议，但最终的运行责任由用户承担。特别是报告发布目标（`DISCUSSION_REPO`）务必指定为限制访问的私有仓库。发布到公开仓库可能构成许可违规。

- **API 密钥和计费**：
  - 本工具使用 Google Gemini API，根据使用量可能产生费用。
  - Fork 本仓库使用时，Fork 方所有者自行承担其 API 密钥的全部计费责任。
  - 为确实遵守 Unreal Engine 条款，强烈建议使用发送数据不会用于 AI 训练的 API 密钥。

- **设计安全性**：
  - 为降低许可违规风险，本工具在向 AI 提供信息时，绝不发送 Unreal Engine 的源代码或代码差异（diff）。分析对象仅为提交信息和变更文件路径。

- **运行注意事项**：
  - 本脚本将根据设置实际发布到 GitHub Discussions。测试运行时请注意。
  - 各 API 存在使用限制（速率限制）。
