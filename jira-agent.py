"""OpenAI Agents SDK agent wired to the Jira MCP server.

Requires OPENAI_API_KEY and Jira credentials in .env (project root).

Run from project root:
    uv run jira-agent.py

Or with a custom prompt:
    uv run jira-agent.py "Find open bugs in project ABC assigned to me"
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from agents import Agent, Runner, trace
from agents.mcp import MCPServerStdio
from dotenv import load_dotenv

JIRA_DIR = Path(__file__).resolve().parent
REPO_ROOT = JIRA_DIR

load_dotenv(JIRA_DIR / ".env", override=True)

JIRA_SERVER_PARAMS = {
    "command": "uv",
    "args": ["run", str(JIRA_DIR / "jira-server.py")],
    "cwd": str(REPO_ROOT),
}


async def run_jira_agent(
    request: str,
    model: str = "gpt-4o-mini",
) -> str:
    async with MCPServerStdio(
        params=JIRA_SERVER_PARAMS,
        client_session_timeout_seconds=60,
    ) as mcp_server:
        agent = Agent(
            name="jira_assistant",
            instructions=(
                "You are a Jira assistant with MCP tools to search issues (JQL) and fetch "
                "individual issues by key. Always use the appropriate tool before answering. "
                "Summarize results clearly: key, summary, status, assignee when available. "
                "If a tool returns JSON with error=true, explain the failure and suggest fixes "
                "(credentials, JQL syntax, or issue key)."
            ),
            model=model,
            mcp_servers=[mcp_server],
        )
        with trace("jira_agent"):
            result = await Runner.run(agent, request)
        return result.final_output


def main() -> None:
    if len(sys.argv) > 1:
        request = " ".join(sys.argv[1:])
    else:
        request = (
            'Search ffor issues updated in the last 7 days using JQL '
            '"updated >= -7d ORDER BY updated DESC" (limit 5). '
            "Summarize what you find."
        )
    print(asyncio.run(run_jira_agent(request)))


if __name__ == "__main__":
    main()
