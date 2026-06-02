"""MCP server exposing Jira Cloud search and issue lookup tools.

Run (from repo root):
    uv run 2_openai/jira/jira_server.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

_JIRA_DIR = Path(__file__).resolve().parent
load_dotenv(_JIRA_DIR / ".env", override=True)

mcp = FastMCP("jira_server")


def _credentials() -> tuple[str, str, str]:
    base_url = (os.getenv("JIRA_BASE_URL") or "").strip().rstrip("/")
    email = (os.getenv("JIRA_EMAIL") or "").strip()
    token = (os.getenv("JIRA_API_TOKEN") or "").strip()
    missing = [
        name
        for name, value in [
            ("JIRA_BASE_URL", base_url),
            ("JIRA_EMAIL", email),
            ("JIRA_API_TOKEN", token),
        ]
        if not value
    ]
    if missing:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing)}. "
            f"Copy {_JIRA_DIR / '.env.example'} to {_JIRA_DIR / '.env'} and fill in values."
        )
    return base_url, email, token


def _session() -> tuple[requests.Session, str]:
    base_url, email, token = _credentials()
    session = requests.Session()
    session.auth = (email, token)
    session.headers.update(
        {"Accept": "application/json", "Content-Type": "application/json"}
    )
    return session, base_url


def _parse_fields(fields: str | None) -> list[str] | None:
    if not fields or not fields.strip():
        return None
    return [part.strip() for part in fields.split(",") if part.strip()]


def _to_json(payload: dict[str, Any]) -> str:
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


def _search_jira(jql: str, max_results: int, fields: str | None) -> dict[str, Any]:
    session, base_url = _session()
    body: dict[str, Any] = {
        "jql": jql,
        "maxResults": max(1, min(max_results, 100)),
    }
    field_list = _parse_fields(fields)
    if field_list:
        body["fields"] = field_list
    response = session.post(
        f"{base_url}/rest/api/3/search/jql", json=body, timeout=30
    )
    response.raise_for_status()
    return response.json()


def _get_jira_issue(issue_key: str, fields: str | None) -> dict[str, Any]:
    session, base_url = _session()
    params: dict[str, str] = {}
    field_list = _parse_fields(fields)
    if field_list:
        params["fields"] = ",".join(field_list)
    response = session.get(
        f"{base_url}/rest/api/3/issue/{issue_key.strip()}",
        params=params or None,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _create_jira_issue(
    project_key: str,
    issue_type: str,
    summary: str,
    description: str = "",
    extra_fields_json: str = "",
) -> dict[str, Any]:
    session, base_url = _session()
    fields: dict[str, Any] = {
        "project": {"key": project_key.strip()},
        "issuetype": {"name": issue_type.strip()},
        "summary": summary.strip(),
    }
    if description.strip():
        fields["description"] = {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": description.strip()}],
                }
            ],
        }
    if extra_fields_json.strip():
        extras = json.loads(extra_fields_json)
        if not isinstance(extras, dict):
            raise ValueError("extra_fields_json must be a JSON object.")
        fields.update(extras)
    response = session.post(
        f"{base_url}/rest/api/3/issue",
        json={"fields": fields},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _update_jira_issue(issue_key: str, fields_json: str) -> dict[str, Any]:
    session, base_url = _session()
    payload = json.loads(fields_json)
    if not isinstance(payload, dict):
        raise ValueError("fields_json must be a JSON object.")
    response = session.put(
        f"{base_url}/rest/api/3/issue/{issue_key.strip()}",
        json={"fields": payload},
        timeout=30,
    )
    response.raise_for_status()
    return {"ok": True, "issue_key": issue_key.strip()}


def _add_jira_comment(issue_key: str, comment: str) -> dict[str, Any]:
    session, base_url = _session()
    body = {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": comment.strip()}],
                }
            ],
        }
    }
    response = session.post(
        f"{base_url}/rest/api/3/issue/{issue_key.strip()}/comment",
        json=body,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _get_transitions(issue_key: str) -> dict[str, Any]:
    session, base_url = _session()
    response = session.get(
        f"{base_url}/rest/api/3/issue/{issue_key.strip()}/transitions",
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _transition_issue(issue_key: str, transition: str) -> dict[str, Any]:
    transitions = _get_transitions(issue_key).get("transitions", [])
    chosen = None
    wanted = transition.strip().lower()
    for item in transitions:
        if str(item.get("id", "")).lower() == wanted or str(
            item.get("name", "")
        ).lower() == wanted:
            chosen = item
            break
    if not chosen:
        available = [
            {"id": item.get("id"), "name": item.get("name")}
            for item in transitions
        ]
        raise ValueError(
            f"Transition '{transition}' not found. Available transitions: "
            f"{json.dumps(available)}"
        )

    session, base_url = _session()
    response = session.post(
        f"{base_url}/rest/api/3/issue/{issue_key.strip()}/transitions",
        json={"transition": {"id": chosen["id"]}},
        timeout=30,
    )
    response.raise_for_status()
    return {
        "ok": True,
        "issue_key": issue_key.strip(),
        "transition": {"id": chosen["id"], "name": chosen.get("name")},
    }


@mcp.tool()
async def search_issues(
    jql: str,
    max_results: int = 20,
    fields: str = "",
) -> str:
    """Search Jira issues using JQL (Jira Query Language).

    Args:
        jql: JQL query, e.g. 'project = MYPROJ AND status = "In Progress"'
        max_results: Maximum issues to return (1-100, default 20)
        fields: Optional comma-separated field ids/names (e.g. summary,status,assignee)
    """
    try:
        return _to_json(
            _search_jira(jql, max_results, fields or None)
        )
    except Exception as exc:
        return _error_json(exc)


@mcp.tool()
async def get_issue(issue_key: str, fields: str = "") -> str:
    """Get a single Jira issue by key or id.

    Args:
        issue_key: Issue key such as PROJ-123
        fields: Optional comma-separated field ids/names to include in the response
    """
    try:
        return _to_json(_get_jira_issue(issue_key, fields or None))
    except Exception as exc:
        return _error_json(exc)


@mcp.tool()
async def create_issue(
    project_key: str,
    issue_type: str,
    summary: str,
    description: str = "",
    extra_fields_json: str = "",
) -> str:
    """Create a Jira issue.

    Args:
        project_key: Project key such as PROJ
        issue_type: Issue type name, e.g. Task, Bug, Story
        summary: Issue summary/title
        description: Optional plain-text description
        extra_fields_json: Optional JSON object string for additional fields
    """
    try:
        return _to_json(
            _create_jira_issue(
                project_key, issue_type, summary, description, extra_fields_json
            )
        )
    except Exception as exc:
        return _error_json(exc)


@mcp.tool()
async def update_issue(issue_key: str, fields_json: str) -> str:
    """Update Jira issue fields.

    Args:
        issue_key: Issue key such as PROJ-123
        fields_json: JSON object string of fields to update
    """
    try:
        return _to_json(_update_jira_issue(issue_key, fields_json))
    except Exception as exc:
        return _error_json(exc)


@mcp.tool()
async def add_comment(issue_key: str, comment: str) -> str:
    """Add a plain-text comment to a Jira issue.

    Args:
        issue_key: Issue key such as PROJ-123
        comment: Comment text
    """
    try:
        return _to_json(_add_jira_comment(issue_key, comment))
    except Exception as exc:
        return _error_json(exc)


@mcp.tool()
async def transition_issue(issue_key: str, transition: str) -> str:
    """Transition a Jira issue by transition id or name.

    Args:
        issue_key: Issue key such as PROJ-123
        transition: Transition id or name, e.g. "31" or "Done"
    """
    try:
        return _to_json(_transition_issue(issue_key, transition))
    except Exception as exc:
        return _error_json(exc)


if __name__ == "__main__":
    mcp.run(transport="stdio")
