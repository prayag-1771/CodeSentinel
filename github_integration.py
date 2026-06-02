from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class GitHubPRInfo:
    owner: str
    repo: str
    pr_number: int


def parse_pr_url(url_or_id: str) -> GitHubPRInfo:
    """Parse GitHub repository owner, repo name, and pull request number from a URL or string identifier.
    
    Supported formats:
    - https://github.com/owner/repo/pull/123
    - github.com/owner/repo/pull/123
    - owner/repo/pull/123
    - owner/repo#123
    - owner/repo:123
    """
    url_or_id = url_or_id.strip()
    
    # Check for URL-like formats
    pattern = r"(?:https?://)?(?:github\.com/)?([^/]+)/([^/]+)/(?:pull|issues)/(\d+)"
    match = re.search(pattern, url_or_id)
    if match:
        return GitHubPRInfo(
            owner=match.group(1),
            repo=match.group(2),
            pr_number=int(match.group(3))
        )
        
    # Check for owner/repo#123 or owner/repo:123 format
    pattern_alt = r"^([^/]+)/([^#:]+)[#:](\d+)$"
    match_alt = re.match(pattern_alt, url_or_id)
    if match_alt:
        return GitHubPRInfo(
            owner=match_alt.group(1),
            repo=match_alt.group(2),
            pr_number=int(match_alt.group(3))
        )
        
    raise ValueError(
        f"Invalid GitHub PR URL or identifier: '{url_or_id}'. "
        "Expected format: 'https://github.com/owner/repo/pull/123' or 'owner/repo#123'"
    )


def fetch_pr_diff(info: GitHubPRInfo, token: str | None = None) -> str:
    """Fetch the unified diff of the PR from GitHub API."""
    url = f"https://api.github.com/repos/{info.owner}/{info.repo}/pulls/{info.pr_number}"
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github.v3.diff")
    req.add_header("User-Agent", "CodeSentinel-AI-Agent")
    
    if token:
        req.add_header("Authorization", f"Bearer {token}")
        
    try:
        with urllib.request.urlopen(req) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else ""
        raise RuntimeError(
            f"Failed to fetch PR diff: HTTP {e.code} ({e.reason}).\nResponse: {body}"
        ) from e
    except Exception as e:
        raise RuntimeError(f"Connection error while fetching PR diff: {e}") from e


def submit_pr_review(
    info: GitHubPRInfo,
    token: str,
    body: str,
    comments: list[dict[str, Any]],
    event: str = "COMMENT"
) -> None:
    """Submit a Pull Request Review with inline comments.
    
    Payload structure:
    {
      "body": "Review summary",
      "event": "COMMENT",
      "comments": [
        {
          "path": "file.py",
          "line": 10,
          "side": "RIGHT",
          "body": "Comment body"
        }
      ]
    }
    """
    url = f"https://api.github.com/repos/{info.owner}/{info.repo}/pulls/{info.pr_number}/reviews"
    payload = {
        "body": body,
        "event": event,
    }
    if comments:
        payload["comments"] = comments

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "CodeSentinel-AI-Agent")
    req.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(req) as response:
            response.read()
    except urllib.error.HTTPError as e:
        body_err = e.read().decode("utf-8") if e.fp else ""
        raise urllib.error.HTTPError(
            req.full_url, e.code, f"{e.reason}. Response: {body_err}", req.headers, e.fp
        ) from e


def submit_pr_comment(info: GitHubPRInfo, token: str, body: str) -> None:
    """Submit a single PR summary comment (fallback mechanism)."""
    url = f"https://api.github.com/repos/{info.owner}/{info.repo}/issues/{info.pr_number}/comments"
    payload = {
        "body": body
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "CodeSentinel-AI-Agent")
    req.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(req) as response:
            response.read()
    except urllib.error.HTTPError as e:
        body_err = e.read().decode("utf-8") if e.fp else ""
        raise RuntimeError(
            f"Failed to post fallback PR comment: HTTP {e.code} ({e.reason}).\nResponse: {body_err}"
        ) from e
    except Exception as e:
        raise RuntimeError(f"Connection error while posting fallback comment: {e}") from e
