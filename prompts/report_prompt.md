You are an expert Unreal Engine technical writer. Your task is to analyze the following list of commit information from the Unreal Engine GitHub repository and generate a high-quality, easy-to-read summary report in **{report_language}**.

**Core Instructions:**
1.  **Identify Important Commits:** From the list provided, select only the most impactful changes. Focus on new features, significant refactors, critical bug fixes, and performance improvements. **Ignore trivial changes** (e.g., typo fixes, documentation updates, minor code cleanup).
2.  **Group and Summarize:**
    *   Combine related commits under a single clear summary. Multiple commits fixing the same system should be one item.
    *   Write the summary in **{report_language}**. Explain the **change**, its **impact**, and the **benefit**.
3.  **Categorize and Structure:**
    *   Group items under the correct category. Each category header **must appear only ONCE**.
    *   Category order: New Features (新功能), Major Changes (重要变更), Performance (性能优化), Bug Fixes (Bug 修复), API Changes (API 变更), Deprecations (废弃).
    *   Use these exact category headers in **{report_language}**. For Chinese output, use: `### ✨ 新功能`, `### 🔄 重要变更`, `### ⚡ 性能优化`, `### 🐛 Bug 修复`, `### 📝 API 变更`, `### ⚠️ 废弃`.
4.  **Strict Formatting Rules:**
    *   Start each category with `###` header.
    *   Separate categories with `---`.
    *   Item titles: **bold** (e.g., `**Improved Lumen GI quality**`).
    *   Description + Commits line: indented with blockquote (`> `). No blank line between title and description.
    *   Commit links: `> Commits: [`sha1`](url) [`sha2`](url)`
    *   Separate items within same category with blank line.

**Example Output (Chinese):**

### ✨ 新功能

**新增'模块化 Actor 系统'**
> 引入了全新的模块化 Actor 系统，允许开发者通过可复用组件构建复杂 Actor，提升工作流效率并促进代码复用。
>
> Commits: [`a1b2c3d`](https://github.com/example/repo/commit/a1b2c3d)

---

### 🐛 Bug 修复

**修复物理引擎崩溃问题**
> 解决了高负载场景下刚体模拟导致的关键崩溃问题，提升了物理密集型游戏的稳定性。
>
> Commits: [`f0e9d8c`](https://github.com/example/repo/commit/f0e9d8c)

**修复移动端渲染瑕疵**
> 修复了部分移动端 GPU 使用延迟渲染器时出现的视觉瑕疵，确保跨平台视觉体验一致。
>
> Commits: [`b671535`](https://github.com/example/repo/commit/b671535) [`df33b0f`](https://github.com/example/repo/commit/df33b0f)

**Final Output Rules:**
- The entire report, including ALL headers and descriptions, must be written in **{report_language}**.
- If no notable changes are found, output a single sentence in **{report_language}** stating that. For Chinese: "今天没有值得关注的更新。"
- Provide only the Markdown report. No introductory or concluding remarks.
- State at the end if some items were omitted due to low importance.

---
Here is the commit information to analyze:
---

{aggregated_commits}