"""
GitHub tools — recent activity across the user's repositories.
"""

import os
import httpx


def register(mcp):

    @mcp.tool()
    async def get_github_activity() -> str:
        """
        Summarize recent GitHub activity: pushes, PRs, and issues across the user's repos.
        Use when asked about GitHub, repositories, commits, pull requests, or code activity.
        """
        username = os.getenv("GITHUB_USERNAME")
        token = os.getenv("GITHUB_TOKEN", "")

        if not username:
            return "GitHub username not configured, boss. Set GITHUB_USERNAME in .env."

        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        try:
            async with httpx.AsyncClient(headers=headers, timeout=8) as client:
                resp = await client.get(
                    f"https://api.github.com/users/{username}/events",
                    params={"per_page": 30},
                )
                if resp.status_code == 401:
                    return "GitHub token is invalid, boss."
                if resp.status_code == 404:
                    return f"GitHub user '{username}' not found."
                if resp.status_code != 200:
                    return "GitHub API is unresponsive right now."

                events = resp.json()

        except Exception as e:
            return f"GitHub feed down, boss: {e}"

        pushes = []
        prs = []
        issues = []

        for event in events:
            etype = event.get("type")
            repo = event["repo"]["name"].split("/")[-1]  # just repo name, not owner/repo
            payload = event.get("payload", {})

            if etype == "PushEvent":
                commits = payload.get("commits", [])
                if commits:
                    msg = commits[-1].get("message", "").split("\n")[0][:60]
                    pushes.append(f"{repo}: {msg}")

            elif etype == "PullRequestEvent":
                action = payload.get("action", "")
                pr = payload.get("pull_request", {})
                title = pr.get("title", "")[:55]
                if action in ("opened", "closed", "merged"):
                    state = "merged" if pr.get("merged") else action
                    prs.append(f"[{state}] {repo}: {title}")

            elif etype == "IssuesEvent":
                action = payload.get("action", "")
                title = payload.get("issue", {}).get("title", "")[:55]
                if action in ("opened", "closed"):
                    issues.append(f"[{action}] {repo}: {title}")

        if not pushes and not prs and not issues:
            return "No recent GitHub activity found, boss."

        lines = ["## GitHub Activity\n"]
        if prs:
            lines.append("**Pull Requests:**")
            lines.extend(f"- {p}" for p in prs[:3])
        if pushes:
            lines.append("\n**Recent Commits:**")
            lines.extend(f"- {p}" for p in pushes[:4])
        if issues:
            lines.append("\n**Issues:**")
            lines.extend(f"- {i}" for i in issues[:3])

        return "\n".join(lines)
