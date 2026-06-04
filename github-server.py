"""MCP server exposing GitHub repository tools.

Run (from project root):
    uv run github-server.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

_GITHUB_DIR = Path(__file__).resolve().parent
load_dotenv(_GITHUB_DIR / ".env", override=True)

mcp = FastMCP("github_server")

_API_VERSION = "2022-11-28"


def _token() -> str:
    token = (os.getenv("GITHUB_TOKEN") or os.getenv("GITHUB_PAT") or "").strip()
    if not token:
        raise ValueError(
            "Missing GITHUB_TOKEN (or GITHUB_PAT). "
            f"Add it to {_GITHUB_DIR / '.env'}."
        )
    return token


def _resolve_repo(owner: str, repo: str) -> tuple[str, str]:
    resolved_owner = (owner or os.getenv("GITHUB_OWNER") or "").strip()
    resolved_repo = (repo or os.getenv("GITHUB_REPO") or "").strip()
    missing = [
        name
        for name, value in [
            ("owner (or GITHUB_OWNER)", resolved_owner),
            ("repo (or GITHUB_REPO)", resolved_repo),
        ]
        if not value
    ]
    if missing:
        raise ValueError(
            f"Missing repository target: {', '.join(missing)}. "
            "Pass owner/repo to the tool or set GITHUB_OWNER and GITHUB_REPO in .env."
        )
    return resolved_owner, resolved_repo


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {_token()}",
            "X-GitHub-Api-Version": _API_VERSION,
            "Content-Type": "application/json",
        }
    )
    return session


def _api_url(path: str) -> str:
    return f"https://api.github.com{path}"


def _to_json(payload: dict[str, Any] | list[Any]) -> str:
    return json.dumps(payload, indent=2, default=str)


def _error_json(exc: Exception) -> str:
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        try:
            detail = exc.response.json()
        except Exception:
            detail = exc.response.text
        return _to_json(
            {
                "error": True,
                "status_code": exc.response.status_code,
                "message": str(exc),
                "detail": detail,
            }
        )
    return _to_json({"error": True, "message": str(exc)})


def _get_repository(owner: str, repo: str) -> dict[str, Any]:
    owner, repo = _resolve_repo(owner, repo)
    session = _session()
    response = session.get(_api_url(f"/repos/{owner}/{repo}"), timeout=30)
    response.raise_for_status()
    return response.json()


def _list_pull_requests(
    owner: str, repo: str, state: str, per_page: int
) -> list[dict[str, Any]]:
    owner, repo = _resolve_repo(owner, repo)
    session = _session()
    response = session.get(
        _api_url(f"/repos/{owner}/{repo}/pulls"),
        params={
            "state": state,
            "per_page": max(1, min(per_page, 100)),
            "sort": "updated",
            "direction": "desc",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _get_pull_request(owner: str, repo: str, pr_number: int) -> dict[str, Any]:
    owner, repo = _resolve_repo(owner, repo)
    session = _session()
    response = session.get(
        _api_url(f"/repos/{owner}/{repo}/pulls/{pr_number}"),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _list_issues(
    owner: str, repo: str, state: str, labels: str, per_page: int
) -> list[dict[str, Any]]:
    owner, repo = _resolve_repo(owner, repo)
    params: dict[str, Any] = {
        "state": state,
        "per_page": max(1, min(per_page, 100)),
        "sort": "updated",
        "direction": "desc",
    }
    if labels.strip():
        params["labels"] = labels.strip()
    session = _session()
    response = session.get(
        _api_url(f"/repos/{owner}/{repo}/issues"),
        params=params,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _get_issue(owner: str, repo: str, issue_number: int) -> dict[str, Any]:
    owner, repo = _resolve_repo(owner, repo)
    session = _session()
    response = session.get(
        _api_url(f"/repos/{owner}/{repo}/issues/{issue_number}"),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _create_issue(
    owner: str, repo: str, title: str, body: str, labels: str
) -> dict[str, Any]:
    owner, repo = _resolve_repo(owner, repo)
    payload: dict[str, Any] = {"title": title.strip()}
    if body.strip():
        payload["body"] = body.strip()
    if labels.strip():
        payload["labels"] = [
            part.strip() for part in labels.split(",") if part.strip()
        ]
    session = _session()
    response = session.post(
        _api_url(f"/repos/{owner}/{repo}/issues"),
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _add_issue_comment(
    owner: str, repo: str, issue_number: int, body: str
) -> dict[str, Any]:
    owner, repo = _resolve_repo(owner, repo)
    session = _session()
    response = session.post(
        _api_url(f"/repos/{owner}/{repo}/issues/{issue_number}/comments"),
        json={"body": body.strip()},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _create_pull_request(
    owner: str,
    repo: str,
    title: str,
    head: str,
    base: str,
    body: str,
) -> dict[str, Any]:
    owner, repo = _resolve_repo(owner, repo)
    payload: dict[str, Any] = {
        "title": title.strip(),
        "head": head.strip(),
        "base": base.strip(),
    }
    if body.strip():
        payload["body"] = body.strip()
    session = _session()
    response = session.post(
        _api_url(f"/repos/{owner}/{repo}/pulls"),
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


@mcp.tool()
async def get_repository(owner: str = "", repo: str = "") -> str:
    """Get repository metadata (default branch, visibility, description).

    Args:
        owner: GitHub owner/org (optional if GITHUB_OWNER is set)
        repo: Repository name (optional if GITHUB_REPO is set)
    """
    try:
        return _to_json(_get_repository(owner, repo))
    except Exception as exc:
        return _error_json(exc)


@mcp.tool()
async def list_pull_requests(
    state: str = "open",
    per_page: int = 20,
    owner: str = "",
    repo: str = "",
) -> str:
    """List pull requests for a repository.

    Args:
        state: open, closed, or all
        per_page: Number of PRs to return (1-100)
        owner: GitHub owner/org (optional if GITHUB_OWNER is set)
        repo: Repository name (optional if GITHUB_REPO is set)
    """
    try:
        return _to_json(_list_pull_requests(owner, repo, state, per_page))
    except Exception as exc:
        return _error_json(exc)


@mcp.tool()
async def get_pull_request(
    pr_number: int,
    owner: str = "",
    repo: str = "",
) -> str:
    """Get a single pull request by number.

    Args:
        pr_number: Pull request number
        owner: GitHub owner/org (optional if GITHUB_OWNER is set)
        repo: Repository name (optional if GITHUB_REPO is set)
    """
    try:
        return _to_json(_get_pull_request(owner, repo, pr_number))
    except Exception as exc:
        return _error_json(exc)


@mcp.tool()
async def list_issues(
    state: str = "open",
    labels: str = "",
    per_page: int = 20,
    owner: str = "",
    repo: str = "",
) -> str:
    """List GitHub issues for a repository.

    Args:
        state: open, closed, or all
        labels: Optional comma-separated label filter
        per_page: Number of issues to return (1-100)
        owner: GitHub owner/org (optional if GITHUB_OWNER is set)
        repo: Repository name (optional if GITHUB_REPO is set)
    """
    try:
        return _to_json(_list_issues(owner, repo, state, labels, per_page))
    except Exception as exc:
        return _error_json(exc)


@mcp.tool()
async def get_issue(
    issue_number: int,
    owner: str = "",
    repo: str = "",
) -> str:
    """Get a single GitHub issue by number.

    Args:
        issue_number: Issue number
        owner: GitHub owner/org (optional if GITHUB_OWNER is set)
        repo: Repository name (optional if GITHUB_REPO is set)
    """
    try:
        return _to_json(_get_issue(owner, repo, issue_number))
    except Exception as exc:
        return _error_json(exc)


@mcp.tool()
async def create_issue(
    title: str,
    body: str = "",
    labels: str = "",
    owner: str = "",
    repo: str = "",
) -> str:
    """Create a GitHub issue.

    Args:
        title: Issue title
        body: Optional issue body (markdown supported)
        labels: Optional comma-separated labels
        owner: GitHub owner/org (optional if GITHUB_OWNER is set)
        repo: Repository name (optional if GITHUB_REPO is set)
    """
    try:
        return _to_json(_create_issue(owner, repo, title, body, labels))
    except Exception as exc:
        return _error_json(exc)


@mcp.tool()
async def add_issue_comment(
    issue_number: int,
    body: str,
    owner: str = "",
    repo: str = "",
) -> str:
    """Add a comment to a GitHub issue or pull request.

    Args:
        issue_number: Issue/PR number
        body: Comment text (markdown supported)
        owner: GitHub owner/org (optional if GITHUB_OWNER is set)
        repo: Repository name (optional if GITHUB_REPO is set)
    """
    try:
        return _to_json(_add_issue_comment(owner, repo, issue_number, body))
    except Exception as exc:
        return _error_json(exc)


@mcp.tool()
async def create_pull_request(
    title: str,
    head: str,
    base: str,
    body: str = "",
    owner: str = "",
    repo: str = "",
) -> str:
    """Create a pull request.

    Args:
        title: PR title
        head: Source branch (e.g. feature/login)
        base: Target branch (e.g. main)
        body: Optional PR description
        owner: GitHub owner/org (optional if GITHUB_OWNER is set)
        repo: Repository name (optional if GITHUB_REPO is set)
    """
    try:
        return _to_json(_create_pull_request(owner, repo, title, head, base, body))
    except Exception as exc:
        return _error_json(exc)


if __name__ == "__main__":
    mcp.run(transport="stdio")
