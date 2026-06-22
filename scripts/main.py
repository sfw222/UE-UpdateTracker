# main.py
# This script will contain the core logic for checking Unreal Engine updates.
import os
import re
import sys
import time
import requests
from github import Github
from github.GithubException import UnknownObjectException
from google import genai
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

UE_REPO_NAME = "EpicGames/UnrealEngine" # Target repository
raw_limit = os.environ.get("COMMIT_SCAN_LIMIT") # Keep for manual override
COMMIT_SCAN_LIMIT = int(raw_limit) if raw_limit and raw_limit.isdigit() else None

# Timeout (seconds) for outbound HTTP calls (GitHub GraphQL, Slack, Discord).
REQUEST_TIMEOUT = 30


def get_target_branches():
    """Returns the list of (label, branch) pairs to track.

    Reads UE_BRANCHES (comma-separated, e.g. "ue5-main,ue6-main"). Falls back to
    the legacy single UE_BRANCH for backward compatibility, then to a default of
    both ue5-main and ue6-main. The label is derived from the first '-'-delimited
    segment, uppercased (ue5-main -> UE5, ue6-main -> UE6).
    """
    raw = os.environ.get("UE_BRANCHES") or os.environ.get("UE_BRANCH") or "ue5-main,ue6-main"
    branches = [b.strip() for b in raw.split(",") if b.strip()]
    return [(branch.split("-")[0].upper(), branch) for branch in branches]


def fetch_new_commits(github_client, branch):
    """
    Fetches new commits from the UE repo for the given branch.
    - If COMMIT_SCAN_LIMIT is set (manual run), it fetches that many recent commits.
    - Otherwise (scheduled run), it fetches commits from the last 24 hours.
    """
    print(f"正在从 {UE_REPO_NAME} 获取分支 {branch} 的提交...")
    try:
        repo = github_client.get_repo(UE_REPO_NAME)
        print("成功访问仓库。")

        if COMMIT_SCAN_LIMIT:
            print(f"手动覆盖：正在获取分支 '{branch}' 的最新 {COMMIT_SCAN_LIMIT} 条提交。")
            commits = repo.get_commits(sha=branch)
            new_commits = list(commits[:COMMIT_SCAN_LIMIT])
            new_commits.reverse() # Oldest to newest
        else:
            since_time = datetime.now(timezone.utc) - timedelta(hours=24)
            print(f"定时运行：正在获取分支 '{branch}' 自 {since_time.isoformat()} UTC 以来的提交...")
            commits = repo.get_commits(sha=branch, since=since_time)
            new_commits = list(commits)
            # Commits from .get_commits(since=...) are already in chronological order.

        print(f"发现 {len(new_commits)} 条新提交。")
        return new_commits

    except UnknownObjectException:
        print(f"错误：仓库 '{UE_REPO_NAME}' 未找到。请检查 PAT 权限。")
        return None
    except Exception as e:
        print(f"获取提交时发生意外错误：{e}")
        return None


def filter_commit(commit):
    """
    Performs primary filtering to exclude obviously unimportant commits.
    Returns True if the commit is potentially important, False otherwise.
    """
    commit_message = commit.commit.message.lower()
    # commit.files is a PaginatedList; materialize it once so we don't trigger a
    # fresh paginated API fetch on every check below. (PaginatedList also has no
    # __bool__/__len__, so `not commit.files` would always be False.)
    files = list(commit.files)
    # Ignore merge/empty commits with no file changes
    if not files:
        return False
    # Ignore commits that only touch documentation
    if all(f.filename.startswith("Documentation/") for f in files):
        return False
    # Ignore localization-only changes
    if all("Localization/" in f.filename for f in files):
        return False
    # Ignore simple typo fixes
    if "typo" in commit_message and len(files) == 1:
        return False
    return True


def analyze_commits_in_bulk(client, model_name, commits, report_language="Japanese"):
    """
    Analyzes a list of commits in bulk with the Gemini API and returns a formatted Markdown report.
    """
    print(f"正在聚合 {len(commits)} 条提交以进行批量分析...")
    
    commits_data = []
    for commit in commits:
        # IMPORTANT: To comply with Epic Games' license and prevent leaking sensitive information,
        # DO NOT include file contents or diffs in the data sent to the AI.
        # Only commit messages and file paths are used.
        file_list = "\n".join([f"- {file.filename}" for file in commit.files])
        commit_info = f"""---
提交: {commit.sha[:7]}
URL: {commit.html_url}
信息:
{commit.commit.message}
变更文件:
{file_list}
"""
        commits_data.append(commit_info)
    
    aggregated_commits = "\n".join(commits_data)

    try:
        # Load the prompt from the external file
        with open("prompts/report_prompt.md", "r", encoding="utf-8") as f:
            prompt_template = f.read()
        
        prompt = prompt_template.format(
            report_language=report_language,
            aggregated_commits=aggregated_commits
        )

        print(f"  > 正在向 Gemini 发送 {len(commits)} 条提交的聚合提示词（语言：{report_language}）...")

        # Retry transient errors (503, 429, etc.) up to 3 times with backoff
        max_retries = 3
        last_error = None
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(model=model_name, contents=prompt)
                break  # Success — exit retry loop
            except Exception as e:
                last_error = e
                err_str = str(e)
                if attempt < max_retries - 1 and ("503" in err_str or "429" in err_str or "UNAVAILABLE" in err_str or "RESOURCE_EXHAUSTED" in err_str):
                    wait = 5 * (2 ** attempt)  # 5, 10, 20 seconds
                    print(f"  ⚠ Gemini 暂时不可用（{e}），{wait}s 后重试（{attempt + 2}/{max_retries}）...")
                    time.sleep(wait)
                    continue
                raise

        if last_error is not None:
            raise last_error

        # --- Start of Detailed Logging ---
        print(f"--- 批量响应 ---\n{response.text}\n--------------------\n")
        # --- End of Detailed Logging ---

        print(f"  < 已收到 Gemini 的批量响应。")
        
        return response.text

    except FileNotFoundError:
        print("致命错误：未找到 prompts/report_prompt.md。")
        return None
    except Exception as e:
        print(f"AI 批量分析提交时出错：{e}")
        return None


def _run_graphql_query(query, variables, pat):
    """A helper function to run a GraphQL query."""
    headers = {"Authorization": f"bearer {pat}"}
    response = requests.post(
        'https://api.github.com/graphql',
        json={'query': query, 'variables': variables},
        headers=headers,
        timeout=REQUEST_TIMEOUT
    )
    if response.status_code == 200:
        result = response.json()
        if "errors" in result:
            raise Exception(f"GraphQL query failed: {result['errors']}")
        return result
    else:
        raise Exception(f"Query failed with status code {response.status_code}: {response.text}")

def get_repository_and_category_ids(repo_name, pat, category_name="日报"):
    """Gets the repository and discussion category IDs using the GraphQL API."""
    owner, name = repo_name.split('/')
    query = """
    query GetRepoAndCategory($owner: String!, $name: String!) {
      repository(owner: $owner, name: $name) {
        id
        discussionCategories(first: 10) {
          nodes {
            id
            name
          }
        }
      }
    }
    """
    variables = {"owner": owner, "name": name}
    result = _run_graphql_query(query, variables, pat)
    
    repo_id = result["data"]["repository"]["id"]
    category_id = None
    for category in result["data"]["repository"]["discussionCategories"]["nodes"]:
        if category["name"] == category_name:
            category_id = category["id"]
            break
            
    if not category_id:
        # Fallback to the first category if the named one isn't found
        categories = result["data"]["repository"]["discussionCategories"]["nodes"]
        if categories:
            fallback_category = categories[0]
            category_id = fallback_category["id"]
            print(f"警告：未找到 Discussion 分类 '{category_name}'。回退为 '{fallback_category['name']}'。")
        else:
            raise Exception(f"仓库中未找到任何 Discussion 分类。")
        
    return repo_id, category_id

def create_discussion(repo_name, title, body, pat, category_name="日报"):
    """Creates a new GitHub Discussion using the GraphQL API."""
    print("---")
    print("正在通过 GraphQL 创建 GitHub Discussion...")
    try:
        repo_id, category_id = get_repository_and_category_ids(repo_name, pat, category_name)
        print(f"找到仓库 ID：{repo_id}")
        print(f"找到分类 ID：{category_id}（分类名：'{category_name}'）")

        mutation_query = """
        mutation CreateDiscussion($repoId: ID!, $categoryId: ID!, $title: String!, $body: String!) {
          createDiscussion(input: {
            repositoryId: $repoId,
            categoryId: $categoryId,
            title: $title,
            body: $body
          }) {
            discussion {
              url
            }
          }
        }
        """
        variables = {
            "repoId": repo_id,
            "categoryId": category_id,
            "title": title,
            "body": body
        }

        result = _run_graphql_query(mutation_query, variables, pat)
        discussion_url = result["data"]["createDiscussion"]["discussion"]["url"]
        print(f"成功创建 GitHub Discussion：{discussion_url}")
        return True

    except Exception as e:
        print(f"创建 Discussion 时发生错误：{e}")
        return False


def _github_md_to_slack_mrkdwn(text):
    """Convert the GitHub-flavored Markdown report into Slack mrkdwn.

    Slack mrkdwn differs from GitHub Markdown: it has no '#' headers, uses
    *bold* (single asterisk), and links are <url|text> instead of [text](url).
    """
    lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        # Horizontal rule -> a visual separator (Slack mrkdwn has no '---' rule)
        if stripped in ("---", "***", "___"):
            lines.append("───────────────")
            continue
        # Headers (#, ##, ###...) -> a bold line
        m = re.match(r"^\s*#{1,6}\s+(.*)$", line)
        if m:
            lines.append(f"*{m.group(1).strip()}*")
            continue
        lines.append(line)
    converted = "\n".join(lines)
    # [text](url) -> <url|text>
    converted = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r"<\2|\1>", converted)
    # **bold** -> *bold*
    converted = re.sub(r"\*\*([^*]+)\*\*", r"*\1*", converted)
    return converted


def _chunk_text(text, limit):
    """Split text into <=limit-char chunks at line boundaries.

    Used by both Slack (section text fields capped at 3000 chars) and Discord
    (embed descriptions capped at 4096 chars); callers pass an appropriate limit
    with a safety margin. A single over-long line is hard-split as a last resort.
    """
    chunks = []
    current = ""
    for line in text.split("\n"):
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        candidate = line if not current else current + "\n" + line
        if len(candidate) > limit:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def send_slack_notification(webhook_url, channel, message_text, title):
    """Sends a notification to a Slack channel via a webhook.

    The full report can easily exceed Slack's 3000-char per-section limit, so we
    convert it to mrkdwn and split it across multiple 'section' blocks.
    """
    print("---")
    print("正在发送 Slack 通知...")
    try:
        chunks = _chunk_text(_github_md_to_slack_mrkdwn(message_text), 2900)

        # Slack allows at most 50 blocks per message. Reserve room for the header,
        # the divider, and (when truncating) the truncation notice, so the total
        # stays <= 50: 47 sections + header + divider + notice = 50.
        MAX_SECTION_BLOCKS = 47
        truncated = len(chunks) > MAX_SECTION_BLOCKS
        if truncated:
            chunks = chunks[:MAX_SECTION_BLOCKS]

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": title[:150], "emoji": True}
            },
            {"type": "divider"},
        ]
        for chunk in chunks:
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": chunk}})
        if truncated:
            blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "_…（消息已截断）_"}})

        payload = {
            "channel": channel,
            "username": "UE Update Tracker",
            "icon_emoji": ":robot_face:",
            "text": f"*{title}*", # Fallback text for notifications
            "blocks": blocks
        }

        response = requests.post(webhook_url, json=payload, timeout=REQUEST_TIMEOUT)
        response.raise_for_status() # Raise an exception for bad status codes
        print("成功发送 Slack 通知。")
        return True
    except requests.exceptions.RequestException as e:
        print(f"发送 Slack 通知时发生错误：{e}")
        return False


def _post_discord_message(webhook_url, payload):
    """POST a single Discord webhook message, honoring 429 rate limits.

    Discord returns 429 with a Retry-After header (seconds) when rate limited;
    we wait and retry once. Returns True on success, False otherwise.
    """
    for attempt in range(2):
        response = requests.post(webhook_url, json=payload, timeout=REQUEST_TIMEOUT)
        if response.status_code == 429 and attempt == 0:
            retry_after = response.headers.get("Retry-After", "1")
            try:
                wait = float(retry_after)
            except ValueError:
                wait = 1.0
            print(f"  Discord rate limited (429). Waiting {wait}s before retry...")
            time.sleep(min(wait, 30))
            continue
        response.raise_for_status()
        return True
    return False


def send_discord_notification(webhook_url, message_text, title):
    """Sends a notification to a Discord channel via a webhook.

    The full report can exceed Discord's 4096-char embed description limit, so we
    split it across multiple sequential messages. Returns True only if every
    chunk posts successfully, so a partially-delivered report is not silently
    reported as success.
    """
    print("---")
    print("正在发送 Discord 通知...")
    # 3900 keeps a margin under the 4096 embed-description limit, leaving room for
    # the truncation notice appended to the final chunk when we hit the cap.
    chunks = _chunk_text(message_text, 3900)

    # Cap the number of messages to avoid flooding the channel; mark truncation
    # on the last message, mirroring the Slack section cap.
    MAX_MESSAGES = 10
    truncated = len(chunks) > MAX_MESSAGES
    if truncated:
        chunks = chunks[:MAX_MESSAGES]
        chunks[-1] = chunks[-1] + "\n\n…（消息已截断）"

    total = len(chunks)
    all_ok = True
    for i, chunk in enumerate(chunks, start=1):
        embed_title = title if i == 1 else f"{title} ({i}/{total})"
        payload = {
            "username": "UE Update Tracker",
            "avatar_url": "https://i.imgur.com/4M34hi2.png", # A simple robot icon
            "embeds": [
                {
                    "title": embed_title,
                    "description": chunk,
                    "color": 3447003,  # A nice blue color, hex #3498db
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            ]
        }
        try:
            if _post_discord_message(webhook_url, payload):
                # Small delay between sequential posts to ease webhook rate limits.
                if i < total:
                    time.sleep(0.5)
            else:
                all_ok = False
                print(f"  发送 Discord 消息 {i}/{total} 失败。")
        except requests.exceptions.RequestException as e:
            all_ok = False
            print(f"  发送 Discord 消息 {i}/{total} 时发生错误：{e}")

    if all_ok:
        print(f"成功发送 Discord 通知（共 {total} 条消息）。")
    else:
        print("Discord 通知未完成：一条或多条消息发送失败。")
    return all_ok

def process_branch(github_client, ai_client, branch, label, model_name, report_language):
    """Fetch, filter, and analyze commits for a single branch.

    Returns a dict {label, branch, status, body, shas} where status is one of:
      - "ok":    body holds the generated Markdown report
      - "empty": no important commits after filtering (nothing to report)
      - "error": fetch failed or the AI returned no content
    Failures are returned (not raised) so the caller can isolate one branch's
    problem and still report the others.
    """
    new_commits = fetch_new_commits(github_client, branch)
    if new_commits is None:
        print(f"获取分支 '{branch}' 的提交失败。")
        return {"label": label, "branch": branch, "status": "error", "body": None, "shas": []}
    if not new_commits:
        print(f"分支 '{branch}' 没有发现新提交。")
        return {"label": label, "branch": branch, "status": "empty", "body": None, "shas": []}

    important_commits = [commit for commit in new_commits if filter_commit(commit)]
    if not important_commits:
        print(f"过滤后分支 '{branch}' 没有发现重要提交。")
        return {"label": label, "branch": branch, "status": "empty", "body": None, "shas": []}

    print(f"发现 {len(important_commits)} 条可能需要分析的重要提交（分支：'{branch}'）。")
    shas = [commit.sha for commit in important_commits]
    report_body = analyze_commits_in_bulk(ai_client, model_name, important_commits, report_language)
    if not report_body:
        print(f"AI 为分支 '{branch}' 生成报告失败。")
        return {"label": label, "branch": branch, "status": "error", "body": None, "shas": shas}

    return {"label": label, "branch": branch, "status": "ok", "body": report_body, "shas": shas}


def _warn_duplicate_shas(branch_results):
    """Log a warning when the same commit appears on more than one branch.

    UE branches share history, so a cherry-picked/merged commit can land in two
    branches' windows and be summarized twice. We only surface this (no dedupe),
    since deciding which branch 'owns' a shared commit is out of scope.
    """
    seen = {}
    for result in branch_results:
        for sha in result.get("shas", []):
            seen.setdefault(sha, []).append(result["label"])
    dups = {sha: labels for sha, labels in seen.items() if len(labels) > 1}
    if dups:
        print(f"警告：{len(dups)} 条提交出现在多个追踪分支中"
              f"（按分支分别报告，未去重）：")
        for sha, labels in list(dups.items())[:20]:
            print(f"  {sha[:7]}: {', '.join(labels)}")


def _build_combined_report(branch_results, report_language):
    """Concatenate per-branch reports into one document, each under an H2 header.

    'ok' branches contribute their generated report; 'empty' and 'error' branches
    get a short localized placeholder so readers know the branch was checked.
    """
    is_ja = ("japan" in report_language.lower()) or ("日本" in report_language)
    is_zh = ("chinese" in report_language.lower()) or ("中文" in report_language) or ("中国" in report_language)
    
    if is_ja:
        no_update = "_本日の注目すべき更新はありません。_"
        failed_note = "_⚠️ レポート生成に失敗しました。_"
    elif is_zh:
        no_update = "_今天没有值得关注的更新。_"
        failed_note = "_⚠️ 报告生成失败。_"
    else:
        no_update = "_No notable updates today._"
        failed_note = "_⚠️ Failed to generate the report._"

    sections = []
    for result in branch_results:
        header = f"## {result['label']} ({result['branch']})"
        if result["status"] == "ok":
            body = result["body"].strip()
        elif result["status"] == "empty":
            body = no_update
        else:
            body = failed_note
        sections.append(f"{header}\n\n{body}")
    return "\n\n---\n\n".join(sections)


def main():
    """
    Main function to execute the update check.
    """
    print("=============================================")
    print("启动 Unreal Engine 更新检查脚本")
    print("=============================================")
    
    # --- API Setup ---
    print("\n--- 1. 初始化 API ---")
    pat = os.environ.get("UE_REPO_PAT")
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    
    if not pat:
        print("致命错误：未设置 UE_REPO_PAT 环境变量。")
        sys.exit(1)
    print("UE_REPO_PAT 已就绪。")

    if not gemini_api_key:
        print("致命错误：未设置 GEMINI_API_KEY 环境变量。")
        sys.exit(1)
    print("GEMINI_API_KEY 已就绪。")
    
    try:
        print("正在初始化 GitHub 客户端...")
        github_client = Github(pat)
        print("GitHub 客户端初始化完成。")
        
        gemini_model_name = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")
        print(f"正在配置 Gemini API，模型：{gemini_model_name}...")
        ai_client = genai.Client(api_key=gemini_api_key)
        print("Gemini API 配置完成。")
    except Exception as e:
        print(f"致命错误：初始化 API 失败：{e}")
        sys.exit(1)

    # --- Notification Target Check ---
    print("\n--- 2. 检查通知目标 ---")
    discussion_repo_name = os.environ.get("DISCUSSION_REPO")
    discussion_repo_pat = os.environ.get("DISCUSSION_REPO_PAT")
    slack_webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    slack_channel = os.environ.get("SLACK_CHANNEL")
    discord_webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")

    has_discussion_target = discussion_repo_name and discussion_repo_pat
    has_slack_target = slack_webhook_url and slack_channel
    has_discord_target = discord_webhook_url

    # A discussion repo without a PAT silently posts nowhere — warn explicitly.
    # (We intentionally do NOT fall back to GITHUB_TOKEN: that would auto-post to
    # the current repo, risking a leak if it is public. Discussion posting is
    # opt-in via DISCUSSION_REPO_PAT on a private repo.)
    if discussion_repo_name and not discussion_repo_pat:
        print("警告：已设置 DISCUSSION_REPO 但缺少 DISCUSSION_REPO_PAT。"
              "将跳过 GitHub Discussion 发布。请设置 DISCUSSION_REPO_PAT"
              "（具有私有仓库 Discussions 写入权限的 PAT）以启用此功能。")

    if not has_discussion_target and not has_slack_target and not has_discord_target:
        print("致命错误：未配置任何通知目标。请至少设置以下之一：DISCUSSION_REPO/DISCUSSION_REPO_PAT、SLACK_WEBHOOK_URL/SLACK_CHANNEL 或 DISCORD_WEBHOOK_URL。")
        sys.exit(1)
    
    print("通知目标已正确配置。")
    if has_discussion_target:
        print("- GitHub Discussion 已启用。")
    if has_slack_target:
        print("- Slack 通知已启用。")
    if has_discord_target:
        print("- Discord 通知已启用。")

    # --- Process Each Tracked Branch ---
    print("\n--- 3. 处理追踪分支 ---")
    targets = get_target_branches()
    print(f"正在追踪 {len(targets)} 个分支：{', '.join(branch for _, branch in targets)}")

    report_language = os.environ.get("REPORT_LANGUAGE", "Chinese")
    print(f"报告语言设置为：{report_language}")

    branch_results = []
    for label, branch in targets:
        print(f"\n--- 分支：{label} ({branch}) ---")
        try:
            branch_results.append(
                process_branch(github_client, ai_client, branch, label, gemini_model_name, report_language)
            )
        except Exception as e:
            # Isolate per-branch failures so one bad branch doesn't abort the rest.
            print(f"处理分支 '{branch}' 时发生意外错误：{e}")
            branch_results.append({"label": label, "branch": branch, "status": "error", "body": None, "shas": []})

    # Surface (do not dedupe) commits shared across branches.
    _warn_duplicate_shas(branch_results)

    has_ok = any(r["status"] == "ok" for r in branch_results)
    has_error = any(r["status"] == "error" for r in branch_results)

    # All branches empty (and none errored): nothing worth reporting — exit quietly.
    if not has_ok and not has_error:
        print("\n所有追踪分支均未发现重要提交。退出。")
        return

    # --- Generate Report Title ---
    # Date the report in the configured timezone (defaults to JST) so the daily
    # title matches when readers receive it. time.strftime() uses the runner's
    # UTC clock, which dates the report a day behind for JST readers.
    report_tz = os.environ.get("REPORT_TIMEZONE", "Asia/Tokyo")
    try:
        report_date = datetime.now(ZoneInfo(report_tz)).strftime('%Y-%m-%d')
    except Exception as e:
        print(f"警告：无效的 REPORT_TIMEZONE '{report_tz}'（{e}）；回退为 UTC。")
        report_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    report_title = f"Unreal Engine 每日报告 - {report_date}"

    # Track (target_name, success) so the workflow can fail if nothing posted.
    results = []

    # No branch produced content, but at least one errored: don't hide the
    # failure. Notify Slack/Discord (a Discussion needs a body) and fail the run.
    if not has_ok:
        failed = ", ".join(f"{r['label']} ({r['branch']})" for r in branch_results if r["status"] == "error")
        print(f"\n以下分支的报告生成全部失败：{failed}")
        error_message = f"错误：无法为以下分支生成 Unreal Engine 报告：{failed}。"
        if has_slack_target:
            print("\n--- 处理失败时的 Slack 通知 ---")
            results.append(("Slack", send_slack_notification(slack_webhook_url, slack_channel, error_message, report_title)))
        if has_discord_target:
            print("\n--- 处理失败时的 Discord 通知 ---")
            results.append(("Discord", send_discord_notification(discord_webhook_url, error_message, report_title)))
        print("\n--- 投递摘要 ---")
        for name, ok in results:
            print(f"  {'成功  ' if ok else '失败  '}：{name}")
        print("致命错误：所有分支的报告生成均失败；未投递任何报告。")
        sys.exit(1)

    # --- Build and Send the Combined Report ---
    print("\n--- 5. 生成并发送合并报告 ---")
    report_body = _build_combined_report(branch_results, report_language)

    # --- 5a. Post to GitHub Discussion ---
    if has_discussion_target:
        print("\n--- 5a. 发布到 GitHub Discussion ---")
        discussion_category = os.environ.get("DISCUSSION_CATEGORY", "日报")
        print(f"正在尝试发布到仓库 '{discussion_repo_name}'，分类：'{discussion_category}'")
        results.append(("GitHub Discussion", create_discussion(discussion_repo_name, report_title, report_body, discussion_repo_pat, category_name=discussion_category)))
    else:
        print("\n--- 5a. 未配置 GitHub Discussion 目标，跳过。 ---")

    # --- 5b. Post to Slack ---
    if has_slack_target:
        print("\n--- 5b. 发送到 Slack ---")
        results.append(("Slack", send_slack_notification(slack_webhook_url, slack_channel, report_body, report_title)))
    else:
        print("\n--- 5b. 未配置 Slack 目标，跳过。 ---")

    # --- 5c. Post to Discord ---
    if has_discord_target:
        print("\n--- 5c. 发送到 Discord ---")
        results.append(("Discord", send_discord_notification(discord_webhook_url, report_body, report_title)))
    else:
        print("\n--- 5c. 未配置 Discord 目标，跳过。 ---")

    # --- Delivery summary ---
    print("\n--- 投递摘要 ---")
    for name, ok in results:
        print(f"  {'成功  ' if ok else '失败  '}：{name}")
    if results and not any(ok for _, ok in results):
        print("致命错误：所有配置的通知目标均投递失败。")
        sys.exit(1)

    # --- Finish ---
    print("\n=============================================")
    print("更新检查脚本执行完毕")
    print("=============================================")

if __name__ == "__main__":
    main()
